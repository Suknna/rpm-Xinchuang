#!/usr/bin/env bash
# Run inside the same pinned UBI7/UBI8 images as OpenSSH.
set -euo pipefail

EL="${1:?usage: build-source-rpm.sh <el7|el8> <package> <url> <checksum-type> <checksum> <version> <release>}"
PKG="${2:?missing package}"
URL="${3:?missing SRPM URL}"
HASH_TYPE="${4:?missing checksum type}"
HASH="${5:?missing checksum}"
VER="${6:?missing version}"
REL="${7:?missing release}"
SRC="${SRC_DIR:-/src}"
case "$EL:$PKG" in
  el7:chrony|el7:vim|el7:bash|el7:sudo|el7:ntp|el7:telnet|el8:chrony|el8:vim|el8:bash|el8:sudo|el8:telnet) ;;
  *) echo "unsupported component/platform: $EL:$PKG" >&2; exit 2 ;;
esac
case "$HASH_TYPE:$HASH" in
  sha256:*) [[ "$HASH" =~ ^[a-fA-F0-9]{64}$ ]] || exit 2 ;;
  sha1:*) [[ "$HASH" =~ ^[a-fA-F0-9]{40}$ ]] || exit 2 ;;
  *) echo "unsupported SRPM checksum: $HASH_TYPE" >&2; exit 2 ;;
esac
[[ "$URL" == https://vault.centos.org/* || "$URL" == https://vault.almalinux.org/* ]] || exit 2

# shellcheck source=scripts/repos-common.sh
source "$SRC/scripts/repos-common.sh"
"configure_repos_$EL"
if [ "$EL" = el7 ]; then
  yum -y -q install rpm-build yum-utils curl cpio gcc gcc-c++ make glibc-devel redhat-rpm-config
  KEY="$SRC/certs/centos7-key.asc"
else
  dnf -y -q install rpm-build dnf-plugins-core curl cpio gcc gcc-c++ make glibc-devel redhat-rpm-config
  KEY="$SRC/certs/almalinux8-key.asc"
fi
rpm --import "$KEY"

TOP="$SRC/.rpmbuild/source-$PKG-$EL"
OUT="$SRC/dist/$PKG/$EL"
mkdir -p "$TOP"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} "$OUT"
SRPM="$TOP/$PKG.src.rpm"
curl -fL --retry 3 --connect-timeout 20 -o "$SRPM" "$URL"
echo "$HASH  $SRPM" | "${HASH_TYPE}sum" -c -
# The repository checksum alone does not authenticate the untrusted metadata.
rpm --checksig --verbose "$SRPM" | tee "$TOP/signature.txt"
grep -Eiq '(rsa|pgp).*: OK' "$TOP/signature.txt" || { echo "SRPM signature missing/invalid" >&2; exit 1; }
# EL7 SRPM headers sometimes retain the target arch (e.g. i686); the
# repository 'src' metadata and included spec establish that this is a source RPM.
rpm -qp --qf '%{NAME} %{VERSION} %{RELEASE}\n' "$SRPM" | \
  grep -Fx "$PKG $VER $REL"
rpm -qpl "$SRPM" | grep -Eq "(^|/)$PKG\.spec$"
rpm -ivh --define "_topdir $TOP" "$SRPM"
SPEC="$TOP/SPECS/$PKG.spec"
[ -f "$SPEC" ] || { echo "missing upstream spec: $SPEC" >&2; exit 1; }
if [ "$EL:$PKG" = el7:sudo ]; then
  # The upstream tarball preserves uid 8036 on this fixture, while the
  # regression expects the included sudoers file to be owned by root.
  # Fix only its temporary build-tree ownership; keep all tests enabled.
  grep -qx '%check' "$SPEC"
  sed -i '/^%check$/a\chown 0:0 plugins/sudoers/regress/testsudoers/test3.d/root' "$SPEC"
fi
if [ "$EL" = el7 ]; then
  yum-builddep -y "$SPEC"
else
  if [ "$PKG" = chrony ]; then
    # UBI's GnuTLS and Alma's gnutls-devel both own the FIPS .hmac file.
    # Use the signed matching Alma runtime in this disposable build container.
    dnf -y -q --disablerepo='ubi-*' reinstall gnutls
  fi
  dnf -y -q builddep "$SPEC"
fi
rpmbuild -bb --define "_topdir $TOP" --define "dist .$EL" "$SPEC"
shopt -s nullglob
rpms=("$TOP"/RPMS/{x86_64,noarch}/*.rpm)
[ "${#rpms[@]}" -gt 0 ] || { echo "no RPMs produced" >&2; exit 1; }
for rpmfile in "${rpms[@]}"; do
  info="$(rpm -qp --qf '%{VERSION} %{ARCH}' "$rpmfile")"
  [ "$info" = "$VER x86_64" ] || [ "$info" = "$VER noarch" ] || {
    echo "unexpected RPM version/arch: $rpmfile: $info" >&2; exit 1;
  }
done
# Local repeat builds must not accidentally publish stale RPMs from an older EVR.
rm -f "$OUT"/*.rpm "$OUT/SHA256SUMS"
for rpmfile in "${rpms[@]}"; do cp "$rpmfile" "$OUT/"; done
(cd "$OUT" && sha256sum ./*.rpm > SHA256SUMS && sha256sum -c SHA256SUMS)
