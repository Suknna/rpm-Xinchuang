#!/usr/bin/env bash
# OpenSSH DEB 构建（仅在临时 Ubuntu 22.04 amd64 容器内运行）。
# 由 scripts/package.sh 注入 SPEC_PATH/PACKAGING_PATH/DIST_DIR/BUILD_PLATFORM。
set -euo pipefail
SRC="${SRC_DIR:-/src}"
# shellcheck source=/dev/null
source /etc/os-release
[ "$ID:$VERSION_ID:$(dpkg --print-architecture)" = ubuntu:22.04:amd64 ] || {
    echo 'Expected Ubuntu 22.04 amd64' >&2; exit 2;
}
: "${SPEC_PATH:?SPEC_PATH missing (invoke via scripts/package.sh)}"
: "${PACKAGING_PATH:?PACKAGING_PATH missing (invoke via scripts/package.sh)}"
: "${DIST_DIR:?DIST_DIR missing (invoke via scripts/package.sh)}"
: "${BUILD_PLATFORM:?BUILD_PLATFORM missing (invoke via scripts/package.sh)}"
# 版本/修订号宏以共享 spec 为唯一来源；源 spec 不修改，版本由参数或默认值解析。
SPEC_FILE="$SRC/$SPEC_PATH"
VER="${1:-$(sed -n 's/^%global ver[[:space:]]\+//p' "$SPEC_FILE")}"
[[ "$VER" =~ ^[0-9]+\.[0-9]+p[0-9]+$ ]] || exit 2
REL="$(sed -n 's/^%global rel \([0-9][0-9]*\).*/\1/p' "$SPEC_FILE")"
[[ "$REL" =~ ^[0-9]+$ ]] || exit 2
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends build-essential debhelper libssl-dev zlib1g-dev \
    libpam0g-dev libkrb5-dev libedit-dev pkg-config curl ca-certificates gnupg openssh-client python3
# 构建缓存平台优先：.debbuild/<platform>/<package>。
TOP="$SRC/.debbuild/$BUILD_PLATFORM/openssh"
mkdir -p "$TOP/sources"
cd "$TOP/sources"
for suffix in tar.gz tar.gz.asc; do
    curl -fSL --retry 3 --connect-timeout 20 -o "openssh-$VER.$suffix" \
        "https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-$VER.$suffix"
done
export GNUPGHOME
GNUPGHOME="$(mktemp -d)"
trap 'rm -rf "$GNUPGHOME"' EXIT
gpg --batch --import "$SRC/certs/openssh-release-key.asc"
FP="$(gpg --with-colons --fingerprint | awk -F: '/^fpr/{print $10; exit}')"
[ "$FP" = 7168B983815A5EEF59A4ADFD2A3F414E736060BA ] || exit 2
gpg --batch --verify "openssh-$VER.tar.gz.asc" "openssh-$VER.tar.gz"
rm -rf "$TOP/build"
mkdir -p "$TOP/build"
tar -xzf "openssh-$VER.tar.gz" -C "$TOP/build"
cd "$TOP/build/openssh-$VER"
cp -a "$SRC/$PACKAGING_PATH" debian
chmod +x debian/rules debian/*.postinst
# Epoch 1 is required to upgrade Ubuntu's 1:8.9p1 package with apt/dpkg.
cat > debian/changelog <<EOF
openssh (1:$VER-${REL}ubuntu22.04) jammy; urgency=medium

  * Build verified upstream OpenSSH for Ubuntu 22.04 amd64.

 -- rpm-Xinchuang maintainers <noreply@github.com>  $(LC_ALL=C date -R -r version.h)
EOF
cp LICENCE debian/copyright
printf '\n' >> debian/copyright
cat debian/packaging-copyright >> debian/copyright
# Privilege separation is needed by upstream regress, independently of packaging.
getent passwd sshd >/dev/null || adduser --system --group --no-create-home --home /run/sshd sshd
mkdir -p /run/sshd
dpkg-buildpackage -b -us -uc -j4
OUT="$SRC/$DIST_DIR"
mkdir -p "$OUT"
rm -f "$OUT"/*.deb
cp "$TOP/build/"*.deb "$OUT/"
sha256sum "$TOP/sources/openssh-$VER.tar.gz" | sed "s|$TOP/sources/||" > "$OUT/SOURCE-SHA256SUM"
cp debian/changelog "$OUT/changelog"
VER="$VER" REL="$REL" OUT="$OUT" python3 - <<'PY'
import json, os, pathlib
pathlib.Path(os.environ['OUT'], 'build.json').write_text(json.dumps({
    'package': 'openssh', 'platform': 'ubuntu2204', 'architecture': 'amd64',
    'version': os.environ['VER'], 'release': os.environ['REL'] + 'ubuntu22.04',
    'deb_version': '1:' + os.environ['VER'] + '-' + os.environ['REL'] + 'ubuntu22.04',
}, indent=2) + '\n')
PY
(cd "$OUT" && sha256sum ./*.deb > SHA256SUMS)
bash "$SRC/scripts/verify-debs.sh" "$OUT" "$VER"
