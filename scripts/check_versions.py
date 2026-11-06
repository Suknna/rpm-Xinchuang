#!/usr/bin/env python3
"""Find newer upstream releases for enabled RPM components via Anitya."""

import argparse
import json
import os
import re
import urllib.parse
import urllib.request

# Pin project IDs: Anitya has unrelated projects named sudo and ntp.
PROJECTS = {
    "openssh": ("OpenSSH", 2565, r"\d+\.\d+p\d+", "https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-{version}.tar.gz"),
    "chrony": ("chrony", 8810, r"\d+(?:\.\d+)+", "https://chrony-project.org/releases/chrony-{version}.tar.gz"),
    # Temporarily paused: exclude Vim from scheduled, forced and retry builds.
    # "vim": ("vim", 5092, r"\d+(?:\.\d+)+", "https://github.com/vim/vim/archive/refs/tags/v{version}.tar.gz"),
    "bash": ("bash", 166, r"\d+(?:\.\d+)+", "https://ftp.gnu.org/gnu/bash/bash-{version}.tar.gz"),
    "sudo": ("sudo", 4906, r"\d+(?:\.\d+)+p\d+", "https://www.sudo.ws/dist/sudo-{version}.tar.gz"),
    "ntp": ("ntp", 9025, r"\d+(?:\.\d+)+p\d+", "https://downloads.nwtime.org/ntp/ntp-{version}.tar.gz"),
    "telnet": ("inetutils", 13805, r"\d+(?:\.\d+)+", "https://ftp.gnu.org/gnu/inetutils/inetutils-{version}.tar.gz"),
}
API = "https://release-monitoring.org/api/v2/projects/?name="
PLATFORMS = ("el7", "el8", "centos7")
SSH_PLATFORMS = ("centos7", "ubuntu2204")


def platform_openssh(version, platform):
    return {"package": "openssh", "el": platform, "version": version,
            "url": PROJECTS["openssh"][3].format(version=version)}


def centos_openssh(version):
    return {"package": "openssh", "el": "centos7", "version": version,
            "url": PROJECTS["openssh"][3].format(version=version)}


def latest(package, fetch=None):
    """Read stable releases for the exact upstream project, not a name collision."""
    name, project_id, pattern, _ = PROJECTS[package]
    url = API + urllib.parse.quote(name)
    if fetch is None:
        def fetch(url):
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.load(response)
    projects = fetch(url)["items"]
    project = next((item for item in projects if item["id"] == project_id), None)
    if project is None:
        raise ValueError("Anitya project missing: %s (%s)" % (name, project_id))
    versions = project["stable_versions"]
    if not versions or not re.fullmatch(pattern, versions[0]):
        raise ValueError("invalid stable version for %s: %r" % (package, versions[:1]))
    return versions


def detect(state, get_versions=latest, force=False):
    """Build only when upstream is ahead of a platform's published version."""
    matrix = []
    openssh = get_versions("openssh")
    ssh_update = openssh[0] if is_newer(openssh, state["openssh"]) else ""
    for platform in SSH_PLATFORMS:
        if is_newer(openssh, state.get("openssh_" + platform)):
            matrix.append(platform_openssh(openssh[0], platform))
    for package, (_, _, _, template) in PROJECTS.items():
        if package == "openssh":
            continue
        versions = get_versions(package)
        version = versions[0]
        for el in PLATFORMS:
            if force or is_newer(versions, state[package].get(el)):
                matrix.append({"package": package, "el": el, "version": version,
                               "url": template.format(version=version)})
    return ssh_update, matrix


def is_newer(versions, current):
    # Anitya orders stable_versions newest-first. Unknown/absent baselines
    # (e.g. an EL8 package never published here) bootstrap the latest release.
    if current is None:
        return True
    def parts(version):
        return tuple((0, int(part)) if part.isdigit() else (1, part)
                     for part in re.findall(r"\d+|[A-Za-z]+", version))
    return parts(versions[0]) > parts(current)


def repair_pam_matrix(state, sudo_spec="spec/sudo/el8.spec"):
    """Rebuild only the affected SSH and EL8 sudo packages, without Anitya."""
    with open(sudo_spec, encoding="utf-8") as fh:
        match = re.search(r"^Version:\s*(\S+)", fh.read(), re.MULTILINE)
    if match is None or not re.fullmatch(PROJECTS["sudo"][2], match.group(1)):
        raise ValueError("invalid sudo version in " + str(sudo_spec))
    version = match.group(1)
    return state["openssh"], [centos_openssh(state["openssh"]), {
        "package": "sudo", "el": "el8", "version": version,
        "url": PROJECTS["sudo"][3].format(version=version),
    }]


def retry_component_matrix(selection):
    """Retry exactly one pinned upstream component on all platforms."""
    package, sep, version = selection.partition(":")
    if not sep or package not in PROJECTS or package == "openssh":
        raise ValueError("invalid retry component: " + selection)
    pattern, template = PROJECTS[package][2:]
    if not re.fullmatch(pattern, version):
        raise ValueError("invalid retry version: " + selection)
    return "", [{"package": package, "el": el, "version": version,
                 "url": template.format(version=version)} for el in PLATFORMS]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-file", default="version.json")
    parser.add_argument("--output", default=os.environ.get("GITHUB_OUTPUT", ""))
    parser.add_argument("--force", action="store_true", help="rebuild the current upstream release")
    parser.add_argument("--repair-pam", action="store_true", help="rebuild SSH and EL8 sudo PAM repairs only")
    parser.add_argument("--retry-component", help="retry one component at a pinned version (e.g. chrony:4.9)")
    parser.add_argument("--sudo-spec", default="spec/sudo/el8.spec")
    parser.add_argument("--openssh-version", default=os.environ.get("FORCE_VERSION", ""),
                        help="build a pinned OpenSSH version on all platforms")
    args = parser.parse_args()
    if sum((args.repair_pam, args.force, bool(args.retry_component))) > 1:
        parser.error("--repair-pam, --force and --retry-component cannot be combined")
    if args.openssh_version:
        if args.repair_pam or args.retry_component:
            parser.error("--openssh-version cannot be combined with --repair-pam or --retry-component")
        if not re.fullmatch(PROJECTS["openssh"][2], args.openssh_version):
            parser.error("invalid OpenSSH version: " + args.openssh_version)
    with open(args.version_file, encoding="utf-8") as fh:
        state = json.load(fh)
    if args.retry_component:
        ssh, matrix = retry_component_matrix(args.retry_component)
    elif args.repair_pam:
        ssh, matrix = repair_pam_matrix(state, args.sudo_spec)
    else:
        ssh, matrix = detect(state, force=args.force)
    if args.openssh_version:
        ssh = args.openssh_version
        matrix = [row for row in matrix if row["package"] != "openssh"]
        matrix.extend(platform_openssh(ssh, platform) for platform in SSH_PLATFORMS)
    print("OpenSSH update:", ssh or "none")
    print("Matrix updates:", ", ".join(p["package"] + "/" + p["el"] for p in matrix) or "none")
    if args.output:
        with open(args.output, "a", encoding="utf-8") as fh:
            fh.write("new_version=" + ssh + "\n")
            fh.write("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")) + "\n")
            fh.write("has_updates=" + str(bool(matrix)).lower() + "\n")
    return ssh, matrix


if __name__ == "__main__":
    main()
