#!/usr/bin/env bash
# RPM 构建产物质量门禁（在 UBI 容器内运行，位于安装行为测试之前）。
# 用法: verify-rpms.sh <el7|el8>
#
# 检查项：
#   1. 三包齐全且 EVR/arch 正确（openssh / clients / server, x86_64）
#   2. SHA256SUMS 与实际产物一致
#   3. 所有 ELF 不动态依赖 libcrypto/libssl/libz（静态链接验证）
#   4. sshd 动态链接 libpam（PAM 必须动态可用）
#   5. /etc 下不得有任何真实 payload（只允许 config+noreplace+ghost 标记项）
#   6. 模板文件与 ghost 声明齐全；server 运行依赖正确
set -uo pipefail

EL="${1:?usage: verify-rpms.sh <el7|el8>}"
DIST="${SRC_DIR:-/src}/dist/$EL"
FAIL=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }

SPEC="${SRC_DIR:-/src}/openssh.spec"
VER="$(sed -n 's/^%global ver[[:space:]]\+//p' "$SPEC" | head -1 | tr -d '[:space:]')"

echo "== [$EL] 1) 三包齐全与 EVR/arch"
for p in openssh openssh-clients openssh-server; do
	f="$DIST/$p-$VER-1.$EL.x86_64.rpm"
	if [ -f "$f" ]; then pass "$(basename "$f") 存在"; else fail "缺失 $f"; continue; fi
	got="$(rpm -qp --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}' "$f")"
	[ "$got" = "$p-$VER-1.$EL.x86_64" ] && pass "EVR/arch: $got" || fail "EVR/arch 期望 $p-$VER-1.$EL.x86_64，实际 $got"
done

echo "== [$EL] 2) SHA256SUMS"
( cd "$DIST" && grep -v SHA256SUMS SHA256SUMS | sha256sum -c --quiet ) \
	&& pass "SHA256SUMS 校验通过" || fail "SHA256SUMS 不一致"

echo "== [$EL] 3/4) ELF 动态依赖检查（静态 libcrypto/libssl/zlib + 动态 PAM）"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/x"
for rpm in "$DIST"/openssh-*.rpm; do
	( cd "$TMP/x" && rpm2cpio "$rpm" | cpio -idm --quiet ) || { fail "解包失败: $rpm"; }
done
FOUND_SSL=0; FOUND_Z=0
while IFS= read -r bin; do
	out="$(ldd "$bin" 2>/dev/null)" || continue
	echo "$out" | grep -qE "libcrypto|libssl" && { FOUND_SSL=1; fail "动态依赖 libcrypto/libssl: $bin"; }
	echo "$out" | grep -qE "libz\.so" && { FOUND_Z=1; fail "动态依赖 libz: $bin"; }
done < <(find "$TMP/x" -type f \( -path "*/bin/*" -o -path "*/sbin/*" -o -path "*/openssh/*" \))
[ "$FOUND_SSL" = 0 ] && pass "无 libcrypto/libssl 动态依赖"
[ "$FOUND_Z" = 0 ] && pass "无 libz 动态依赖"
ldd "$TMP/x/usr/sbin/sshd" 2>/dev/null | grep -q libpam \
	&& pass "sshd 动态链接 libpam" || fail "sshd 未动态链接 libpam"
for b in sshd sshd-session sftp-server; do
	[ -x "$TMP/x/usr/sbin/$b" ] || [ -x "$TMP/x/usr/libexec/openssh/$b" ] || fail "缺少服务端二进制 $b"
done
[ -x "$TMP/x/usr/libexec/openssh/sshd-auth" ] && pass "sshd-auth 就位" || fail "缺少 sshd-auth"
[ -x "$TMP/x/usr/bin/ssh" ] && pass "客户端二进制就位" || fail "缺少 ssh"

echo "== [$EL] 5) /etc 无真实 payload（仅允许 ghost 标记）"
# FILEFLAGS 位: CONFIG=1 NOREPLACE=16 GHOST=32。/etc 下所有文件必须同时带三标记(49)。
BAD_ETC="$(rpm -qp --qf '[%{FILENAMES}\t%{FILEFLAGS}\n]' "$DIST"/openssh-*.rpm |
	while IFS=$'\t' read -r path flags; do
		case "$path" in
		/etc/*)
			if [ $(( flags & 1 )) -eq 0 ] || [ $(( flags & 16 )) -eq 0 ] || [ $(( flags & 32 )) -eq 0 ]; then
				echo "BAD $path flags=$flags"
			fi
			;;
		esac
	done)"
if [ -n "$BAD_ETC" ]; then
	fail "/etc 存在非 ghost 的真实 payload: $BAD_ETC"
else
	pass "/etc 下无真实 payload（全部为 config+noreplace+ghost 声明）"
fi

echo "== [$EL] 6) 模板与 ghost 声明、运行依赖"
FILELIST="$(rpm -qp --qf '%{NAME} %{FILENAMES}\n' "$DIST"/openssh-*.rpm)"
for t in /usr/share/openssh/sshd_config /usr/share/openssh/ssh_config \
         /usr/share/openssh/moduli /usr/share/openssh/sshd.pam \
         /usr/share/openssh/sshd.init; do
	echo "$FILELIST" | grep -q "$t" && pass "模板 $t" || fail "缺模板 $t"
done
for g in /etc/ssh/sshd_config /etc/ssh/ssh_config /etc/ssh/moduli /etc/pam.d/sshd /etc/rc.d/init.d/sshd; do
	echo "$FILELIST" | grep -q "$g" && pass "ghost 声明 $g" || fail "缺 ghost 声明 $g"
done
REQ="$(rpm -qp --requires "$DIST"/openssh-server-*.rpm)"
echo "$REQ" | grep -q "initscripts" && pass "Requires initscripts" || fail "缺 Requires initscripts"
echo "$REQ" | grep -q "chkconfig" && pass "Requires chkconfig" || fail "缺 Requires chkconfig"
echo "$REQ" | grep -qE "pam|system-auth" && pass "Requires pam" || fail "缺 Requires pam"

echo "== [$EL] verify 结果: $FAIL failure(s)"
exit $((FAIL > 0))
