#!/usr/bin/env python3
"""Persist only successfully installed and published upstream component builds."""

import hashlib
import json
import pathlib
import shutil
import sys

from check_versions import PROJECTS


def record(version_file, receipts, spec_root="spec"):
    path = pathlib.Path(version_file)
    versions = json.loads(path.read_text(encoding="utf-8"))
    for receipt in receipts:
        receipt = pathlib.Path(receipt)
        row = json.loads(receipt.read_text(encoding="utf-8"))
        package, el = row["package"], row["el"]
        if package not in PROJECTS or package == "openssh" or el not in ("el7", "el8"):
            raise ValueError("unexpected component release receipt")
        built_spec = receipt.parent.parent / "spec" / package / (el + ".spec")
        if hashlib.sha256(built_spec.read_bytes()).hexdigest() != row["spec_sha256"]:
            raise ValueError("published spec checksum mismatch: " + str(built_spec))
        target = pathlib.Path(spec_root) / package / (el + ".spec")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(built_spec, target)
        versions[package][el] = row["version"]
    path.write_text(json.dumps(versions, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    record(sys.argv[1], sys.argv[2:])
