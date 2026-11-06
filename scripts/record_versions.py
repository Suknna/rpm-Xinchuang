#!/usr/bin/env python3
"""Persist only successfully installed and published upstream component builds."""

import hashlib
import json
import pathlib
import re
import shutil
import sys

from check_versions import PLATFORMS, PROJECTS, is_newer


def record(version_file, receipts, spec_root="spec"):
    path = pathlib.Path(version_file)
    versions = json.loads(path.read_text(encoding="utf-8"))
    for receipt in receipts:
        receipt = pathlib.Path(receipt)
        row = json.loads(receipt.read_text(encoding="utf-8"))
        package, el = row["package"], row["el"]
        if package == "openssh" and el == "ubuntu2204":
            built = receipt.parent.parent / "metadata" / "openssh-ubuntu2204.json"
            if hashlib.sha256(built.read_bytes()).hexdigest() != row["metadata_sha256"]:
                raise ValueError("published metadata checksum mismatch")
            metadata = json.loads(built.read_text(encoding="utf-8"))
            if (metadata["package"] != package or metadata["platform"] != el
                    or metadata["architecture"] != "amd64" or metadata["version"] != row["version"]
                    or not re.fullmatch(PROJECTS["openssh"][2], row["version"])
                    or not re.fullmatch(r"\d+ubuntu22\.04", metadata["release"])
                    or metadata["deb_version"] != "1:" + row["version"] + "-" + metadata["release"]):
                raise ValueError("unexpected published Ubuntu build metadata")
            current = versions.get("openssh_ubuntu2204")
            if is_newer([row["version"]], current):
                versions["openssh_ubuntu2204"] = row["version"]
            continue
        if (package not in PROJECTS or el not in PLATFORMS
                or (package == "openssh" and el != "centos7")):
            raise ValueError("unexpected component release receipt")
        built_spec = receipt.parent.parent / "spec" / package / (el + ".spec")
        if hashlib.sha256(built_spec.read_bytes()).hexdigest() != row["spec_sha256"]:
            raise ValueError("published spec checksum mismatch: " + str(built_spec))
        # CentOS reuses EL7/OpenSSH packaging. A successful CentOS build must
        # not advance another platform's spec or create a divergent spec copy.
        if el != "centos7":
            target = pathlib.Path(spec_root) / package / (el + ".spec")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(built_spec, target)
        if package == "openssh":
            versions["openssh_centos7"] = row["version"]
        else:
            versions[package][el] = row["version"]
    path.write_text(json.dumps(versions, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    record(sys.argv[1], sys.argv[2:])
