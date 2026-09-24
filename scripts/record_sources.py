#!/usr/bin/env python3
"""Merge successful publication receipts into the tracked source RPM state."""

import json
import sys


def main(state_file, receipts):
    with open(state_file, encoding="utf-8") as fh:
        state = json.load(fh)
    for receipt in receipts:
        with open(receipt, encoding="utf-8") as fh:
            row = json.load(fh)
        state.setdefault(row["el"], {})[row["package"]] = row["checksum"]
    with open(state_file, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
