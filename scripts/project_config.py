#!/usr/bin/env python3
"""平台与包构建配置的单一来源（宿主机解析；构建容器内没有 python3/PyYAML）。

平台声明在 platforms/<id>/platform.yaml（包归属平台），共享上游注册在
packaging/upstreams.yaml。宿主机用本模块解析后，通过 `docker -e`（见 shell
子命令与 target_env()）把目标契约传给容器内脚本。

接口契约（供构建/发布脚本 import）：
  load_config(root=ROOT) -> {"root", "platforms", "upstreams"}
  iter_targets(config)   -> 迭代全部启用组合的扁平 target dict
  get_target(platform, package, root=ROOT) -> 扁平 target dict
  load_upstreams(root=ROOT) -> {package: {name, anitya_id, version_pattern,
                                          source_url, enabled}}
target 字段：platform, package, kind（openssh-rpm / upstream-rpm / openssh-deb 三种之一；
可显式声明或缺省按包名派生，声明必须与 family 及包名角色一致。不支持其余组合：
构建链按字面包名 openssh 分发，别名包不受支持）, family, el, repos, image,
spec, assets, packaging, aux_source, pre_build, dist_dir。
所有路径相对仓库根（POSIX 风格，禁止绝对路径与 `..`）；不适用的路径/数值字段
一律为空字符串；pre_build 是宿主机构建前置钩子名（如 ntp-openssl），空表示无。
平台目录名、packages/upstreams 键、el/repos、pre_build 必须是安全标识
[a-z0-9][a-z0-9_-]*（可直接用作 Release tag 与 shell 片段，dist 拼接不会越界）。
所有非法输入（未知平台/包、路径越界、重复键、浮动镜像、空启用集合等）抛
ConfigError（ValueError 子类）。
"""

import argparse
import json
import re
import shlex
import sys
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS_DIR = "platforms"
UPSTREAMS_FILE = "packaging/upstreams.yaml"
FAMILIES = ("rpm", "deb")

# 镜像必须 digest 固定（name@sha256:<64位十六进制>），禁止浮动 tag。
_IMAGE_RE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
# 安全标识：平台目录名、packages/upstreams 键、el/repos、pre_build 钩子名。
_SAFE_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")
# 仅支持的三种 kind；别名包或第四种组合（如通用 upstream-deb）一律拒绝。
KINDS = ("openssh-rpm", "upstream-rpm", "openssh-deb")
_PLATFORM_KEYS = {"image", "family", "el", "repos", "packages"}
_PACKAGE_KEYS = {"enabled", "kind", "spec", "assets", "packaging", "aux_source", "pre_build"}
_UPSTREAM_KEYS = {"name", "anitya_id", "version_pattern", "source_url", "enabled"}

# 环境变量契约：宿主机解析后 docker -e 传入容器；缺省字段输出空字符串。
ENV_FIELDS = (
    ("BUILD_PLATFORM", "platform"),
    ("PACKAGE", "package"),
    ("PACKAGE_KIND", "kind"),
    ("PACKAGE_FAMILY", "family"),
    ("BUILD_IMAGE", "image"),
    ("PACKAGING_EL", "el"),
    ("SPEC_PATH", "spec"),
    ("ASSETS_PATH", "assets"),
    ("PACKAGING_PATH", "packaging"),
    ("AUX_SOURCE", "aux_source"),
    ("PRE_BUILD", "pre_build"),
    ("DIST_DIR", "dist_dir"),
)


class ConfigError(ValueError):
    """配置缺失、越界或自相矛盾；消息面向仓库维护者，可直接打印。"""


class _UniqueKeyLoader(yaml.SafeLoader):
    """拒绝重复键的 YAML 加载器（PyYAML 默认静默取后者，会掩盖配置错误）。"""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                hash(key)
            except TypeError as exc:
                raise ConfigError(f"unhashable key at line {key_node.start_mark.line + 1}") from exc
            if key in seen:
                raise ConfigError(
                    f"duplicate key {key!r} in {node.start_mark.name} "
                    f"at line {key_node.start_mark.line + 1}")
            seen.add(key)
        return super().construct_mapping(node, deep)


def _load_yaml(path):
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.load(fh, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def _check_keys(data, allowed, where):
    # 先拦截非字符串键，避免与未知键混合后 sorted 对异构类型崩溃。
    non_string = [key for key in data if not isinstance(key, str)]
    if non_string:
        raise ConfigError(f"{where}: keys must be strings, got: "
                          + ", ".join(repr(key) for key in non_string))
    unknown = sorted(key for key in data if key not in allowed)
    if unknown:
        raise ConfigError(f"{where}: unknown keys: {', '.join(unknown)}")


def _relpath(value, what, where):
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: {what} must be a non-empty repo-relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "\\" in value:
        raise ConfigError(f"{where}: {what} escapes the repository root: {value!r}")
    return pure.as_posix()


def _optional_path(entry, key, where):
    value = entry.get(key)
    return "" if value is None else _relpath(value, key, where)


def _safe_id(value, what, where):
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise ConfigError(
            f"{where}: {what} must match [a-z0-9][a-z0-9_-]*, got {value!r}")
    return value


def _enabled(entry, where):
    enabled = entry.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError(f"{where}: enabled must be a boolean, got {enabled!r}")
    return enabled


def _validate_platform(name, data, where):
    """结构校验单个平台配置；不检查文件存在性（延迟到 get_target）。"""
    _check_keys(data, _PLATFORM_KEYS, where)
    image = data.get("image")
    if not isinstance(image, str) or not _IMAGE_RE.fullmatch(image):
        raise ConfigError(f"{where}: image must be digest-pinned (name@sha256:<64 hex>), got {image!r}")
    family = data.get("family")
    if family not in FAMILIES:
        raise ConfigError(f"{where}: family must be one of {'|'.join(FAMILIES)}, got {family!r}")
    el = data.get("el", "")
    repos = data.get("repos", el)
    for label, value in (("el", el), ("repos", repos)):
        if not isinstance(value, str):
            raise ConfigError(f"{where}: {label} must be a string, got {value!r}")
        if value:
            _safe_id(value, label, where)
    if family == "rpm" and not el:
        raise ConfigError(f"{where}: rpm platform requires 'el' (e.g. el7)")
    packages = data.get("packages")
    if not isinstance(packages, dict) or not packages:
        raise ConfigError(f"{where}: packages must be a non-empty mapping")
    validated = {}
    for package, entry in packages.items():
        pkg_where = f"{where}: packages.{package}"
        if not isinstance(entry, dict):
            raise ConfigError(f"{pkg_where}: must be a mapping")
        _check_keys(entry, _PACKAGE_KEYS, pkg_where)
        _safe_id(package, "package name", pkg_where)
        kind = entry.get("kind")
        if kind is not None and (not isinstance(kind, str) or kind not in KINDS):
            raise ConfigError(
                f"{pkg_where}: kind must be one of {'|'.join(KINDS)}, got {kind!r}")
        expected_kind = ("openssh-" if package == "openssh" else "upstream-") + family
        if kind is None:
            kind = expected_kind
        elif kind != expected_kind:
            raise ConfigError(
                f"{pkg_where}: kind {kind!r} does not match package {package!r} "
                f"on family {family!r} (expected {expected_kind!r})")
        spec = _optional_path(entry, "spec", pkg_where)
        if family == "rpm" and not spec:
            raise ConfigError(f"{pkg_where}: rpm package requires 'spec'")
        if family == "deb" and not entry.get("packaging"):
            raise ConfigError(f"{pkg_where}: deb package requires 'packaging'")
        if family == "deb" and package != "openssh":
            raise ConfigError(f"{pkg_where}: only openssh is packaged as deb")
        aux_source = entry.get("aux_source")
        if aux_source is not None and (isinstance(aux_source, bool) or not isinstance(aux_source, int)):
            raise ConfigError(f"{pkg_where}: aux_source must be an integer, got {aux_source!r}")
        pre_build = entry.get("pre_build")
        if pre_build is not None and (
                not isinstance(pre_build, str) or not _SAFE_ID_RE.fullmatch(pre_build)):
            raise ConfigError(f"{pkg_where}: pre_build must be a hook name like ntp-openssl, got {pre_build!r}")
        validated[package] = {
            "enabled": _enabled(entry, pkg_where),
            "kind": kind,
            "spec": spec,
            "assets": _optional_path(entry, "assets", pkg_where),
            "packaging": _optional_path(entry, "packaging", pkg_where),
            "aux_source": aux_source,
            "pre_build": pre_build or "",
        }
    if not any(item["enabled"] for item in validated.values()):
        raise ConfigError(f"{where}: no enabled packages")
    return {
        "image": image,
        "family": family,
        "el": el,
        "repos": repos,
        "packages": validated,
    }


def _load_platforms(root):
    platforms_dir = root / PLATFORMS_DIR
    if not platforms_dir.is_dir():
        raise ConfigError(f"missing directory: {PLATFORMS_DIR}/")
    platforms = {}
    for source in sorted(platforms_dir.glob("*/platform.yaml")):
        name = _safe_id(source.parent.name, "platform id", str(source))
        platforms[name] = _validate_platform(name, _load_yaml(source), str(source))
    if not platforms:
        raise ConfigError(f"no platform.yaml found under {PLATFORMS_DIR}/")
    return platforms


def load_config(root=ROOT):
    """加载并校验全部配置：{"root", "platforms": {id: 平台配置}, "upstreams"}。"""
    root = Path(root)
    return {
        "root": root,
        "platforms": _load_platforms(root),
        "upstreams": load_upstreams(root),
    }


def iter_targets(config):
    """按 (platform, package) 排序迭代全部启用组合的扁平 target dict。"""
    if not isinstance(config, dict) or not isinstance(config.get("platforms"), dict):
        raise ConfigError("iter_targets expects the dict returned by load_config()")
    root = config.get("root", ROOT)
    platforms = config["platforms"]
    for platform in sorted(platforms):
        packages = platforms[platform]["packages"]
        for package in sorted(packages):
            if packages[package]["enabled"]:
                yield _build_target(platforms[platform], platform, package, root)


def get_target(platform, package, root=ROOT):
    """解析一个构建目标；未知目标、越界或缺失文件都视为配置错误。"""
    platforms = load_config(root)["platforms"]
    if platform not in platforms:
        raise ConfigError(
            f"unknown platform {platform!r} (have: {', '.join(sorted(platforms))})")
    return _build_target(platforms[platform], platform, package, root)


def _build_target(platform_cfg, platform, package, root):
    packages = platform_cfg["packages"]
    if package not in packages:
        raise ConfigError(
            f"unknown package {platform}/{package} (have: {', '.join(sorted(packages))})")
    family = platform_cfg["family"]
    entry = packages[package]
    kind = entry["kind"]
    root = Path(root)
    spec = entry["spec"]
    if spec and not (root / spec).is_file():
        raise ConfigError(f"{platform}/{package}: spec not found: {spec}")
    # assets 缺省取 spec 同目录的 assets/；该目录不存在则视为无素材。
    assets = entry["assets"]
    if not assets and spec:
        default = (PurePosixPath(spec).parent / "assets").as_posix()
        assets = default if (root / default).is_dir() else ""
    if assets and not (root / assets).is_dir():
        raise ConfigError(f"{platform}/{package}: assets not found: {assets}")
    packaging = entry["packaging"]
    if packaging and not (root / packaging).is_dir():
        raise ConfigError(f"{platform}/{package}: packaging not found: {packaging}")
    aux_source = entry["aux_source"]
    return {
        "platform": platform,
        "package": package,
        "kind": kind,
        "family": family,
        "el": platform_cfg["el"],
        "repos": platform_cfg["repos"],
        "image": platform_cfg["image"],
        "spec": spec,
        "assets": assets,
        "packaging": packaging,
        "aux_source": "" if aux_source is None else str(aux_source),
        "pre_build": entry["pre_build"],
        "dist_dir": f"dist/{platform}/{package}",
    }


def load_upstreams(root=ROOT):
    """读取共享上游注册表，返回 {package: 上游字段字典}；vim 等暂停项 enabled=False。"""
    source = Path(root) / UPSTREAMS_FILE
    if not source.is_file():
        raise ConfigError(f"missing upstream registry: {UPSTREAMS_FILE}")
    data = _load_yaml(source)
    _check_keys(data, {"projects"}, str(source))
    projects = data.get("projects")
    if not isinstance(projects, dict) or not projects:
        raise ConfigError(f"{source}: 'projects' must be a non-empty mapping")
    upstreams = {}
    for package, entry in projects.items():
        where = f"{source}: projects.{package}"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: must be a mapping")
        _check_keys(entry, _UPSTREAM_KEYS, where)
        _safe_id(package, "upstream name", where)
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"{where}: name must be a non-empty string")
        anitya_id = entry.get("anitya_id")
        if isinstance(anitya_id, bool) or not isinstance(anitya_id, int):
            raise ConfigError(f"{where}: anitya_id must be an integer, got {anitya_id!r}")
        pattern = entry.get("version_pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ConfigError(f"{where}: version_pattern must be a non-empty regex string")
        source_url = entry.get("source_url")
        if not isinstance(source_url, str) or "{version}" not in source_url:
            raise ConfigError(
                f"{where}: source_url must be a template containing {{version}}, got {source_url!r}")
        upstreams[package] = {
            "name": name,
            "anitya_id": anitya_id,
            "version_pattern": pattern,
            "source_url": source_url,
            "enabled": _enabled(entry, where),
        }
    return upstreams


def target_env(target):
    """把构建目标映射为环境变量契约（docker -e 传给容器脚本）。"""
    return {name: "" if target.get(field) is None else str(target[field])
            for name, field in ENV_FIELDS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip())
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("target", "print one build target as JSON"),
        ("shell", "print shell-safe KEY=value exports for the host"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("platform")
        cmd.add_argument("package")
    cmd_image = sub.add_parser("image", help="print the pinned container image for a platform")
    cmd_image.add_argument("platform")
    args = parser.parse_args(argv)
    try:
        if args.command == "target":
            print(json.dumps(get_target(args.platform, args.package), indent=2))
        elif args.command == "shell":
            for name, value in target_env(get_target(args.platform, args.package)).items():
                print(f"{name}={shlex.quote(value)}")
        else:
            config = load_config()
            if args.platform not in config["platforms"]:
                raise ConfigError(
                    f"unknown platform {args.platform!r} "
                    f"(have: {', '.join(sorted(config['platforms']))})")
            print(config["platforms"][args.platform]["image"])
    except ConfigError as exc:
        print(f"project_config: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
