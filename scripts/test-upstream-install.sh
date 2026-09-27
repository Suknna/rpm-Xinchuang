#!/usr/bin/env bash
# Verify binary RPM installation and a real command in a fresh UBI container.
set -euo pipefail
PKG="${1:?usage: test-upstream-install.sh <package> <el7|el8> <version>}"
EL="${2:?missing platform}"
VER="${3:?missing version}"
SRC="${SRC_DIR:-/src}"
DIST="$SRC/dist/$PKG/$EL"

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
rpm -q --qf '%{VERSION}\n' "$query_pkg" | grep -Fx "$VER"
case "$PKG" in
  bash) /bin/bash -c '[[ $(printf ok) == ok ]]' && /bin/bash --version | grep -F "$VER" ;;
  sudo) if [ "$EL" = el7 ]; then yum -y -q install cpio shadow-utils util-linux
        else dnf -y -q install cpio shadow-utils util-linux; fi
        bash "$SRC/scripts/verify-pam-rpms.sh" sudo "$DIST/sudo-$VER-"*."$EL".x86_64.rpm
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
       grep -Fx 'works' /tmp/vim-smoke.txt ;;
  ntp) ntpd --version 2>&1 | grep -F "$VER"; test -f /usr/lib/systemd/system/ntpd.service ;;
  telnet) telnet --version | grep -F "$VER"; rpm -q telnet-server
          test -f /usr/lib/systemd/system/telnet.socket
          if [ "$EL" = el7 ]; then python "$SRC/scripts/test-telnet-negotiation.py"
          else /usr/libexec/platform-python "$SRC/scripts/test-telnet-negotiation.py"; fi ;;
  *) exit 2 ;;
esac
echo "$PKG $VER on $EL installed and ran successfully"
