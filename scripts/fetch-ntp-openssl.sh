#!/usr/bin/env bash
# EL7 NTP needs OpenSSL >= 1.1; use the same pinned source as OpenSSH.
set -euo pipefail
SRC="${1:-.}"
version="$(sed -n 's/^%global ntp_ssl_ver[[:space:]]\+//p' "$SRC/spec/ntp/el7.spec")"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'invalid OpenSSL version' >&2; exit 2; }
archive="openssl-$version.tar.gz"
checksum="$(sed -n "s/^$archive: sha256://p" "$SRC/certs/checksums.yaml")"
[[ "$checksum" =~ ^[0-9a-f]{64}$ ]] || { echo "missing pinned checksum: $archive" >&2; exit 2; }
sources="$SRC/.rpmbuild/upstream-ntp-el7/SOURCES"
mkdir -p "$sources"
if [ ! -s "$sources/$archive" ]; then
  curl -fL --retry 3 --connect-timeout 20 \
    -o "$sources/$archive" \
    "https://github.com/openssl/openssl/releases/download/openssl-$version/$archive"
fi
echo "$checksum  $sources/$archive" | sha256sum -c -
