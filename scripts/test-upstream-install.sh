#!/usr/bin/env bash
# Verify binary RPM installation and a real command in a fresh platform container.
# 容器内执行；PACKAGING_EL/DIST_DIR 由 scripts/package.sh 注入。
set -euo pipefail
PKG="${1:?usage: test-upstream-install.sh <package> <platform> <version>}"
PLATFORM="${2:?missing platform}"
VER="${3:?missing version}"
SRC="${SRC_DIR:-/src}"
EL="${PACKAGING_EL:?PACKAGING_EL missing (invoke via scripts/package.sh)}"
DIST="${DIST_DIR:+$SRC/$DIST_DIR}"
[ -n "$DIST" ] || { echo "DIST_DIR missing (invoke via scripts/package.sh)" >&2; exit 2; }

test_chrony_daemon() {
  # No external NTP traffic and no access to the system clock (-x, port 0).
  cat > /tmp/rpm-xinchuang-chrony.conf <<'CHRONY'
driftfile /tmp/rpm-xinchuang-chrony.drift
pidfile /tmp/rpm-xinchuang-chrony.pid
port 0
bindcmdaddress 127.0.0.1
local stratum 8
CHRONY
  chronyd -x -d -f /tmp/rpm-xinchuang-chrony.conf > /tmp/rpm-xinchuang-chrony.log 2>&1 &
  local pid=$! ready=0
  for attempt in 1 2 3 4 5; do
    if chronyc -h 127.0.0.1 tracking > /tmp/rpm-xinchuang-tracking 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done
  kill "$pid" 2>/dev/null || :
  wait "$pid" 2>/dev/null || :
  if [ "$ready" != 1 ]; then
    echo "chronyd did not answer chronyc tracking on loopback" >&2
    return 1
  fi
  grep -F 'Stratum' /tmp/rpm-xinchuang-tracking
}

# shellcheck source=scripts/repos-common.sh
source "$SRC/scripts/repos-common.sh"
"configure_repos_$EL"
# 实际包身份与构建元数据一致（Name/Version/Release/Arch；共享 spec 按 dist 展开宏）。
# shellcheck source=scripts/rpm-identity.sh
source "$SRC/scripts/rpm-identity.sh"
rpm_identity_verify "$DIST" "$DIST/build.spec" "$PLATFORM" "$VER" || exit 1
shopt -s nullglob
rpms=("$DIST"/*.rpm)
install=()
for file in "${rpms[@]}"; do
  case "$(basename "$file")" in
    *-debuginfo-*|*-debugsource-*) continue ;;
  esac
  install+=("$file")
done
[ "${#install[@]}" -gt 0 ] || { echo "no installable RPMs: $DIST" >&2; exit 1; }
(cd "$DIST" && sha256sum -c SHA256SUMS)
if [ "$EL" = el7 ]; then
  yum -y -q install "${install[@]}"
else
  dnf -y -q install "${install[@]}"
fi
query_pkg="$PKG"
[ "$PKG" != vim ] || query_pkg=vim-enhanced
# 安装后身份核对：Version/Release 与 build.spec（含 dist 展开值）一致，Arch 合理。
expected_release="$(rpm_identity_release "$DIST/build.spec" "$PLATFORM")"
identity="$(rpm -q --qf '%{VERSION} %{RELEASE} %{ARCH}' "$query_pkg" 2>/dev/null)" || {
  echo "package $query_pkg ($VER) not installed" >&2; exit 1;
}
read -r got_version got_release got_arch <<<"$identity"
if [ "$got_version" != "$VER" ] || [ "$got_release" != "$expected_release" ] \
    || { [ "$got_arch" != x86_64 ] && [ "$got_arch" != noarch ]; }; then
  echo "installed identity mismatch: $query_pkg $got_version-$got_release.$got_arch, expected $VER-$expected_release.{x86_64|noarch}" >&2
  exit 1
fi
case "$PKG" in
  bash) /bin/bash -c '[[ $(printf ok) == ok ]]' && /bin/bash --version | grep -F "$VER" ;;
  sudo) if [ "$EL" = el7 ]; then yum -y -q install cpio shadow-utils util-linux
        else dnf -y -q install cpio shadow-utils util-linux; fi
        bash "$SRC/scripts/verify-pam-rpms.sh" sudo "$DIST/sudo-$VER-"*."$PLATFORM".x86_64.rpm
        sudo -V | grep -F "$VER"; test -f /etc/sudoers
        test -s /etc/pam.d/sudo && test -s /etc/pam.d/sudo-i
        sudo -n /usr/bin/true
        # Root's passwordless smoke test cannot exercise PAM authentication.
        useradd -m -G wheel pam-ci
        password="PAM-ci-$(date +%s%N)"
        printf 'pam-ci:%s\n' "$password" | chpasswd
        test "$(printf '%s\n' "$password" | runuser -u pam-ci -- sudo -S -k /usr/bin/id -u)" = 0
        test "$(printf '%s\n' "$password" | runuser -u pam-ci -- sudo -S -k -i /usr/bin/id -u)" = 0 ;;
  chrony) chronyd -v | grep -F "$VER"; test -f /usr/lib/systemd/system/chronyd.service
          test_chrony_daemon ;;
  vim) vim_banner="$(vim --version)"
       grep -F "Vi IMproved ${VER%.*}" <<< "$vim_banner"
       grep -F "${VER##*.}" <<< "$vim_banner"
       test -f /etc/vimrc
       printf 'hello\n' > /tmp/vim-smoke.txt
       vim -es -u NONE -c '%s/hello/works/' -c wq /tmp/vim-smoke.txt
       grep -Fx 'works' /tmp/vim-smoke.txt
       # Command-line Vim cannot catch GUI ABI/runtime regressions. Use only
       # the target distribution's X server and libraries in this clean image.
       if [ "$EL" = el7 ]; then yum -y -q install xorg-x11-server-Xvfb xorg-x11-xauth
       else dnf -y -q install xorg-x11-server-Xvfb xorg-x11-xauth; fi
       gvim --version
       printf 'hello\n' > /tmp/gvim-smoke.txt
       timeout 30s xvfb-run -a gvim -f -u NONE -U NONE -i NONE -n \
         -c "if !has('gui_running') | cquit | endif" \
         -c '%s/hello/gui-works/' -c wq /tmp/gvim-smoke.txt
       grep -Fx 'gui-works' /tmp/gvim-smoke.txt ;;
  ntp) ntpd --version 2>&1 | grep -F "$VER"; test -f /usr/lib/systemd/system/ntpd.service ;;
  telnet) telnet --version | grep -F "$VER"; rpm -q telnet-server
          test -f /usr/lib/systemd/system/telnet.socket
          if [ "$EL" = el7 ]; then python "$SRC/scripts/test-telnet-negotiation.py"
          else /usr/libexec/platform-python "$SRC/scripts/test-telnet-negotiation.py"; fi ;;
  *)
    # 通用默认 smoke：只承诺安装后 EVR 一致（上方 rpm -q 已强校验）。
    # 未注册专用验证的包不伪报组件特有检查；配置新增普通包无需改本脚本。
    echo "$PKG $VER on $PLATFORM installed; no package-specific smoke test registered" ;;
esac
echo "$PKG $VER on $PLATFORM installed and ran successfully"
