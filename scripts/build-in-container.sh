#!/usr/bin/env bash
# 在官方 UBI / CentOS 容器内执行的单平台构建脚本。
#
# 用法（宿主机）：
#   docker run --rm -v "$PWD":/src registry.access.redhat.com/ubi7/ubi:latest \
#       bash /src/scripts/build-in-container.sh el7
#   （el8 / centos7 同理换镜像与参数；本地推荐使用 local-build.sh）
#
# 步骤：配置补充源(全 gpgcheck=1) → 安装构建依赖 → 下载源码 →
#       OpenSSH tarball GPG 验签 + OpenSSL SHA256 校验 → rpmbuild →
#       产物复制到 /src/dist/<platform>/ 并输出 SHA256SUMS。
set -euo pipefail

PLATFORM="${1:?usage: build-in-container.sh <el7|el8|centos7>}"
SRC="${SRC_DIR:-/src}"
cd "$SRC"

# shellcheck source=scripts/platforms.sh
source "$SRC/scripts/platforms.sh"
EL="$(platform_el "$PLATFORM")"

# shellcheck source=repos-common.sh
source "$(dirname "$0")/repos-common.sh"

echo "== [$PLATFORM] 配置 yum/dnf 源（gpgcheck 全开）"
"configure_repos_$EL"
echo "== [$PLATFORM] 安装构建依赖"
install_build_deps "$EL" "$SRC/spec/openssh.spec"

# spec 是版本唯一来源（避免两处维护漂移）
VER="$(sed -n 's/^%global ver[[:space:]]\+//p' spec/openssh.spec | head -1 | tr -d '[:space:]')"
SSL_VER="$(sed -n 's/^%global ssl_ver[[:space:]]\+//p' spec/openssh.spec | head -1 | tr -d '[:space:]')"
ZLIB_VER="$(sed -n 's/^%global zlib_ver[[:space:]]\+//p' spec/openssh.spec | head -1 | tr -d '[:space:]')"
[ -n "$VER" ] && [ -n "$SSL_VER" ] && [ -n "$ZLIB_VER" ] || { echo "ERROR: cannot parse ver/ssl_ver from spec" >&2; exit 2; }
echo "== [$PLATFORM] OpenSSH=$VER OpenSSL=$SSL_VER zlib=$ZLIB_VER"

# 按构建平台隔离，CentOS 7 与 UBI7 也不能共用工作目录。
RPM_TOP="$SRC/.rpmbuild/$PLATFORM"
mkdir -p "$RPM_TOP"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
SOURCES="$RPM_TOP/SOURCES"
install -m644 "$SRC/source-assets/openssh/sshd.pam" "$SOURCES/sshd.pam"

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

echo "== [$PLATFORM] 下载并校验源码包"
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

echo "== [$PLATFORM] rpmbuild"
cp -f "$SRC/spec/openssh.spec" "$RPM_TOP/SPECS/"
# A reused local build tree must not publish old releases alongside this one.
rm -f "$RPM_TOP"/RPMS/x86_64/openssh-*.rpm
rpmbuild -bb \
	--define "dist .${PLATFORM}" \
	--define 'debug_package %{nil}' \
	--define "_topdir $RPM_TOP" \
	"$RPM_TOP/SPECS/openssh.spec"

echo "== [$PLATFORM] OpenSSH 上游 regress 测试"
bash "$SRC/scripts/test-openssh-upstream.sh" "$EL" "$RPM_TOP/BUILD/openssh-$VER"

echo "== [$PLATFORM] 收集产物"
OUT="$SRC/dist/$PLATFORM"
mkdir -p "$OUT"
rm -f "$OUT"/openssh-*.rpm
cp -f "$RPM_TOP"/RPMS/x86_64/*.rpm "$OUT/"
cp "$RPM_TOP/SPECS/openssh.spec" "$OUT/openssh-$PLATFORM.spec"
( cd "$SOURCES" && sha256sum "openssh-${VER}.tar.gz" ) > "$OUT/SOURCE-SHA256SUM"
( cd "$OUT" && sha256sum ./*.rpm | tee SHA256SUMS )
echo "== [$PLATFORM] DONE"
ls -l "$OUT"
