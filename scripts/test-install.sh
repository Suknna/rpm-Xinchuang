#!/usr/bin/env bash
# RPM 安装行为测试：在干净的官方 UBI 容器内运行。
#
# 用法（宿主机，见 local-test.sh）：
#   docker run --rm -v "$PWD":/src registry.access.redhat.com/ubi7/ubi:latest \
#       bash /src/scripts/test-install.sh el7 fresh
#
# 场景：
#   fresh         全新安装：不生成 host key、不启动 sshd、服务注册且开机自启、
#                 启动后仅生成缺失密钥且重启不再改写密钥
#   upgrade       用发行版旧 openssh（EL7=7.4p1 / EL8=8.0p1）真实升级到本包：
#                 配置与密钥逐字节保留、绝不产生 .rpmnew/.rpmsave、
#                 验证“旧包 scriptlet 可能重启”的真实边界
#   reinstall     同版本强制重装：配置保留、运行中的 sshd 不被重启
#   uninstall     卸载：停止服务、注销服务、配置原位保留（不删除不移动）
#   symlink-guard 已存在悬空软链/FIFO 等目录项时：绝不覆盖，仅补真正缺失项
#
# 任一断言失败都会使脚本以非零退出。
set -uo pipefail

EL="${1:?usage: test-install.sh <el7|el8> <fresh|upgrade|reinstall|uninstall>}"
SCENARIO="${2:?usage: test-install.sh <el7|el8> <fresh|upgrade|reinstall|uninstall>}"
SRC="${SRC_DIR:-/src}"
DIST="/src/dist/$EL"
MARKER="# RPM-XINCHUANG-TEST-MARKER"

FAILURES=0
pass() { echo "  PASS: $1"; }
fail() {
	echo "  FAIL: $1" >&2
	FAILURES=$((FAILURES + 1))
}
assert_eq() { # assert_eq <说明> <期望> <实际>
	if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (expect [$2], got [$3])"; fi
}
assert_file() {
	if [ -e "$2" ]; then pass "$1"; else fail "$1 (missing $2)"; fi
}
assert_no_file() {
	if [ ! -e "$2" ]; then pass "$1"; else fail "$1 (unexpected $2)"; fi
}
assert_contains() {
	case "$2" in
	*"$3"*) pass "$1" ;;
	*) fail "$1 ([$3] not found in [$2])" ;;
	esac
}

source /src/scripts/repos-common.sh

PM_INSTALL() { # 用包管理器安装本地 rpm（自动解析依赖）
	if [ "$EL" = el7 ]; then
		yum -y install "$DIST"/openssh-*.rpm
	else
		dnf -y install "$DIST"/openssh-*.rpm
	fi
}

pid1_is_systemd() { [ "$(ps -p 1 -o comm= 2>/dev/null)" = "systemd" ]; }

start_distro_sshd() { # 发行版包的启动方式（升级场景）
	if [ "$EL" = el7 ]; then
		/etc/rc.d/init.d/sshd start
	elif pid1_is_systemd; then
		systemctl start sshd
	else
		# 容器无 systemd：直接拉起守护进程（效果等同，写 /var/run/sshd.pid）
		/usr/sbin/sshd
	fi
}

start_our_sshd() {
	/etc/rc.d/init.d/sshd start
}

read_banner() { # 读取本机 22 端口 banner；20*0.5s 内失败则输出空串
	local i b
	for i in $(seq 1 20); do
		if exec 3<> /dev/tcp/127.0.0.1/22 2>/dev/null; then
			b=""
			read -r -t 5 b <&3 || true
			exec 3<&- 3>&- 2>/dev/null || true
			if [ -n "$b" ]; then echo "$b"; return 0; fi
		fi
		sleep 0.5
	done
	echo ""
	return 1
}

keys_state() { # 所有 host key 内容指纹的组合校验值（检测密钥是否被改写）
	local f sum=""
	for f in /etc/ssh/ssh_host_*key; do
		[ -f "$f" ] || continue
		sum="$sum$(sha256sum "$f" | awk '{print $1}')"
	done
	echo "$sum"
}

config_state() { sha256sum /etc/ssh/sshd_config 2>/dev/null | awk '{print $1}'; }

echo "=== [$EL/$SCENARIO] 仓库配置（gpgcheck 全开）"
case "$EL" in
el7) configure_repos_el7 ;;
el8) configure_repos_el8 ;;
*) echo "unknown EL" >&2; exit 2 ;;
esac

case "$SCENARIO" in

fresh)
	echo "=== 全新安装"
	PM_INSTALL || { fail "rpm 安装失败"; exit 1; }

	assert_file "sshd_config 默认配置已安装" /etc/ssh/sshd_config
	assert_eq "sshd_config 权限 600" "600" "$(stat -c %a /etc/ssh/sshd_config)"
	cmp -s /etc/ssh/sshd_config /usr/share/openssh/sshd_config &&
		pass "默认配置与 /usr/share 模板一致" ||
		fail "默认配置与模板不一致"
	assert_file "ssh_config 已安装" /etc/ssh/ssh_config
	assert_file "PAM 配置已安装" /etc/pam.d/sshd
	assert_file "init 脚本已安装" /etc/rc.d/init.d/sshd
	assert_file "moduli 已安装" /etc/ssh/moduli
	assert_eq "安装后不生成 host key" "0" \
		"$(ls /etc/ssh/ssh_host_*key 2>/dev/null | wc -l)"
	if pgrep -x sshd >/dev/null; then fail "安装后 sshd 不应运行"; else pass "安装后 sshd 未运行"; fi
	assert_no_file "安装后无 pid 文件" /var/run/sshd.pid
	assert_contains "服务已注册且开机自启(3:on)" \
		"$(chkconfig --list sshd 2>/dev/null || true)" "3:on"
	id sshd >/dev/null 2>&1 && pass "privsep 用户 sshd 已创建" || fail "privsep 用户缺失"
	assert_file "privsep 目录存在" /var/empty/sshd
	ssh -V 2>&1 | grep -q "OpenSSH_10\." && pass "客户端为 OpenSSH 10.x" \
		|| fail "客户端版本异常: $(ssh -V 2>&1)"

	echo "=== 首次启动（init 脚本负责生成缺失密钥）"
	start_our_sshd || fail "服务启动失败"
	BANNER="$(read_banner)"
	assert_contains "banner 为 OpenSSH 10.x" "$BANNER" "SSH-2.0-OpenSSH_10."
	[ "$(ls /etc/ssh/ssh_host_*key 2>/dev/null | wc -l)" -ge 3 ] &&
		pass "首次启动生成了缺失的 host key" ||
		fail "host key 未生成"
	/usr/sbin/sshd -t && pass "sshd -t 配置检查通过" || fail "sshd -t 失败"

	echo "=== 重启不改写已有密钥"
	KEYS_BEFORE="$(keys_state)"
	/etc/rc.d/init.d/sshd stop || fail "服务停止失败"
	start_our_sshd || fail "二次启动失败"
	assert_eq "重启后密钥逐字节一致" "$KEYS_BEFORE" "$(keys_state)"
	pgrep -x sshd >/dev/null && pass "二次启动后 sshd 运行中" || fail "二次启动后 sshd 未运行"
	;;

upgrade)
	echo "=== 安装发行版旧版 openssh 作为升级基线"
	if [ "$EL" = el7 ]; then
		yum -y -q install openssh-server openssh-clients
	else
		dnf -y -q install openssh-server openssh-clients
	fi
	DISTRO_VER="$(rpm -q openssh-server)"
	echo "  发行版基线: $DISTRO_VER"
	ssh -V 2>&1
	INIT_BEFORE="$(sha256sum /etc/rc.d/init.d/sshd 2>/dev/null | awk '{print $1}')"
	# 留证：旧包 scriptlet 是否包含重启逻辑（“旧包升级会重启”边界的客观依据）
	echo "--- 发行版 openssh-server 的 %postun scriptlet:"
	rpm -q --scripts openssh-server | sed -n '/postun program/,/^$/{/^postun/,/^$/p}' | head -20
	rpm -q --scripts openssh-server | grep -iE "condrestart|try-restart|restart" \
		&& OLD_SCRIPT_RESTARTS=yes || OLD_SCRIPT_RESTARTS=no

	echo "=== 启动发行版 sshd 并定制配置"
	start_distro_sshd || { fail "发行版 sshd 启动失败"; exit 1; }
	OLD_BANNER="$(read_banner)"
	OLD_PID="$(pgrep -xo sshd)"
	echo "  旧 banner: $OLD_BANNER  pid: $OLD_PID"
	echo "$MARKER" >> /etc/ssh/sshd_config
	echo "PasswordAuthentication yes" >> /etc/ssh/sshd_config
	CONFIG_BEFORE="$(config_state)"
	KEYS_BEFORE="$(keys_state)"

	echo "=== 升级到本包"
	PM_INSTALL || { fail "升级失败"; exit 1; }
	rpm -q openssh-server | grep -q "10\." && pass "openssh-server 已是 10.x" \
		|| fail "版本未升级: $(rpm -q openssh-server)"

	echo "=== 升级后：配置与密钥必须逐字节保留（严格：不覆盖不移动）"
	assert_eq "sshd_config 内容未变" "$CONFIG_BEFORE" "$(config_state)"
	assert_contains "定制标记仍在" "$(cat /etc/ssh/sshd_config)" "$MARKER"
	assert_eq "host key 未被改写" "$KEYS_BEFORE" "$(keys_state)"
	assert_eq "init 脚本未被替换/移动" "$INIT_BEFORE" \
		"$(sha256sum /etc/rc.d/init.d/sshd 2>/dev/null | awk '{print $1}')"
	assert_no_file "严格策略：不产生 .rpmnew" /etc/ssh/sshd_config.rpmnew
	assert_no_file "严格策略：不产生 .rpmsave" /etc/ssh/sshd_config.rpmsave
	assert_no_file "严格策略：不产生 .rpmnew(init)" /etc/rc.d/init.d/sshd.rpmnew
	/usr/sbin/sshd -t && pass "新二进制 + 保留配置: sshd -t 通过" || fail "sshd -t 失败（升级将无法重启！）"

	echo "=== 升级后：运行状态边界（如实验证，不虚假保证）"
	NEW_PID="$(pgrep -xo sshd || true)"
	if [ -n "$NEW_PID" ] && [ "$NEW_PID" != "$OLD_PID" ]; then
		pass "sshd 在升级过程中被重启（旧包 scriptlet 所致，pid $OLD_PID -> $NEW_PID）"
		NEW_BANNER="$(read_banner)"
		assert_contains "重启后新版本接管" "$NEW_BANNER" "OpenSSH_10."
	elif pgrep -x sshd >/dev/null; then
		pass "sshd 全程未被触碰（pid 保持 $OLD_PID；容器内旧包重启脚本未生效）"
	else
		fail "升级后 sshd 未运行（进程丢失，这属于危险行为）"
	fi
	if [ "$OLD_SCRIPT_RESTARTS" = yes ]; then
		pass "已证实旧包 scriptlet 含重启逻辑（真实环境升级会触发重启，README 如实说明）"
	else
		pass "旧包 scriptlet 不含重启逻辑"
	fi
	;;

reinstall)
	echo "=== 全新安装本包并定制配置、启动服务"
	PM_INSTALL || { fail "安装失败"; exit 1; }
	echo "$MARKER" >> /etc/ssh/sshd_config
	start_our_sshd || fail "启动失败"
	read_banner >/dev/null
	PID_BEFORE="$(pgrep -xo sshd)"
	CONFIG_BEFORE="$(config_state)"
	KEYS_BEFORE="$(keys_state)"

	echo "=== 同版本强制重装（模拟重装场景，scriptlet 以升级语义运行）"
	rpm -Uvh --force "$DIST"/openssh-*.rpm || fail "重装失败"

	assert_eq "配置逐字节保留" "$CONFIG_BEFORE" "$(config_state)"
	assert_contains "定制标记仍在" "$(cat /etc/ssh/sshd_config)" "$MARKER"
	assert_eq "host key 未变" "$KEYS_BEFORE" "$(keys_state)"
	if pgrep -xo sshd 2>/dev/null | grep -q "^$PID_BEFORE$"; then
		pass "运行中的 sshd 未被重启（pid 保持 $PID_BEFORE）"
	else
		fail "sshd 被重启或丢失（pid $PID_BEFORE -> $(pgrep -xo sshd || echo none))"
	fi
	assert_no_file "内容一致不产生 .rpmnew" /etc/ssh/sshd_config.rpmnew
	;;

uninstall)
	echo "=== 安装、启动、定制后卸载"
	PM_INSTALL || { fail "安装失败"; exit 1; }
	echo "$MARKER" >> /etc/ssh/sshd_config
	start_our_sshd || fail "启动失败"
	read_banner >/dev/null

	rpm -e openssh-server || fail "卸载失败"
	! pgrep -x sshd >/dev/null && pass "卸载已停止 sshd" || fail "卸载后 sshd 仍在运行"
	assert_no_file "锁文件已清理" /var/lock/subsys/sshd
	chkconfig --list sshd >/dev/null 2>&1 && fail "服务仍注册" || pass "服务已注销"
	assert_file "卸载不删除配置（ghost 所有权）" /etc/ssh/sshd_config
	assert_contains "保留的配置内含定制标记" "$(cat /etc/ssh/sshd_config)" "$MARKER"
	assert_no_file "卸载不产生 .rpmsave（不移动文件）" /etc/ssh/sshd_config.rpmsave
	;;

*)
	echo "unknown scenario: $SCENARIO" >&2
	exit 2
	;;
esac

case "$SCENARIO" in

symlink-guard)
	echo "=== 预置悬空软链与 FIFO（模拟既有目录项）"
	mkdir -p /etc/ssh
	ln -s /nonexistent-target /etc/ssh/sshd_config
	mkfifo /etc/pam.d/sshd
	echo "=== 安装（目录项已存在，绝不覆盖）"
	PM_INSTALL || { fail "rpm 安装失败"; exit 1; }
	assert_eq "悬空软链未被覆盖" "/nonexistent-target" "$(readlink /etc/ssh/sshd_config)"
	[ -p /etc/pam.d/sshd ] && pass "FIFO 未被覆盖" || fail "FIFO 被替换: $(ls -l /etc/pam.d/sshd)"
	echo "=== 强制重装（仍不覆盖既有目录项）"
	rpm -Uvh --force "$DIST"/openssh-*.rpm || fail "重装失败"
	assert_eq "重装后悬空软链仍未被覆盖" "/nonexistent-target" "$(readlink /etc/ssh/sshd_config)"
	[ -p /etc/pam.d/sshd ] && pass "重装后 FIFO 仍未被覆盖" || fail "重装后 FIFO 被替换"
	echo "=== 清理测试目录项后重装 → 仅此时才补模板"
	rm -f /etc/ssh/sshd_config /etc/pam.d/sshd
	rpm -Uvh --force "$DIST"/openssh-*.rpm || fail "重装失败"
	assert_file "缺失的 sshd_config 已从模板补齐" /etc/ssh/sshd_config
	assert_eq "补齐的 sshd_config 权限 600" "600" "$(stat -c %a /etc/ssh/sshd_config)"
	cmp -s /etc/ssh/sshd_config /usr/share/openssh/sshd_config &&
		pass "补齐内容与模板一致" || fail "补齐内容与模板不一致"
	assert_file "缺失的 pam 配置已补齐" /etc/pam.d/sshd
	;;

*)
	echo "unknown scenario: $SCENARIO" >&2
	exit 2
	;;
esac

echo "=== [$EL/$SCENARIO] 结果: ${FAILURES} failure(s)"
exit $((FAILURES > 0))
