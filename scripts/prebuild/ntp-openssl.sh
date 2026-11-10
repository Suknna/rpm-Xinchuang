#!/usr/bin/env bash
# NTP EL7 家族构建所需的静态 OpenSSL 预取（pre_build 钩子 ntp-openssl 的实现）。
# 由 scripts/package.sh 在容器构建前于宿主机调用（platform.yaml 的 pre_build
# 配置触发）；版本读 SPEC_PATH 指向的 NTP spec，缓存进平台优先的构建树
# .rpmbuild/<platform>/<package>/SOURCES，与 build-upstream.sh 共用缓存。
set -euo pipefail
SRC="${1:-.}"
PLATFORM="${2:?missing platform}"
PKG="${PACKAGE:-ntp}"
: "${SPEC_PATH:?SPEC_PATH must point to the NTP spec (set by scripts/package.sh)}"
version="$(sed -n 's/^%global ntp_ssl_ver[[:space:]]\+//p' "$SRC/$SPEC_PATH" | head -1 | tr -d '[:space:]')"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'invalid OpenSSL version' >&2; exit 2; }
archive="openssl-$version.tar.gz"
checksum="$(sed -n "s/^$archive: sha256://p" "$SRC/certs/checksums.yaml")"
[[ "$checksum" =~ ^[0-9a-f]{64}$ ]] || { echo "missing pinned checksum: $archive" >&2; exit 2; }
sources="$SRC/.rpmbuild/$PLATFORM/$PKG/SOURCES"
mkdir -p "$sources"
if [ ! -s "$sources/$archive" ]; then
  curl -fL --retry 3 --connect-timeout 20 \
    -o "$sources/$archive" \
    "https://github.com/openssl/openssl/releases/download/openssl-$version/$archive"
fi
echo "$checksum  $sources/$archive" | sha256sum -c -
