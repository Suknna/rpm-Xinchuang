#!/usr/bin/env python3
"""Check whether an OpenSSH Release tag already exists on GitHub."""

import argparse
import os
import sys
import urllib.error
import urllib.request


def release_exists(repo, tag, token=None, timeout=30):
    url = "https://api.github.com/repos/%s/releases/tags/%s" % (repo, tag)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "rpm-xinchuang-check"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("has-release")
    p.add_argument("--repo", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    p.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        exists = release_exists(args.repo, args.tag, args.token, args.timeout)
    except Exception as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    print("release %s %s" % (args.tag, "exists" if exists else "does not exist"))
    return 0 if exists else 3


if __name__ == "__main__":
    sys.exit(main())
