#!/usr/bin/env python3
"""Advance per-(platform, package) baselines in version.json from verified receipts.

凭据由 publish_release.py 产出并通过哈希锚定构建 spec / DEB 元数据。回写规则：

* version.json 是唯一回写对象（{"platforms": {<platform>: {<package>: <version>}}}），
  源 spec 永不因单平台成功而改写；原 spec 版本只是默认值，成功基线才是发布事实。
* 只认新格式；较低或同版本补发不得回退基线（版本比较与检测侧一致）。
* receipt 校验（身份 + 哈希 + 构建 spec/元数据一致性）集中在 read_receipt：
  record 与 prune 的清理前置预检共用同一实现，保证「校验不过不删除」。
* 平台独立回写：可选 --platform 限定本批凭据平台（artifact 下载 pattern 误
  带入的其他平台凭据，含前缀相似平台，写盘前拒绝）；预检全部凭据后才写盘，
  一张坏凭据 = 零写入。
* RPM 身份校验用 rpm.spec 宏展开（真实共享 spec 的 Version/Release 是
  %{ver}/2%{?dist} 形态，禁止用未展开原文比较）。
"""

import argparse
import hashlib
import json
import pathlib
import re
import sys

import rpm

import check_versions
import project_config

RPM_RELEASE_RE = re.compile(r"\d+[A-Za-z0-9._+~^]*")
DEB_RELEASE_RE = re.compile(r"\d+[A-Za-z0-9._+~^]*")


def receipt_tag(row):
    return "%s-%s-%s-%s" % (row["platform"], row["package"], row["version"], row["release"])


def published_root(receipt):
    """receipt 位于 published/receipts/，凭据树根即 published/。"""
    return pathlib.Path(receipt).resolve().parent.parent


def spec_identity(path, dist):
    """rpm 权威展开 spec 身份：真实 spec 的 Version/Release 常为宏（%{ver}/%{?dist}）。"""
    rpm.addMacro("dist", dist)
    try:
        spec = rpm.spec(str(path))
        header = spec.sourceHeader
        return header["name"], header["version"], header["release"]
    finally:
        rpm.delMacro("dist")


def verify_rpm(root, row):
    built = root / "spec" / row["platform"] / (row["package"] + ".spec")
    if hashlib.sha256(built.read_bytes()).hexdigest() != row["spec_sha256"]:
        raise ValueError("published spec checksum mismatch: " + str(built))
    # dist 后缀 = "." + 平台 id（构建统一 --define dist .<platform>，与 repos/el 无关）。
    # 平台是否声明/启用由 read_receipt 的 get_target（project_config）把关，这里不枚举平台。
    name, version, release = spec_identity(built, "." + row["platform"])
    if name != row["package"]:
        raise ValueError("built spec name mismatch: %s (%s)" % (name, built))
    if version != row["version"]:
        raise ValueError("built spec version mismatch: %s != %s (%s)"
                         % (version, row["version"], built))
    if release != row["release"]:
        raise ValueError("built spec release mismatch: %s != %s (%s)"
                         % (release, row["release"], built))


def verify_deb(root, row):
    built = root / "metadata" / (row["platform"] + "-" + row["package"] + ".json")
    if hashlib.sha256(built.read_bytes()).hexdigest() != row["metadata_sha256"]:
        raise ValueError("published metadata checksum mismatch")
    metadata = json.loads(built.read_text(encoding="utf-8"))
    if (metadata["package"] != row["package"] or metadata["platform"] != row["platform"]
            or metadata["architecture"] != "amd64" or metadata["version"] != row["version"]
            or metadata["release"] != row["release"]
            or not DEB_RELEASE_RE.fullmatch(row["release"])
            or metadata["deb_version"] != "1:" + row["version"] + "-" + row["release"]):
        raise ValueError("unexpected published Ubuntu build metadata")


def read_receipt(receipt, get_target=None):
    """完整校验一张 receipt 并返回其字段；record 与 prune 预检共用，失败即抛错。"""
    if get_target is None:
        get_target = project_config.get_target
    path = pathlib.Path(receipt)
    row = json.loads(path.read_text(encoding="utf-8"))
    for field in ("platform", "package", "version", "release", "tag"):
        if not isinstance(row.get(field), str) or not row[field]:
            raise ValueError("receipt field missing: %s (%s)" % (field, path))
    target = get_target(row["platform"], row["package"])
    if receipt_tag(row) != row["tag"]:
        raise ValueError("receipt tag does not match its fields: " + row["tag"])
    root = published_root(path)
    if target["family"] == "deb":
        verify_deb(root, row)
    else:
        verify_rpm(root, row)
    return row


def record(version_file, receipts, get_target=None, platform=None):
    path = pathlib.Path(version_file)
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state.get("platforms"), dict):
        raise ValueError("unsupported version.json format: expected {'platforms': {...}}")
    # 预检全部 receipt（身份 + 哈希 + 平台 scope）之后才动 state / 写盘：一张
    # 坏凭据 = 零写入；平台 scope 用精确字段比较，前缀相似平台绝不混淆。
    rows = []
    for receipt in receipts:
        row = read_receipt(receipt, get_target=get_target)
        if platform is not None and row["platform"] != platform:
            raise ValueError("receipt platform %r is outside platform scope %r: %s"
                             % (row["platform"], platform, receipt))
        rows.append(row)
    for row in rows:
        platforms = state["platforms"].setdefault(row["platform"], {})
        current = platforms.get(row["package"])
        if current is None or check_versions.is_newer([row["version"]], current):
            platforms[row["package"]] = row["version"]
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform",
                        help="限定本批凭据平台；其他平台（含前缀相似）的凭据写盘前拒绝")
    parser.add_argument("version_file")
    parser.add_argument("receipts", nargs="+")
    args = parser.parse_args(argv)
    try:
        record(args.version_file, args.receipts, platform=args.platform)
    except (ValueError, KeyError, OSError, rpm.error) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
