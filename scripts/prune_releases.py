#!/usr/bin/env python3
"""Keep the highest RPM version/release after a successful GitHub publication."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import pathlib
import re
import subprocess
import sys

import rpm

from check_versions import PROJECTS


@dataclass(frozen=True)
class ReleaseKey:
    package: str
    el: str
    version: str
    release: str


def parse_tag(tag):
    # OpenSSH has always published both platforms together; its first tag had
    # no RPM release suffix and represented release 1.
    match = re.fullmatch(r"v(\d+\.\d+p\d+)(?:-(\d+))?", tag)
    if match:
        return ReleaseKey("openssh", "all", match[1], match[2] or "1")
    match = re.fullmatch(r"([a-z]+)-(el[78])-([^-]+)-(\d+[A-Za-z0-9._+~^]*)", tag)
    if not match:
        return None
    package, el, version, release = match.groups()
    if package not in PROJECTS or package == "openssh":
        return None
    # Historical distro sudo releases (e.g. 1.8.23) predate the pN suffix.
    pattern = r"\d+(?:\.\d+)+(?:p\d+)?" if package == "sudo" else PROJECTS[package][2]
    if (not re.fullmatch(pattern, version)
            or not re.search(r"\." + el + r"(?:[._]|$)", release)):
        return None
    return ReleaseKey(package, el, version, release)


def github(*args, text=True):
    return subprocess.run(["gh", *args], check=True, stdout=subprocess.PIPE, text=text).stdout


def verify_release(repo, release, key):
    """Require a complete, uploaded RPM set before removing any fallback."""
    tag = release["tag_name"]
    assets = {asset["name"]: asset for asset in release["assets"]}
    if len(assets) != len(release["assets"]):
        raise ValueError("duplicate release assets: " + tag)
    platforms = ("el7", "el8") if key.package == "openssh" else (key.el,)
    all_rpms = {name for name in assets if name.endswith(".rpm")}
    covered = set()
    for el in platforms:
        rpms = {name for name in all_rpms
                if re.search(r"\." + el + r"(?:[._][A-Za-z0-9]+)*\.(?:x86_64|noarch)\.rpm$", name)}
        required = ("openssh", "openssh-clients", "openssh-server") if key.package == "openssh" else (key.package,)
        for package in required:
            primary = {name for name in rpms
                       if name.startswith(package + "-" + key.version + "-") and name.endswith(".x86_64.rpm")}
            if len(primary) != 1:
                raise ValueError("missing or duplicate primary RPM: " + tag + "/" + package + "/" + el)
        if any(name.rsplit("-", 2)[1] != key.version for name in rpms):
            raise ValueError("mixed RPM versions: " + tag)
        manifest = "SHA256SUMS-" + el if key.package == "openssh" else "SHA256SUMS"
        for name in rpms | {manifest}:
            asset = assets.get(name, {})
            if asset.get("state") != "uploaded" or asset.get("size", 0) <= 0:
                raise ValueError("missing or incomplete asset: " + tag + "/" + name)
        contents = github("release", "download", tag, "--repo", repo, "--pattern", manifest, "--output", "-")
        checksums = {}
        for line in contents.splitlines():
            match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](?:\./)?([^/]+\.rpm)", line)
            if not match or match[2] in checksums:
                raise ValueError("invalid checksum manifest: " + tag + "/" + manifest)
            checksums[match[2]] = match[1].lower()
        if set(checksums) != rpms:
            raise ValueError("RPM assets do not match checksum manifest: " + tag + "/" + manifest)
        for name, checksum in checksums.items():
            digest = assets[name].get("digest")
            if not digest:
                # Older GitHub assets may not expose a server-side SHA256.
                data = github("release", "download", tag, "--repo", repo, "--pattern", name, "--output", "-", text=False)
                digest = "sha256:" + hashlib.sha256(data).hexdigest()
            if digest != "sha256:" + checksum:
                raise ValueError("RPM checksum mismatch: " + tag + "/" + name)
        covered.update(rpms)
    if covered != all_rpms:
        raise ValueError("unexpected platform in RPM assets: " + tag)


def prune(repo, tag, dry_run=False):
    current_key = parse_tag(tag)
    if current_key is None:
        raise ValueError("unsupported release tag: " + tag)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid repository: " + repo)
    # The API is not ordered by RPM version, and old releases can span pages.
    pages = json.loads(github("api", "--paginate", "--slurp", "repos/" + repo + "/releases?per_page=100"))
    candidates = []
    for page in pages:
        for release in page:
            key = parse_tag(release["tag_name"])
            if (key is not None and (key.package, key.el) == (current_key.package, current_key.el)
                    and not release["draft"] and not release["prerelease"]):
                candidates.append((release, key))
    current = next((release for release, _ in candidates if release["tag_name"] == tag), None)
    if current is None:
        raise ValueError("successful published release not found: " + tag)
    keeper, keeper_key = current, current_key
    for release, key in candidates:
        # Use RPM's own ordering for numeric releases and distro suffixes.
        if rpm.labelCompare(("0", key.version, key.release), ("0", keeper_key.version, keeper_key.release)) > 0:
            keeper, keeper_key = release, key
    verify_release(repo, current, current_key)
    if keeper["id"] != current["id"]:
        verify_release(repo, keeper, keeper_key)
    print("Keep Release " + keeper["tag_name"])
    for release, _ in candidates:
        if release["id"] == keeper["id"]:
            continue
        print(("Would delete Release " if dry_run else "Delete Release ") + release["tag_name"])
        if not dry_run:
            # Delete by immutable Release ID; Git tags are deliberately retained.
            github("api", "--method", "DELETE", "repos/%s/releases/%s" % (repo, release["id"]))
    return keeper["tag_name"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True, help="tag whose build, installation and publication succeeded")
    parser.add_argument("--output", help="GitHub Actions output file")
    parser.add_argument("--dry-run", action="store_true", help="verify and show the cleanup without deleting")
    args = parser.parse_args(argv)
    try:
        keeper = prune(args.repo, args.tag, args.dry_run)
        if args.output:
            with pathlib.Path(args.output).open("a", encoding="utf-8") as output:
                output.write("retained=" + str(keeper == args.tag).lower() + "\n")
                output.write("retained_tag=" + keeper + "\n")
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
