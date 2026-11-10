#!/usr/bin/env python3
"""Publish one verified (platform, package) build as an independent GitHub Release.

由发布矩阵任务在每个组合安装验证通过后调用。幂等语义：目标 Release 已存在时
必须逐字节证明资产与本次产物一致，否则失败（不重建、不写发布凭据）；新建
Release 成功后同样必须通过远程全资产逐字节校验才写凭据——创建成功不等于完整
成功。Release 资产恰好是包文件 + SHA256SUMS；build.spec / build.json 只作为
凭据工件随 published/ 上传，绝不当二进制资产发布。tag 统一为
<platform>-<package>-<version>-<release>；RPM release 取自 rpm header 权威
元数据而非文件名。
"""

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import rpm

import check_update
import project_config
import record_versions

# Vim 的源码包没有同名二进制 RPM；编辑器在 vim-enhanced 里。
MAIN_BINARY_PACKAGE = {"vim": "vim-enhanced"}
RELEASE_SUFFIXES = {"rpm": ".rpm", "deb": ".deb"}
RELEASE_RE = re.compile(r"\d+[A-Za-z0-9._+~^]*")
DEB_RELEASE_RE = re.compile(r"\d+ubuntu22\.04")


def github(*args, text=True):
    return subprocess.run(["gh", *args], check=True, stdout=subprocess.PIPE,
                          text=text).stdout


def read_rpm_header(path):
    """权威 RPM 元数据：(name, version, release, arch)，直接读自二进制 header。"""
    transaction = rpm.TransactionSet()
    # 本包刚由受控构建产出：跳过签名/摘要校验，但保留完整 header 解析。
    transaction.setVSFlags(rpm._RPMVSF_NOSIGNATURES | rpm._RPMVSF_NODIGESTS)
    with open(path, "rb") as handle:
        header = transaction.hdrFromFdno(handle.fileno())
    return header["name"], header["version"], header["release"], header["arch"]


AUTO_GENERATED_SUFFIXES = ("-debuginfo", "-debugsource")


def spec_package_names(spec_path):
    """build.spec 声明的二进制包名集合（含 %package 子包，如 ntpdate/sntp）。"""
    spec = rpm.spec(str(spec_path))
    return {package.header["name"] for package in spec.packages}


def validate_rpm_set(dist, package, version, release, spec_path, platform):
    """本次构建的全部 RPM 必须锚定 spec 的二进制包集合与平台展开身份。

    * 平台归属由 spec 宏展开（dist = "." + 平台 id）独立验证：spec 展开的
      N/V/R 必须与主包 header 一致，禁止用文件名拼双平台或前缀推断。
    * 每个 RPM 文件名必须精确等于 header 的 N-V-R.arch.rpm（改名伪装拒绝）。
    * 允许 spec 声明的任意子包（含 ntpdate/sntp 非前缀名）、noarch、构建期
      自动生成的 -debuginfo/-debugsource；拒绝混入的同 EVR 无关包与任何
      V/R 不一致子包。远程 legacy Release 没有 spec，不受本约束。
    """
    spec_name, spec_version, spec_release = record_versions.spec_identity(
        spec_path, "." + platform)
    if (spec_name, spec_version, spec_release) != (package, version, release):
        raise ValueError("build.spec expanded identity mismatch: %s/%s/%s != %s/%s/%s (%s)"
                         % (spec_name, spec_version, spec_release,
                            package, version, release, spec_path))
    declared = spec_package_names(spec_path)
    for path in sorted(dist.glob("*.rpm")):
        name, hdr_version, hdr_release, arch = read_rpm_header(path)
        expected = "%s-%s-%s.%s.rpm" % (name, hdr_version, hdr_release, arch)
        if path.name != expected:
            raise ValueError("filename does not match RPM header: %s != %s"
                             % (path.name, expected))
        if hdr_version != version or hdr_release != release:
            raise ValueError("RPM V/R differs from primary header: %s (%s/%s)"
                             % (path.name, hdr_version, hdr_release))
        if arch not in ("x86_64", "noarch"):
            raise ValueError("unexpected RPM arch: %s (%s)" % (path.name, arch))
        if name in declared or name.endswith(AUTO_GENERATED_SUFFIXES):
            continue
        raise ValueError("unrelated RPM not declared by build.spec: %s (%s)" % (path.name, name))


def build_metadata(dist):
    """scripts/package.sh 写入的构建凭据：RPM 用 build.spec，DEB 用 build.json。"""
    rpm_spec = dist / "build.spec"
    deb_meta = dist / "build.json"
    if rpm_spec.is_file() != deb_meta.is_file():
        return ("rpm", rpm_spec) if rpm_spec.is_file() else ("deb", deb_meta)
    raise ValueError("exactly one of build.spec / build.json expected in " + str(dist))


def verify_manifest(dist, suffix):
    """SHA256SUMS 必须恰好覆盖全部包文件，且逐个哈希一致。"""
    manifest = dist / "SHA256SUMS"
    files = {path.name for path in dist.glob("*" + suffix)}
    if not files:
        raise ValueError("no %s files in %s" % (suffix, dist))
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](?:\./)?(\S+)", line)
        if not match or match[2] in entries:
            raise ValueError("invalid checksum manifest: " + str(manifest))
        entries[match[2]] = match[1].lower()
    if set(entries) != files:
        raise ValueError("manifest must cover exactly the package files: %s"
                         % sorted(set(entries) ^ files))
    for name, digest in entries.items():
        actual = hashlib.sha256((dist / name).read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError("checksum mismatch: %s/%s" % (dist, name))
    return files


def select_main_rpm(dist, package, version):
    """主二进制 RPM 及其 release。

    release 以 rpm header 为权威；文件名必须精确等于 header 的
    N-V-R.arch.rpm（不拼双平台、不用前缀放宽）。平台归属由 validate_rpm_set
    的 spec 宏展开独立验证；含连字符/下划线的包名按前缀定位，歧义直接失败。
    """
    primary = MAIN_BINARY_PACKAGE[package] if package in MAIN_BINARY_PACKAGE else package
    mains = []
    for path in sorted(dist.glob("%s-%s-*.rpm" % (primary, version))):
        name, header_version, release, arch = read_rpm_header(path)
        if (name, header_version, arch) != (primary, version, "x86_64"):
            continue
        if not RELEASE_RE.fullmatch(release):
            raise ValueError("invalid release in RPM header: %s (%s)" % (release, path.name))
        expected = "%s-%s-%s.%s.rpm" % (name, header_version, release, arch)
        if path.name != expected:
            raise ValueError("filename does not match RPM header: %s != %s"
                             % (path.name, expected))
        mains.append((path, release))
    if len(mains) != 1:
        raise ValueError("需要且仅需一个主 RPM (%s %s): %s"
                         % (package, version,
                            ", ".join(path.name for path, _ in mains) or "none"))
    return mains[0]


def deb_release(dist):
    metadata = json.loads((dist / "build.json").read_text(encoding="utf-8"))
    release = metadata.get("release", "")
    if not DEB_RELEASE_RE.fullmatch(release):
        raise ValueError("unexpected DEB release metadata: " + str(release))
    return release


def expected_assets(dist, suffix):
    return sorted(dist.glob("*" + suffix)) + [dist / "SHA256SUMS"]


def verify_existing(repo, tag, dist, assets):
    """已存在或刚创建的 Release 必须逐字节等于本次产物；失败绝不写凭据。"""
    listing = json.loads(github("release", "view", tag, "--repo", repo, "--json", "assets"))
    remote = {asset["name"]: asset for asset in listing["assets"]}
    expected = {path.name for path in assets}
    if set(remote) != expected:
        raise ValueError("Release %s asset set mismatch: %s"
                         % (tag, sorted(set(remote) ^ expected)))
    for path in assets:
        asset = remote[path.name]
        if asset.get("state") != "uploaded" or asset.get("size", 0) <= 0:
            raise ValueError("missing or incomplete asset: %s/%s" % (tag, path.name))
        data = github("release", "download", tag, "--repo", repo,
                      "--pattern", path.name, "--output", "-", text=False)
        if data != path.read_bytes():
            raise ValueError("asset byte mismatch: %s/%s" % (tag, path.name))


def release_notes(family, platform, package, version, source_url, dist):
    if family == "deb":
        notes = (
            "原生 DEB 升级包：openssh-client、openssh-server、"
            "openssh-sftp-server。官方上游源码经固定 release key 验签；通过上游 "
            "regress、DEB 门禁和五场景安装验证。动态链接系统 OpenSSL/zlib/PAM/Kerberos。"
            "保留已有配置与 host key，安装/升级不主动重启 SSH。下载全部 deb 与 "
            "SHA256SUMS，先执行 sha256sum -c SHA256SUMS，再 sudo apt install ./*.deb。"
            "验证配置后手动重启 ssh 服务；首次启动由服务生成缺失密钥。详细说明见仓库 README。")
    elif package == "openssh":
        notes = (
            "OpenSSH portable 官方源码 openssh-%s.tar.gz（构建时已验证官方 GPG 签名）；"
            "静态链接 OpenSSL 与 zlib，动态链接 glibc / PAM / Kerberos5。保留已有配置"
            "和 host key；本包安装/升级不主动重启 sshd，旧发行版包卸载脚本仍可能触发"
            "一次重启，升级后请按需手动 service sshd restart 或 systemctl daemon-reload "
            "&& systemctl restart sshd。完整说明见仓库 README。" % version)
    else:
        notes = ("官方上游源码：%s；使用仓库构建 spec 在固定 digest 镜像内构建，"
                 "经过干净目标系统安装与命令验证。" % (source_url or "固定官方源"))
    manifest = dist / "SHA256SUMS"
    if manifest.is_file():
        notes += "\n\n### 产物校验\n```\n" + manifest.read_text(encoding="utf-8") + "```"
    return notes


def create_release(repo, tag, dist, assets, title, notes):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as notes_file:
        notes_file.write(notes)
        notes_path = notes_file.name
    try:
        github("release", "create", tag, *(str(path) for path in assets),
               "--repo", repo, "--title", title, "--notes-file", notes_path)
    finally:
        pathlib.Path(notes_path).unlink(missing_ok=True)


def write_receipt(root, platform, package, version, release, tag, metadata, family):
    """published/ 凭据树：receipt + 构建 spec / DEB 元数据副本（哈希入 receipt）。"""
    root = pathlib.Path(root)
    row = {"platform": platform, "package": package, "version": version,
           "release": release, "tag": tag}
    if family == "rpm":
        target = root / "spec" / platform / (package + ".spec")
        row["spec_sha256"] = hashlib.sha256(metadata.read_bytes()).hexdigest()
    else:
        target = root / "metadata" / (platform + "-" + package + ".json")
        row["metadata_sha256"] = hashlib.sha256(metadata.read_bytes()).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(metadata, target)
    receipts = root / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / (platform + "-" + package + ".json")).write_text(
        json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return row


def publish(dist, platform, package, version, repo, published_root="published",
            source_url="", token=None, output=None, get_target=None):
    dist = pathlib.Path(dist)
    # 目标必须已声明且启用，构建凭据种类必须与配置 family 一致（收敛到 project_config）。
    if get_target is None:
        get_target = project_config.get_target
    target = get_target(platform, package)
    family, metadata = build_metadata(dist)
    if family != target["family"]:
        raise ValueError("build metadata kind %r does not match configured family %r for %s/%s"
                         % (family, target["family"], platform, package))
    suffix = RELEASE_SUFFIXES[family]
    verify_manifest(dist, suffix)
    if family == "rpm":
        _, release = select_main_rpm(dist, package, version)
        # 本次新构建的 receipt/publish 必须锚定 spec 包集合与平台展开身份
        # （远程 legacy 无 spec，不受此约束）。
        validate_rpm_set(dist, package, version, release, metadata, platform)
    else:
        release = deb_release(dist)
    tag = "%s-%s-%s-%s" % (platform, package, version, release)
    assets = expected_assets(dist, suffix)
    if check_update.release_exists(repo, tag, token):
        print("Release %s 已存在，校验资产完整性…" % tag)
    else:
        family_label = "DEB" if family == "deb" else "RPM"
        machine = "amd64" if family == "deb" else "x86_64"
        title = "%s %s %s (%s, %s)" % (package, version, family_label, platform, machine)
        create_release(repo, tag, dist, assets, title,
                       release_notes(family, platform, package, version, source_url, dist))
    # 创建成功不等于完整成功：远程资产必须逐字节校验通过才写发布凭据。
    verify_existing(repo, tag, dist, assets)
    print("Release %s 资产校验通过" % tag)
    row = write_receipt(published_root, platform, package, version, release, tag,
                        metadata, family)
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write("tag=" + tag + "\n")
    return row["tag"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="dist/<platform>/<package> artifact dir")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--source-url", default="", help="matrix source URL for release notes")
    parser.add_argument("--published-root", default="published")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    try:
        publish(args.dir, args.platform, args.package, args.version, args.repo,
                published_root=args.published_root, source_url=args.source_url,
                token=os.environ.get("GH_TOKEN", ""), output=args.output)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, rpm.error) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
