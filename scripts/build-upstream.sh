#!/usr/bin/env bash
# Build an upstream source archive with the packaging spec maintained in this repo.
# 容器内执行；由 scripts/package.sh 注入环境变量（PACKAGING_EL/SPEC_PATH/
# ASSETS_PATH/AUX_SOURCE/DIST_DIR）。包与平台的合法组合由 project_config 的
# platform.yaml 校验，这里不再维护包/平台白名单；辅助源编号来自 aux_source 配置。
set -euo pipefail

PKG="${1:?usage: build-upstream.sh <package> <platform> <version> <https-source-url>}"
PLATFORM="${2:?missing platform}"
VER="${3:?missing version}"
URL="${4:?missing source URL}"
SRC="${SRC_DIR:-/src}"
: "${PACKAGING_EL:?PACKAGING_EL missing (invoke via scripts/package.sh)}"
: "${SPEC_PATH:?SPEC_PATH missing (invoke via scripts/package.sh)}"
: "${DIST_DIR:?DIST_DIR missing (invoke via scripts/package.sh)}"
# Vim 构建保持暂停：即便 platform.yaml 误启用也在此硬性拦截。
[ "$PKG" = vim ] && { echo "Vim builds are temporarily disabled" >&2; exit 2; }
[[ "$VER" =~ ^[0-9][A-Za-z0-9._+~-]*$ ]] || exit 2
[[ "$URL" == https://* && "$URL" != *..* ]] || exit 2

# shellcheck source=scripts/repos-common.sh
source "$SRC/scripts/repos-common.sh"
"configure_repos_$PACKAGING_EL"
if [ "$PACKAGING_EL" = el7 ]; then
  yum -y -q install rpm-build yum-utils curl cpio gcc gcc-c++ make tar gzip redhat-rpm-config
else
  dnf -y -q install rpm-build dnf-plugins-core curl cpio gcc gcc-c++ make tar gzip redhat-rpm-config
fi

# 构建缓存平台优先：.rpmbuild/<platform>/<package>。
TOP="$SRC/.rpmbuild/$PLATFORM/$PKG"
OUT="$SRC/$DIST_DIR"
SOURCE_SPEC="$SRC/$SPEC_PATH"
test -f "$SOURCE_SPEC"
mkdir -p "$TOP"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} "$OUT"
# Each platform edits its own copy; CentOS 7 must not change the shared EL7 spec.
SPEC="$TOP/SPECS/$PKG.spec"
cp "$SOURCE_SPEC" "$SPEC"
if [ -n "${ASSETS_PATH:-}" ]; then
  cp -a "$SRC/$ASSETS_PATH/." "$TOP/SOURCES/"
fi
ARCHIVE="${URL##*/}"
if [ "${BUILD_SOURCE_CACHE:-0}" != 1 ] || [ ! -s "$TOP/SOURCES/$ARCHIVE" ]; then
  curl -fL --retry 3 --connect-timeout 20 -o "$TOP/SOURCES/$ARCHIVE" "$URL"
fi
sha256sum "$TOP/SOURCES/$ARCHIVE" | tee "$OUT/SOURCE-SHA256SUM"

# These distro spec sources are required by %prep but were previously only
# available in a developer's cached build tree. Fetch and pin them for CI;
# the source number comes from platform.yaml (aux_source), not from this script.
if [ -n "${AUX_SOURCE:-}" ]; then
  auxiliary_url="$(rpmspec -P --define "dist .$PLATFORM" "$SPEC" | sed -n "s/^Source${AUX_SOURCE}:[[:space:]]*//p")"
  [[ "$auxiliary_url" == https://* ]] || { echo "invalid auxiliary source URL: $auxiliary_url" >&2; exit 1; }
  auxiliary_file="${auxiliary_url##*/}"
  expected_sha="$(awk -v name="$auxiliary_file" '$1 == name ":" {sub(/^sha256:/, "", $2); print $2}' "$SRC/certs/checksums.yaml")"
  [ -n "$expected_sha" ] || { echo "missing pinned SHA256: $auxiliary_file" >&2; exit 1; }
  if [ "${BUILD_SOURCE_CACHE:-0}" != 1 ] ||
     ! echo "$expected_sha  $TOP/SOURCES/$auxiliary_file" | sha256sum -c --quiet >/dev/null 2>&1; then
    curl -fL --retry 3 --connect-timeout 20 -o "$TOP/SOURCES/$auxiliary_file" "$auxiliary_url"
  fi
  echo "$expected_sha  $TOP/SOURCES/$auxiliary_file" | sha256sum -c -
fi

sed -Ei "s/^Version:[[:space:]]+.*/Version: $VER/" "$SPEC"
if [ "$PACKAGING_EL" = el7 ]; then
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
rpmbuild -bb --define "_topdir $TOP" --define "dist .$PLATFORM" "$SPEC"
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
# 构建用 spec 副本留档（版本已替换；源 spec 不变）。
cp "$SPEC" "$OUT/build.spec"
(cd "$OUT" && sha256sum ./*.rpm > SHA256SUMS && sha256sum -c SHA256SUMS)
