#!/usr/bin/env bash
# Select the single primary binary RPM and return its path and release.
set -euo pipefail
dir="${1:?missing artifact directory}"
package="${2:?missing package}"
version="${3:?missing version}"
el="${4:?missing platform}"

# Vim's source package has no "vim" binary RPM; the editor lives in vim-enhanced.
primary="$package"
if [ "$package" = vim ]; then primary=vim-enhanced; fi
shopt -s nullglob
candidates=("$dir/$primary-$version-"*."$el".x86_64.rpm)
[ "${#candidates[@]}" = 1 ] || { echo "需要且仅需一个主 RPM: ${candidates[*]}" >&2; exit 1; }
rpmfile="${candidates[0]}"
release="${rpmfile#"$dir/$primary-$version-"}"
release="${release%.x86_64.rpm}"
printf '%s\t%s\n' "$rpmfile" "$release"
