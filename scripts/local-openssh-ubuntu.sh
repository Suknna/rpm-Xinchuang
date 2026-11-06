#!/usr/bin/env bash
# Native amd64 build and clean-container installation tests.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/platforms.sh
source scripts/platforms.sh
action="${1:-all}"
version="${2:-$(sed -n 's/^%global ver[[:space:]]\+//p' spec/openssh.spec)}"
case "$action" in build|test|all) ;; *) echo 'usage: local-openssh-ubuntu.sh [build|test|all] [version]' >&2; exit 2 ;; esac
docker=(docker)
docker info >/dev/null 2>&1 || docker=(sudo docker)
image="$(image_for ubuntu2204)"
if [ "$action" != test ]; then
    "${docker[@]}" run --rm --platform linux/amd64 -v "$PWD":/src -e SRC_DIR=/src "$image" \
        bash /src/scripts/build-openssh-deb.sh "$version"
fi
if [ "$action" != build ]; then
    for scenario in fresh upgrade reinstall uninstall symlink-guard; do
        "${docker[@]}" run --rm --platform linux/amd64 -v "$PWD":/src:ro -e SRC_DIR=/src "$image" \
            bash /src/scripts/test-openssh-deb.sh "$scenario" "$version"
    done
fi
