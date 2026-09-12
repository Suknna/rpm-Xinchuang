#!/usr/bin/env python3
"""OpenSSH portable 稳定版本检测与 GitHub Release 查询。

仅依赖 Python 标准库（urllib/json/re），无第三方依赖。

子命令：
  check        对比上游镜像目录与本地 version.txt；仅当上游出现数值更高的
               稳定版本时输出 new_version，供 CI 触发构建。
  has-release  查询 GitHub Release（按 tag）是否已存在，用于发布幂等。

退出码约定：
  check        0=有更新  1=已是最新  2=网络/数据/参数错误
  has-release  0=已存在  3=不存在    2=查询错误

版本比较规则：仅接受 openssh-X.YpZ 形式的 portable 稳定发行版，
按 (X, Y, Z) 数值比较（避免 10.10p1 < 10.9p1 的字符串误判）。
上游 portable 目录中的 tar 包即为官方稳定发行版（快照不发布到该目录）。
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_LISTING_URL = "https://mirrors.aliyun.com/pub/OpenBSD/OpenSSH/portable/"

# 仅匹配稳定发行版 tar 包；排除 .asc/.diff.gz 等附属文件。
# 不用 ^$ 锚点（HTML 行内出现）；用环视保证前后边界：
#   前不可为 [词字符.+-]，后不可为 [词字符.]（排除 .tar.gz.asc 等）
_TARBALL_RE = re.compile(
    r"(?<![\w.+-])openssh-(\d+)\.(\d+)p(\d+)\.tar\.gz(?![\w.])"
)
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)p(\d+)$")

EXIT_UPDATED = 0
EXIT_UPTODATE = 1
EXIT_ERROR = 2
EXIT_NO_RELEASE = 3

# OpenSSH 官方 release 签名 key 指纹（certs/openssh-release-key.asc）
OPENSSH_RELEASE_FINGERPRINT = "7168B983815A5EEF59A4ADFD2A3F414E736060BA"


def parse_version(text):
    """解析 'X.YpZ' 为数值元组 (X, Y, Z)；非法输入返回 None。"""
    m = _VERSION_RE.match(text.strip()) if text else None
    if not m:
        return None
    return tuple(int(part) for part in m.groups())


def version_to_str(t):
    """数值元组还原为 'X.YpZ'。"""
    return "%d.%dp%d" % t


def latest_upstream_version(listing_html):
    """从镜像目录 HTML 中提取数值最高的稳定版本号；无匹配返回 None。"""
    best = None
    for match in _TARBALL_RE.finditer(listing_html or ""):
        candidate = tuple(int(part) for part in match.groups())
        if best is None or candidate > best:
            best = candidate
    return version_to_str(best) if best else None


def read_current_version(path):
    """读取 version.txt（单行 'X.YpZ'，容忍空白）；文件缺失返回 None。"""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().strip()


def check_update(listing_html, current):
    """纯函数：上游最新版本高于当前版本时返回新版本字符串，否则 None。

    current 为 None（无基线）或非法格式时视为无法比较，返回 None 并由
    调用方处理错误路径。
    """
    latest = latest_upstream_version(listing_html)
    if latest is None:
        raise ValueError("upstream listing has no recognizable openssh tarball")
    cur = parse_version(current) if current else None
    if cur is None:
        raise ValueError("current version missing or invalid: %r" % (current,))
    if parse_version(latest) > cur:
        return latest
    return None


def fetch_url(url, timeout=60, headers=None):
    """GET 一个 URL，返回 bytes；HTTP 非 200 抛 URLError/RuntimeError。"""
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError("HTTP %s for %s" % (resp.status, url))
        return resp.read()


def release_exists(repo, tag, token=None, timeout=30):
    """查询 GitHub Release 是否存在（GET /releases/tags/{tag}）。

    repo 形如 'owner/name'；token 可选（GITHUB_TOKEN 即可，只读用途）。
    """
    url = "https://api.github.com/repos/%s/releases/tags/%s" % (repo, tag)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "rpm-xinchuang-check",
    }
    if token:
        headers["Authorization"] = "Bearer %s" % token
    try:
        fetch_url(url, timeout=timeout, headers=headers)
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def write_output(path, key, value):
    """按 GitHub Actions GITHUB_OUTPUT 的 key=value 格式追加写出。"""
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("%s=%s\n" % (key, value))


def _detect_new_version(args):
    """check 子命令实现。"""
    html = fetch_url(args.url, timeout=args.timeout).decode("utf-8", "replace")
    current = read_current_version(args.version_file)
    if parse_version(current or "") is None:
        print(
            "ERROR: version file %s missing or invalid (expect single 'X.YpZ')"
            % args.version_file,
            file=sys.stderr,
        )
        return EXIT_ERROR
    try:
        new_version = check_update(html, current)
    except ValueError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    if new_version:
        print("update available: %s -> %s" % (current, new_version))
        write_output(args.output, "new_version", new_version)
        return EXIT_UPDATED
    print("already up to date: %s" % current)
    if args.output:
        # 显式置空，避免 CI 复用旧输出
        write_output(args.output, "new_version", "")
    return EXIT_UPTODATE


def _has_release(args):
    """has-release 子命令实现。"""
    try:
        exists = release_exists(
            args.repo, args.tag, token=args.token, timeout=args.timeout
        )
    except Exception as exc:  # 网络/API 错误统一按错误退出码处理
        print("ERROR: %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    if exists:
        print("release %s exists" % args.tag)
        return EXIT_UPDATED
    print("release %s does not exist" % args.tag)
    return EXIT_NO_RELEASE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="检测上游是否有更高稳定版本")
    p_check.add_argument("--url", default=DEFAULT_LISTING_URL)
    p_check.add_argument("--version-file", default="version.txt")
    p_check.add_argument(
        "--output",
        default=os.environ.get("GITHUB_OUTPUT", ""),
        help="追加写出 new_version=<v> 的文件（默认读 GITHUB_OUTPUT 环境变量）",
    )
    p_check.add_argument("--timeout", type=int, default=60)
    p_check.set_defaults(func=_detect_new_version)

    p_rel = sub.add_parser("has-release", help="查询 GitHub Release 是否存在")
    p_rel.add_argument("--repo", required=True, help="owner/name")
    p_rel.add_argument("--tag", required=True, help="release tag，如 v10.5p1")
    p_rel.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    p_rel.add_argument("--timeout", type=int, default=30)
    p_rel.set_defaults(func=_has_release)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
