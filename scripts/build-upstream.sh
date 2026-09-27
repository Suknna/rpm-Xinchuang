#!/usr/bin/env bash
# Build an upstream source archive with the packaging spec maintained in this repo.
set -euo pipefail

PKG="${1:?usage: build-upstream.sh <package> <el7|el8> <version> <https-source-url>}"
EL="${2:?missing platform}"
VER="${3:?missing version}"
URL="${4:?missing source URL}"
SRC="${SRC_DIR:-/src}"
case "$PKG:$EL" in
  bash:el7|bash:el8|chrony:el7|chrony:el8|vim:el7|vim:el8|sudo:el7|sudo:el8|ntp:el7|ntp:el8|telnet:el7|telnet:el8) ;;
  *) echo "unsupported package/platform: $PKG:$EL" >&2; exit 2 ;;
esac
[[ "$VER" =~ ^[0-9][A-Za-z0-9._+~-]*$ ]] || exit 2
[[ "$URL" == https://* && "$URL" != *..* ]] || exit 2

# shellcheck source=scripts/repos-common.sh
source "$SRC/scripts/repos-common.sh"
"configure_repos_$EL"
if [ "$EL" = el7 ]; then
  yum -y -q install rpm-build yum-utils curl cpio gcc gcc-c++ make tar gzip redhat-rpm-config
else
  dnf -y -q install rpm-build dnf-plugins-core curl cpio gcc gcc-c++ make tar gzip redhat-rpm-config
fi

TOP="$SRC/.rpmbuild/upstream-$PKG-$EL"
OUT="$SRC/dist/$PKG/$EL"
SPEC="$SRC/spec/$PKG/$EL.spec"
test -f "$SPEC"
mkdir -p "$TOP"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} "$OUT"
if [ -d "$SRC/source-assets/$PKG/$EL" ]; then
  cp -a "$SRC/source-assets/$PKG/$EL/." "$TOP/SOURCES/"
fi
ARCHIVE="${URL##*/}"
if [ "${BUILD_SOURCE_CACHE:-0}" != 1 ] || [ ! -s "$TOP/SOURCES/$ARCHIVE" ]; then
  curl -fL --retry 3 --connect-timeout 20 -o "$TOP/SOURCES/$ARCHIVE" "$URL"
fi
sha256sum "$TOP/SOURCES/$ARCHIVE" | tee "$OUT/SOURCE-SHA256SUM"

sed -Ei "s/^Version:[[:space:]]+.*/Version: $VER/" "$SPEC"
if [ "$PKG" = vim ]; then
  base="${VER%.*}"
  sed -Ei "s/^%define baseversion .*/%define baseversion $base/; s/^%define patchlevel .*/%define patchlevel ${VER##*.}/; s/^%define vimdir .*/%define vimdir vim${base//./}/" "$SPEC"
fi
if [ "$EL" = el7 ]; then
  yum-builddep -y "$SPEC"
else
  if [ "$PKG" = chrony ]; then
    # UBI8 GnuTLS owns the same FIPS .hmac file as Alma's gnutls-devel.
    dnf -y -q --disablerepo='ubi-*' reinstall gnutls
  fi
  dnf -y -q builddep "$SPEC"
fi
# Reused local build trees may retain older releases; never collect stale RPMs.
rm -f "$TOP"/RPMS/{x86_64,noarch}/*.rpm
rpmbuild -bb --define "_topdir $TOP" --define "dist .$EL" "$SPEC"
shopt -s nullglob
rpms=("$TOP"/RPMS/{x86_64,noarch}/*.rpm)
[ "${#rpms[@]}" -gt 0 ] || { echo "no RPMs produced" >&2; exit 1; }
rm -f "$OUT"/*.rpm "$OUT/SHA256SUMS"
for rpmfile in "${rpms[@]}"; do
  info="$(rpm -qp --qf '%{VERSION} %{ARCH}' "$rpmfile")"
  [[ "$info" == "$VER x86_64" || "$info" == "$VER noarch" ]] || {
    echo "unexpected RPM version/arch: $rpmfile: $info" >&2; exit 1;
  }
  cp "$rpmfile" "$OUT/"
done
cp "$SPEC" "$OUT/$PKG-$EL.spec"
(cd "$OUT" && sha256sum ./*.rpm > SHA256SUMS && sha256sum -c SHA256SUMS)
