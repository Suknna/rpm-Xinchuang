#!/usr/bin/env bash
# OpenSSH RPM 构建（在官方 UBI / CentOS 容器内执行）。
# 由统一宿主入口 scripts/package.sh 注入环境变量驱动，容器内不读 YAML：
#   BUILD_PLATFORM  平台 ID（RPM dist 后缀与 dist 目录段；centos7 与 el7 隔离构建树）
#   PACKAGING_EL    打包家族（el7|el8），决定补充源配置
#   SPEC_PATH       源 spec（仓库根相对，只读；版本只改构建目录副本）
#   ASSETS_PATH / PACKAGING_PATH  共享打包素材目录（根相对，用于定位 sshd.pam）
#   DIST_DIR        产物目录（根相对，dist/<platform>/<package>）
#   VERSION         目标 OpenSSH 版本（宿主入口已从 spec 解析或由参数指定）
#
# 步骤：配置补充源(全 gpgcheck=1) → 复制源 spec 到构建目录并替换版本 →
#       安装构建依赖 → 下载源码 → OpenSSH tarball GPG 验签 +
#       OpenSSL/zlib SHA256 校验 → rpmbuild → 上游 regress 测试 →
#       产物复制到 dist/<platform>/<package>/，输出 SHA256SUMS 与 build.spec。
# 源 spec 永不修改；build.spec 是本次实际使用的 spec 副本留档。
set -euo pipefail

SRC="${SRC_DIR:-/src}"
: "${BUILD_PLATFORM:?BUILD_PLATFORM missing (invoke via scripts/package.sh)}"
: "${PACKAGING_EL:?PACKAGING_EL missing (invoke via scripts/package.sh)}"
: "${SPEC_PATH:?SPEC_PATH missing (invoke via scripts/package.sh)}"
: "${DIST_DIR:?DIST_DIR missing (invoke via scripts/package.sh)}"
: "${VERSION:?VERSION missing (invoke via scripts/package.sh)}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+p[0-9]+$ ]] || { echo "invalid OpenSSH version: $VERSION" >&2; exit 2; }

# shellcheck source=repos-common.sh
source "$(dirname "$0")/repos-common.sh"

echo "== [$BUILD_PLATFORM] 配置 yum/dnf 源（gpgcheck 全开）"
"configure_repos_$PACKAGING_EL"

# 按构建平台隔离，CentOS 7 与 UBI7 也不能共用工作目录。
RPM_TOP="$SRC/.rpmbuild/$BUILD_PLATFORM/openssh"
OUT="$SRC/$DIST_DIR"
SOURCE_SPEC="$SRC/$SPEC_PATH"
test -f "$SOURCE_SPEC"
mkdir -p "$RPM_TOP"/{BUILD,RPMS,SOURCES,SPECS,SRPMS} "$OUT"
# 版本只改构建目录副本，源 spec 保持不动。
SPEC="$RPM_TOP/SPECS/openssh.spec"
cp "$SOURCE_SPEC" "$SPEC"
sed -Ei "s/^%global ver[[:space:]]+.*/%global ver $VERSION/" "$SPEC"

# sshd.pam 位于共享打包目录：优先 ASSETS_PATH，回退 PACKAGING_PATH。
pam_src=""
for dir in "${ASSETS_PATH:-}" "${PACKAGING_PATH:-}"; do
	if [ -n "$dir" ] && [ -f "$SRC/$dir/sshd.pam" ]; then
		pam_src="$SRC/$dir/sshd.pam"
		break
	fi
done
[ -n "$pam_src" ] || { echo "ERROR: sshd.pam not found via ASSETS_PATH/PACKAGING_PATH" >&2; exit 2; }
install -m644 "$pam_src" "$RPM_TOP/SOURCES/sshd.pam"

echo "== [$BUILD_PLATFORM] 安装构建依赖"
install_build_deps "$PACKAGING_EL" "$SPEC"

# spec 是版本唯一来源；OpenSSL/zlib 版本宏随 spec 副本解析。
VER="$VERSION"
SSL_VER="$(sed -n 's/^%global ssl_ver[[:space:]]\+//p' "$SPEC" | head -1 | tr -d '[:space:]')"
ZLIB_VER="$(sed -n 's/^%global zlib_ver[[:space:]]\+//p' "$SPEC" | head -1 | tr -d '[:space:]')"
[ -n "$SSL_VER" ] && [ -n "$ZLIB_VER" ] || { echo "ERROR: cannot parse ssl_ver/zlib_ver from spec" >&2; exit 2; }
echo "== [$BUILD_PLATFORM] OpenSSH=$VER OpenSSL=$SSL_VER zlib=$ZLIB_VER"

SOURCES="$RPM_TOP/SOURCES"

fetch() { # fetch <output> <url> [<url>...] 依次尝试直到成功
	local out="$1"; shift
	local url
	for url in "$@"; do
		if curl -fsSL --retry 3 --connect-timeout 20 -o "$out" "$url"; then
			echo "downloaded: $(basename "$out") <- $url"
			return 0
		fi
	done
	echo "ERROR: all mirrors failed for $(basename "$out")" >&2
	return 1
}

echo "== [$BUILD_PLATFORM] 下载并校验源码包"
fetch "$SOURCES/openssh-${VER}.tar.gz" \
	"https://mirrors.aliyun.com/pub/OpenBSD/OpenSSH/portable/openssh-${VER}.tar.gz" \
	"https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-${VER}.tar.gz"
fetch "$SOURCES/openssh-${VER}.tar.gz.asc" \
	"https://mirrors.aliyun.com/pub/OpenBSD/OpenSSH/portable/openssh-${VER}.tar.gz.asc" \
	"https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-${VER}.tar.gz.asc"

# OpenSSH tarball：用仓库内固定的官方 release key 验签（指纹必须匹配）
export GNUPGHOME
GNUPGHOME="$(mktemp -d)"
trap 'rm -rf "$GNUPGHOME"' EXIT
GPG="$(command -v gpg2 || command -v gpg)"
"$GPG" --quiet --import "$SRC/certs/openssh-release-key.asc"
KEY_FP="$("$GPG" --with-colons --fingerprint 2>/dev/null | awk -F: '/^fpr/{print $10; exit}')"
if [ "$KEY_FP" != "7168B983815A5EEF59A4ADFD2A3F414E736060BA" ]; then
	echo "ERROR: OpenSSH release key fingerprint mismatch: $KEY_FP" >&2
	exit 2
fi
"$GPG" --trust-model always --verify "$SOURCES/openssh-${VER}.tar.gz.asc" \
	"$SOURCES/openssh-${VER}.tar.gz"
echo "OpenSSH ${VER} GPG signature OK"

# OpenSSL / zlib tarball：SHA256 必须命中 certs/checksums.yaml 中人工维护的条目
SSL_TGZ="openssl-${SSL_VER}.tar.gz"
ZLIB_TGZ="zlib-${ZLIB_VER}.tar.gz"
fetch "$SOURCES/$SSL_TGZ" \
	"https://github.com/openssl/openssl/releases/download/openssl-${SSL_VER}/$SSL_TGZ" \
	"https://mirrors.cloud.tencent.com/openssl/source/$SSL_TGZ"
fetch "$SOURCES/$ZLIB_TGZ" \
	"https://github.com/madler/zlib/releases/download/v${ZLIB_VER}/$ZLIB_TGZ" \
	"https://zlib.net/fossils/$ZLIB_TGZ"
for TGZ in "$SSL_TGZ" "$ZLIB_TGZ"; do
	WANT_SHA="$(grep -E "^${TGZ}:" "$SRC/certs/checksums.yaml" \
		| awk '{print $2}' | sed 's/^sha256://')"
	[ -n "$WANT_SHA" ] || {
		echo "ERROR: no pinned sha256 for $TGZ; update certs/checksums.yaml" >&2
		exit 2
	}
	echo "$WANT_SHA  $SOURCES/$TGZ" | sha256sum -c -
	echo "${TGZ} SHA256 OK"
done

echo "== [$BUILD_PLATFORM] rpmbuild"
# A reused local build tree must not publish old releases alongside this one.
rm -f "$RPM_TOP"/RPMS/x86_64/openssh-*.rpm
rpmbuild -bb \
	--define "dist .${BUILD_PLATFORM}" \
	--define 'debug_package %{nil}' \
	--define "_topdir $RPM_TOP" \
	"$SPEC"

echo "== [$BUILD_PLATFORM] OpenSSH 上游 regress 测试"
bash "$SRC/scripts/test-openssh-upstream.sh" "$PACKAGING_EL" "$RPM_TOP/BUILD/openssh-$VER"

echo "== [$BUILD_PLATFORM] 收集产物"
rm -f "$OUT"/openssh-*.rpm
cp -f "$RPM_TOP"/RPMS/x86_64/*.rpm "$OUT/"
cp "$SPEC" "$OUT/build.spec"
( cd "$SOURCES" && sha256sum "openssh-${VER}.tar.gz" ) > "$OUT/SOURCE-SHA256SUM"
( cd "$OUT" && sha256sum ./*.rpm | tee SHA256SUMS )
echo "== [$BUILD_PLATFORM] DONE"
ls -l "$OUT"
