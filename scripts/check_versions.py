#!/usr/bin/env python3
"""Detect upstream updates per enabled (platform, package) target for the CI matrix.

上游注册与目标组合唯一来自 scripts/project_config.py（platforms/<id>/platform.yaml
与 packaging/upstreams.yaml），不再维护内置 PROJECTS 表。输出一个统一的矩阵
（字段为 platform 而非旧的 el），OpenSSH 的全部平台与组件一起进入矩阵。
"""

import argparse
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request

import project_config

API = "https://release-monitoring.org/api/v2/projects/?name="


def load_state(path):
    """version.json 只接受新格式；一次性迁移已随本仓库提交，无旧格式兼容层。"""
    state = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(state.get("platforms"), dict):
        raise ValueError("unsupported version.json format: expected {'platforms': {...}}")
    return state


def baseline(state, platform, package):
    """Published-version baseline; an absent entry bootstraps the latest release."""
    return state["platforms"].get(platform, {}).get(package)


def latest(package, upstream, fetch=None):
    """Read stable releases for the exact upstream project, not a name collision."""
    url = API + urllib.parse.quote(upstream["name"])

    def default_fetch(requested):
        with urllib.request.urlopen(requested, timeout=30) as response:
            return json.load(response)

    fetch = fetch or default_fetch
    projects = fetch(url)["items"]
    project = next((item for item in projects if item["id"] == upstream["anitya_id"]), None)
    if project is None:
        raise ValueError("Anitya project missing: %s (%s)"
                         % (upstream["name"], upstream["anitya_id"]))
    versions = project["stable_versions"]
    if not versions or not re.fullmatch(upstream["version_pattern"], versions[0]):
        raise ValueError("invalid stable version for %s: %r" % (package, versions[:1]))
    return versions


def is_newer(versions, current):
    # Anitya orders stable_versions newest-first. Unknown/absent baselines
    # bootstrap the latest release; equal or older baselines never rebuild.
    if current is None:
        return True
    def parts(version):
        return tuple((0, int(part)) if part.isdigit() else (1, part)
                     for part in re.findall(r"\d+|[A-Za-z]+", version))
    return parts(versions[0]) > parts(current)


def matrix_row(target, version, upstream):
    return {"platform": target["platform"], "package": target["package"],
            "version": version, "url": upstream["source_url"].format(version=version)}


def matrix_rows(state, targets, upstreams, get_versions, force=False):
    """One row per (platform, package) whose upstream is ahead of its baseline."""
    rows = []
    for target in sorted(targets, key=lambda item: (item["package"], item["platform"])):
        package, platform = target["package"], target["platform"]
        upstream = upstreams[package]
        versions = get_versions(package)
        # --force rebuilds the current upstream release of enabled components;
        # OpenSSH follows real updates or an explicit --openssh-version pin.
        if (force and package != "openssh") or is_newer(versions, baseline(state, platform, package)):
            rows.append(matrix_row(target, versions[0], upstream))
    return rows


def parse_selection(selection, targets):
    """Parse 'pkg', 'pkg/platform', 'pkg@ver', 'pkg/platform@ver' (comma separated)."""
    selected = []
    for entry in selection.split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, _, pinned = entry.partition("@")
        parts = name.split("/")
        if len(parts) > 2 or not parts[0]:
            raise ValueError("invalid target selection: " + entry)
        platform = parts[1] if len(parts) == 2 else None
        matched = [target for target in targets
                   if target["package"] == parts[0]
                   and (platform is None or target["platform"] == platform)]
        if not matched:
            raise ValueError("unknown target: " + entry)
        selected.extend({"platform": target["platform"], "package": target["package"],
                         "pin": pinned or None} for target in matched)
    return selected


def selection_rows(state, selected, upstreams, get_versions):
    """Manual selection; version precedence: @pin > published baseline > upstream latest."""
    rows = {}
    for item in selected:
        upstream = upstreams[item["package"]]
        version = (item["pin"] or baseline(state, item["platform"], item["package"])
                   or get_versions(item["package"])[0])
        rows[(item["platform"], item["package"])] = matrix_row(item, version, upstream)
    # 与 matrix_rows 同序：先包名后平台，输出稳定可读。
    return [rows[key] for key in sorted(rows, key=lambda item: (item[1], item[0]))]


def apply_openssh_pin(rows, targets, upstreams, version):
    """Replace detected OpenSSH rows with a pinned version on every OpenSSH target."""
    if not re.fullmatch(upstreams["openssh"]["version_pattern"], version):
        raise ValueError("invalid OpenSSH version: " + version)
    pinned = [matrix_row(target, version, upstreams["openssh"])
              for target in targets if target["package"] == "openssh"]
    rows = [row for row in rows if row["package"] != "openssh"]
    rows.extend(pinned)
    return sorted(rows, key=lambda row: (row["package"], row["platform"]))


def detect(state, targets, upstreams, get_versions, force=False, selection=None,
           openssh_version=""):
    if selection is not None:
        rows = selection_rows(state, selection, upstreams, get_versions)
    else:
        rows = matrix_rows(state, targets, upstreams, get_versions, force=force)
    if openssh_version:
        rows = apply_openssh_pin(rows, targets, upstreams, openssh_version)
    return rows


def registries(config_root):
    """Enabled upstreams and enabled (platform, package) targets from the config."""
    config = project_config.load_config(config_root)
    upstreams = {package: upstream for package, upstream in config["upstreams"].items()
                 if upstream["enabled"]}
    targets = list(project_config.iter_targets(config))
    unregistered = sorted({target["package"] for target in targets} - set(upstreams))
    if unregistered:
        raise ValueError("targets without an enabled upstream: " + ", ".join(unregistered))
    return targets, upstreams


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-file", default="version.json")
    parser.add_argument("--config-root", default=".")
    parser.add_argument("--output", default=os.environ.get("GITHUB_OUTPUT", ""))
    parser.add_argument("--force", action="store_true",
                        help="rebuild the current upstream release of enabled components")
    parser.add_argument("--targets",
                        help="manual selection: pkg, pkg/platform, pkg@ver, pkg/platform@ver")
    parser.add_argument("--openssh-version", default=os.environ.get("FORCE_VERSION", ""),
                        help="build a pinned OpenSSH version on all OpenSSH platforms")
    args = parser.parse_args(argv)
    if args.targets and (args.force or args.openssh_version):
        parser.error("--targets cannot be combined with --force or --openssh-version")
    try:
        targets, upstreams = registries(args.config_root)
        state = load_state(args.version_file)

        def get_versions(package):
            return latest(package, upstreams[package])

        selection = parse_selection(args.targets, targets) if args.targets else None
        matrix = detect(state, targets, upstreams, get_versions, force=args.force,
                        selection=selection, openssh_version=args.openssh_version)
    except ValueError as exc:
        parser.exit(2, "error: %s\n" % exc)
    print("Matrix updates:",
          ", ".join(row["package"] + "/" + row["platform"] for row in matrix) or "none")
    if args.output:
        with open(args.output, "a", encoding="utf-8") as output:
            output.write("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")) + "\n")
            output.write("has_updates=" + str(bool(matrix)).lower() + "\n")
    return matrix


if __name__ == "__main__":
    main()
