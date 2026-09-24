#!/usr/bin/env python3
"""Detect changed EL source RPMs and emit one Actions matrix for all components."""

import argparse
import gzip
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

PACKAGES = ("chrony", "vim", "bash", "sudo", "ntp", "telnet")
REPOS = {
    "el7": (
        "https://vault.centos.org/7.9.2009/os/Source/",
        "https://vault.centos.org/7.9.2009/updates/Source/",
        "https://vault.centos.org/7.9.2009/extras/Source/",
    ),
    "el8": (
        "https://vault.almalinux.org/8.10/BaseOS/Source/",
        "https://vault.almalinux.org/8.10/AppStream/Source/",
    ),
}
NS = {"repo": "http://linux.duke.edu/metadata/repo",
      "common": "http://linux.duke.edu/metadata/common"}


def fetch(url):
    with urllib.request.urlopen(url, timeout=90) as response:
        return response.read()


def source_packages(base, fetcher=fetch):
    """Read only source package entries, verifying repository metadata before use."""
    repomd = ET.fromstring(fetcher(base + "repodata/repomd.xml"))
    primary = next(d for d in repomd.findall("repo:data", NS)
                   if d.get("type") == "primary")
    location = primary.find("repo:location", NS).get("href")
    digest = primary.find("repo:checksum", NS)
    if not location.startswith("repodata/") or "/../" in location:
        raise ValueError("invalid metadata path")
    data = fetcher(urllib.parse.urljoin(base, location))
    if hashlib.new(digest.get("type"), data).hexdigest() != digest.text:
        raise ValueError("repository metadata checksum mismatch: " + base)
    root = ET.fromstring(gzip.decompress(data))
    for p in root.findall("common:package", NS):
        name = p.findtext("common:name", namespaces=NS)
        if name not in PACKAGES or p.get("type") != "rpm":
            continue
        if p.findtext("common:arch", namespaces=NS) != "src":
            continue
        version = p.find("common:version", NS)
        location = p.find("common:location", NS).get("href")
        checksum = p.find("common:checksum", NS)
        ver, rel = version.get("ver"), version.get("rel")
        if not all(re.fullmatch(r"[A-Za-z0-9._+~]+", value) for value in (ver, rel)):
            raise ValueError("invalid upstream RPM version or release")
        if not re.fullmatch(r"(?:Packages|SPackages)/[A-Za-z0-9._+~%-]+\.src\.rpm", location):
            raise ValueError("invalid RPM path: " + location)
        if checksum.get("type") not in ("sha256", "sha1") or not re.fullmatch(
            r"[0-9a-fA-F]{64}" if checksum.get("type") == "sha256" else r"[0-9a-fA-F]{40}",
            checksum.text or "",
        ):
            raise ValueError("invalid SRPM checksum")
        yield {
            "package": name,
            "version": ver,
            "release": rel,
            "url": urllib.parse.urljoin(base, location),
            "checksum": checksum.text,
            "checksum_type": checksum.get("type"),
            "built": int(p.find("common:time", NS).get("build")),
        }


def detect(state, packages=source_packages):
    updates = []
    for el, repos in REPOS.items():
        latest = {}
        for repo in repos:
            for pkg in packages(repo):
                if el == "el8" and pkg["package"] == "ntp":
                    continue  # RHEL 8 ships chrony instead of the retired ntp package.
                name = pkg["package"]
                if name not in latest or pkg["built"] > latest[name]["built"]:
                    latest[name] = pkg
        required = set(PACKAGES) - ({"ntp"} if el == "el8" else set())
        if set(latest) != required:
            raise ValueError("missing source RPMs for %s: %s" % (el, sorted(required - set(latest))))
        for name in sorted(latest):
            pkg = latest[name]
            pkg["el"] = el
            # Track the actual SRPM, including patched rebuilds at the same EVR.
            if state.get(el, {}).get(name) != pkg["checksum"]:
                updates.append(pkg)
    return updates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default="state/sources.json")
    parser.add_argument("--output", default=os.environ.get("GITHUB_OUTPUT", ""))
    parser.add_argument("--force", action="store_true", help="rebuild all packages")
    args = parser.parse_args()
    with open(args.state, encoding="utf-8") as fh:
        state = json.load(fh)
    updates = detect({} if args.force else state)
    matrix = json.dumps({"include": updates}, separators=(",", ":"))
    print("changed:", ", ".join(p["package"] + "/" + p["el"] for p in updates) or "none")
    if args.output:
        with open(args.output, "a", encoding="utf-8") as fh:
            fh.write("matrix=" + matrix + "\n")
            fh.write("has_updates=" + str(bool(updates)).lower() + "\n")
    else:
        print(matrix)


if __name__ == "__main__":
    main()
