#!/usr/bin/env python3
"""Centralized serial Release retention across per-(platform, package) publications.

同一个进程串行处理本次全部发布凭据，避免矩阵并行清理的竞态与双删。规则：

* receipt 先经 record_versions.read_receipt 全量预检（身份 + 哈希 + 构建产物
  一致性），全部通过才发起任何远程校验与删除；一张坏凭据 = 零删除。
* 只保留同 (platform, package) 组合下 EVR 最高的成功 Release；RPM 用
  rpm.labelCompare（~rc 语义正确），Ubuntu 用 dpkg --compare-versions，绝不按
  创建时间。较低版本补发被清理后，其 receipt 在重入时按「可证明更高完整替代」
  降级为 superseded，不阻断批次其他目标，也不伪造放行。
* 资产严格校验：每个 RPM 资产的 N/V/R/arch 必须与 tag（旧合并项按旧约定还原
  R.<platform>）完全一致，主包必须 x86_64；noarch 子包按同 V-R 支持。
* 旧格式 tag 识别为同组合回退：<pkg>-<el>-<ver>-<rel>（组件）、
  openssh-ubuntu2204-*（旧 DEB）；包名取自启用注册表构造正则，分隔符名字
  （demo-tool/demo_tool）无歧义。旧合并 Release v<ver>[-<rel>] 覆盖 EL7+EL8，
  仅当两个平台都存在不低于它（按还原后的 R.<platform> 比较）的完整且校验通过
  的新格式发布才删除，平台未配置/被禁用绝不删除。
* 按不可变 Release ID 删除，Git tag 一律保留。
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
import pathlib
import re
import subprocess
import sys

import rpm

import project_config
import record_versions

MANIFEST = "SHA256SUMS"
UBI_DEB_PACKAGES = ("openssh-client", "openssh-server", "openssh-sftp-server")
# 旧合并 Release 的覆盖范围固定是 EL7 + EL8；任何一个缺失（未配置/禁用）都不能删。
MERGED_PLATFORMS = ("el7", "el8")
# RPM 资产名结构：N-V-R.arch.rpm（V、R 不含连字符；noarch 子包按同 V-R 支持）。
RPM_ASSET_RE = re.compile(
    r"(?P<name>.+)-(?P<version>[^-]+)-(?P<release>[^-]+)\.(?P<arch>x86_64|noarch)\.rpm")


@dataclass(frozen=True)
class ReleaseKey:
    platform: str  # 配置平台 id；旧合并 Release 为 "all"
    package: str
    version: str
    release: str
    fmt: str       # new | legacy_component | legacy_ubuntu | legacy_merged
    family: str = "rpm"  # rpm|deb，由配置平台表在解析时填充，不硬编码平台名单

    @property
    def combo(self):
        return None if self.platform == "all" else (self.platform, self.package)

    def expected_release(self, platform=None):
        """资产必须匹配的 release 段；旧合并项按旧约定还原 R.<platform>。"""
        if self.platform == "all":
            return "%s.%s" % (self.release, platform)
        return self.release


def parse_tag(tag, platforms, packages, families):
    """平台/包集合与 family 全部来自配置注册表（re.escape 处理分隔符名字）。"""
    names = "|".join(sorted((re.escape(name) for name in platforms), key=len, reverse=True))
    pkgs = "|".join(sorted((re.escape(name) for name in packages), key=len, reverse=True))
    match = re.fullmatch(
        r"(?P<platform>%s)-(?P<package>%s)-(?P<version>[^-]+)-"
        r"(?P<release>\d+[A-Za-z0-9._+~^]*)" % (names, pkgs), tag)
    if match:
        return ReleaseKey(match["platform"], match["package"],
                          match["version"], match["release"], "new",
                          families.get(match["platform"], "rpm"))
    match = re.fullmatch(r"openssh-ubuntu2204-(\d+\.\d+p\d+)-(\d+ubuntu22\.04)", tag)
    if match:
        return ReleaseKey("ubuntu2204", "openssh", match[1], match[2], "legacy_ubuntu",
                          families.get("ubuntu2204", "deb"))
    # 旧 UBI OpenSSH 同时发布两个 RPM 平台；最早的 tag 没有 release 段，代表 rel 1。
    match = re.fullmatch(r"v(\d+\.\d+p\d+)(?:-(\d+))?", tag)
    if match:
        return ReleaseKey("all", "openssh", match[1], match[2] or "1", "legacy_merged", "rpm")
    match = re.fullmatch(
        r"(?P<package>%s)-(el[78]|centos7)-([^-]+)-(\d+[A-Za-z0-9._+~^]*)" % pkgs, tag)
    if match and (match["package"] != "openssh" or match[2] == "centos7"):
        return ReleaseKey(match[2], match["package"], match[3], match[4], "legacy_component",
                          families.get(match[2], "rpm"))
    return None


def github(*args, text=True):
    return subprocess.run(["gh", *args], check=True, stdout=subprocess.PIPE, text=text).stdout


def _checksums_from_manifest(contents, tag, manifest, suffix):
    checksums = {}
    for line in contents.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](?:\./)?([^/]+%s)" % suffix, line)
        if not match or match[2] in checksums:
            raise ValueError("invalid checksum manifest: " + tag + "/" + manifest)
        checksums[match[2]] = match[1].lower()
    return checksums


def _digest(repo, tag, assets, name, checksum):
    digest = assets[name].get("digest")
    if not digest:
        # 旧资产可能没有服务端 SHA256；此时必须下载后实测。
        data = github("release", "download", tag, "--repo", repo,
                      "--pattern", name, "--output", "-", text=False)
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
    if digest != "sha256:" + checksum:
        raise ValueError("package checksum mismatch: %s/%s" % (tag, name))


def _require_uploaded(assets, tag, names):
    for name in names:
        asset = assets.get(name, {})
        if asset.get("state") != "uploaded" or asset.get("size", 0) <= 0:
            raise ValueError("missing or incomplete asset: %s/%s" % (tag, name))


def _manifest_assets(repo, tag, assets, rpms, manifest, suffix):
    """清单必须恰好覆盖本平台全部 RPM，且逐资产哈希一致。"""
    _require_uploaded(assets, tag, rpms | {manifest})
    contents = github("release", "download", tag, "--repo", repo,
                      "--pattern", manifest, "--output", "-")
    checksums = _checksums_from_manifest(contents, tag, manifest, suffix)
    if set(checksums) != rpms:
        raise ValueError("RPM assets do not match checksum manifest: %s/%s" % (tag, manifest))
    for name, checksum in checksums.items():
        _digest(repo, tag, assets, name, checksum)


def verify_release(repo, release, key):
    """删除任何回退项之前，保留项与本次发布必须具备完整且哈希一致的资产。"""
    if key.family == "deb":
        return verify_deb_release(repo, release, key)
    tag = release["tag_name"]
    assets = {asset["name"]: asset for asset in release["assets"]}
    if len(assets) != len(release["assets"]):
        raise ValueError("duplicate release assets: " + tag)
    all_rpms = {name for name in assets if name.endswith(".rpm")}
    sections = ("el7", "el8") if key.platform == "all" else (key.platform,)
    covered = set()
    for section in sections:
        expected_release = key.expected_release(section)
        rpms = set()
        primaries = {}
        for name in all_rpms:
            match = RPM_ASSET_RE.fullmatch(name)
            if not match:
                raise ValueError("unrecognized RPM asset name: %s/%s" % (tag, name))
            if match["version"] != key.version or match["release"] != expected_release:
                raise ValueError("RPM asset does not match tag: %s/%s" % (tag, name))
            rpms.add(name)
            if match["arch"] == "x86_64":
                primaries.setdefault(match["name"], name)
        required = (("openssh", "openssh-clients", "openssh-server")
                    if key.package == "openssh" else (key.package,))
        for package in required:
            primary = primaries.get(package)
            if primary is None or not primary.startswith(
                    "%s-%s-%s." % (package, key.version, expected_release)):
                raise ValueError("missing or duplicate primary RPM: %s/%s/%s"
                                 % (tag, package, section))
        manifest = MANIFEST + "-" + section if key.platform == "all" else MANIFEST
        _manifest_assets(repo, tag, assets, rpms, manifest, r"\.rpm")
        covered |= rpms
    if covered != all_rpms:
        raise ValueError("unexpected platform in RPM assets: " + tag)


def verify_deb_release(repo, release, key):
    """新格式 DEB 资产 = 3 个精确 deb + SHA256SUMS；旧格式额外携带元数据文件。"""
    tag = release["tag_name"]
    assets = {asset["name"]: asset for asset in release["assets"]}
    expected = {"%s_%s-%s_amd64.deb" % (package, key.version, key.release)
                for package in UBI_DEB_PACKAGES}
    allowed = expected | {MANIFEST}
    if key.fmt != "new":
        allowed |= {"build.json", "SOURCE-SHA256SUM", "changelog"}
    if len(assets) != len(release["assets"]) or set(assets) != allowed:
        raise ValueError("missing or unexpected DEB assets: " + tag)
    _require_uploaded(assets, tag, allowed)
    contents = github("release", "download", tag, "--repo", repo,
                      "--pattern", MANIFEST, "--output", "-")
    checksums = _checksums_from_manifest(contents, tag, MANIFEST, r"\.deb")
    if set(checksums) != expected:
        raise ValueError("DEB assets do not match checksum manifest: " + tag)
    for name, checksum in checksums.items():
        _digest(repo, tag, assets, name, checksum)


def newer_release(key, previous):
    if key.family == "deb":
        result = subprocess.run(["dpkg", "--compare-versions",
                                 "1:%s-%s" % (key.version, key.release),
                                 "gt", "1:%s-%s" % (previous.version, previous.release)],
                                check=False)
        if result.returncode not in (0, 1):
            raise ValueError("dpkg version comparison failed")
        return result.returncode == 0
    return rpm.labelCompare(("0", key.version, key.release),
                            ("0", previous.version, previous.release)) > 0


def _collect(repo, platforms, packages, families):
    """全部非 draft/prerelease Release 按 (platform, package) 归组；合并项单列。"""
    pages = json.loads(github("api", "--paginate", "--slurp",
                              "repos/" + repo + "/releases?per_page=100"))
    indexed = {}
    merged = []
    for page in pages:
        for release in page:
            if release["draft"] or release["prerelease"]:
                continue
            key = parse_tag(release["tag_name"], platforms, packages, families)
            if key is None:
                continue
            if key.combo is None:
                merged.append((release, key))
            else:
                indexed.setdefault(key.combo, []).append((release, key))
    return indexed, merged


def _newest(indexed, combo, fmt=None):
    """组合内 EVR 最高的候选；fmt 限定新格式（替代判定默认只认新格式）。"""
    candidates = [item for item in indexed.get(combo, [])
                  if fmt is None or item[1].fmt == fmt]
    if not candidates:
        return None
    best = candidates[0]
    for item in candidates[1:]:
        if newer_release(item[1], best[1]):
            best = item
    return best


def prune(repo, receipts, platforms, upstreams, combos, families,
          dry_run=False, get_target=None):
    packages = set(upstreams)
    # 阶段零：本地全量预检 receipt（身份 + 哈希 + 构建产物一致性）；一张坏凭据
    # 即中止，绝不发起任何远程校验或删除。
    rows = []
    for receipt in receipts:
        row = record_versions.read_receipt(receipt, get_target=get_target)
        if (row["platform"], row["package"]) not in combos:
            raise ValueError("receipt target is not configured: %s/%s"
                             % (row["platform"], row["package"]))
        rows.append(row)
    indexed, merged = _collect(repo, platforms, packages, families)
    # 本次发布定位：凭据指向的 Release 必须真实存在；缺失时仅当同组合存在
    # 更高 EVR 且完整校验通过的已发布替代（保留项），才视为已被保留策略删除
    # 的重入（superseded），否则硬失败——绝不静默忽略缺失。superseded 组合
    # 与正常组合共用同一保留/删除计划：替代即保留项，剩余历史照常清理。
    currents = {}
    keepers = {}
    verified = set()
    for row in rows:
        combo = (row["platform"], row["package"])
        tag = row["tag"]
        current = next(((release, key) for release, key in indexed.get(combo, [])
                        if release["tag_name"] == tag), None)
        if current is not None:
            currents[combo] = current
            continue
        receipt_key = ReleaseKey(row["platform"], row["package"],
                                 row["version"], row["release"], "new",
                                 families.get(row["platform"], "rpm"))
        replacement = _newest(indexed, combo)
        if replacement is None or not newer_release(replacement[1], receipt_key):
            raise ValueError("published release not found without a newer verified "
                             "replacement: " + tag)
        verify_release(repo, replacement[0], replacement[1])
        verified.add(replacement[0]["id"])
        keepers[combo] = replacement
        print("Receipt %s 已被保留策略删除；替代 %s 校验通过，按 superseded 重入"
              % (tag, replacement[0]["tag_name"]))
    # 阶段一：先验证后删除；任何校验失败都在删除前中止。
    for combo, (current, ckey) in currents.items():
        verify_release(repo, current, ckey)
        keeper, kkey = current, ckey
        for release, key in indexed[combo]:
            if newer_release(key, kkey):
                keeper, kkey = release, key
        if keeper["id"] != current["id"]:
            verify_release(repo, keeper, kkey)
        verified.add(keeper["id"])
        keepers[combo] = (keeper, kkey)
        print("Keep Release " + keeper["tag_name"] + " (%s/%s)" % combo)
    deletable_merged = []
    if tuple(p for p in MERGED_PLATFORMS if (p, "openssh") in combos) == MERGED_PLATFORMS:
        for release, key in merged:
            for platform in MERGED_PLATFORMS:
                # 比较按旧约定还原的 R.<platform>：2.el7~rc1 不满足 >= 2.el7。
                effective = ReleaseKey("all", "openssh", key.version,
                                       key.release + "." + platform, "legacy_merged", "rpm")
                replacement = _newest(indexed, (platform, "openssh"), fmt="new")
                if replacement is None or newer_release(effective, replacement[1]):
                    break
                if replacement[0]["id"] not in verified:
                    verify_release(repo, replacement[0], replacement[1])
                    verified.add(replacement[0]["id"])
            else:
                deletable_merged.append(release)
                continue
            print("Keep Release " + release["tag_name"] + " (merged fallback)")
    # 阶段二：删除同组合非保留项与已满足双平台替代条件的合并 Release。
    for combo, (keeper, _) in keepers.items():
        for release, _ in indexed[combo]:
            if release["id"] == keeper["id"]:
                continue
            _delete(repo, release, dry_run)
    for release in deletable_merged:
        _delete(repo, release, dry_run)


def _delete(repo, release, dry_run):
    print(("Would delete Release " if dry_run else "Delete Release ") + release["tag_name"])
    if not dry_run:
        # 按不可变 Release ID 删除；Git tag 刻意保留。
        github("api", "--method", "DELETE", "repos/%s/releases/%s" % (repo, release["id"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="verify and show the cleanup without deleting")
    parser.add_argument("receipts", nargs="+",
                        help="published receipt JSON files from this run")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        parser.error("invalid repository: " + args.repo)
    try:
        config = project_config.load_config()
        upstreams = {package: upstream for package, upstream
                     in config["upstreams"].items() if upstream["enabled"]}
        platforms = sorted(config["platforms"])
        families = {pid: cfg["family"] for pid, cfg in config["platforms"].items()}
        combos = {(target["platform"], target["package"])
                  for target in project_config.iter_targets(config)}
        prune(args.repo, args.receipts, platforms, upstreams, combos, families, args.dry_run)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, rpm.error) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
