#!/usr/bin/env bash
# Run each scenario in a fresh Ubuntu 22.04 amd64 container, never on the host.
set -euo pipefail
scenario="${1:?usage: test-openssh-deb.sh <scenario> <version>}"
version="${2:?missing version}"
case "$scenario" in fresh|upgrade|reinstall|uninstall|symlink-guard) ;; *) exit 2 ;; esac
# shellcheck source=/dev/null
source /etc/os-release
[ "$ID:$VERSION_ID:$(dpkg --print-architecture)" = ubuntu:22.04:amd64 ] || exit 2
SRC="${SRC_DIR:-/src}"
dir="$SRC/dist/openssh/ubuntu2204"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends ca-certificates python3 binutils sshpass systemd
bash "$SRC/scripts/verify-debs.sh" "$dir" "$version"
# Suppress distro service autostart only during fixture preparation.
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod +x /usr/sbin/policy-rc.d
if [ "$scenario" = upgrade ]; then
    apt-get install -y openssh-server openssh-client openssh-sftp-server
fi
mkdir -p /run/sshd /root/.ssh
if [ "$scenario" = symlink-guard ]; then
    mkdir -p /etc/ssh /etc/pam.d /etc/default
    for file in /etc/ssh/ssh_config /etc/ssh/sshd_config /etc/ssh/moduli /etc/pam.d/sshd /etc/default/ssh; do
        ln -s /missing-config-target "$file"
    done
fi
if [ "$scenario" = upgrade ]; then
    printf '\n# locally managed server config\n' >> /etc/ssh/sshd_config
    printf '\n# locally managed client config\n' >> /etc/ssh/ssh_config
    printf '\n# locally managed PAM config\n' >> /etc/pam.d/sshd
    printf '\n# local service options\n' >> /etc/default/ssh
    printf '# local included configuration\n' > /etc/ssh/sshd_config.d/local.conf
    sha256sum /etc/ssh/ssh*_config /etc/ssh/sshd_config.d/local.conf /etc/ssh/moduli \
        /etc/ssh/ssh_host_* /etc/pam.d/sshd /etc/default/ssh > /tmp/preserved
    ssh-keygen -q -t ed25519 -N '' -f /root/.ssh/id_ed25519
    cp /root/.ssh/id_ed25519.pub /root/.ssh/authorized_keys
    /usr/sbin/sshd -D -p 2222 -o PermitRootLogin=prohibit-password -E /tmp/old-sshd.log &
    old_pid=$!
    # A live session must continue through the package transaction.
    for attempt in {1..30}; do
        if ssh -p 2222 -o StrictHostKeyChecking=no -o BatchMode=yes root@127.0.0.1 true; then break; fi
        sleep 1
    done
    ssh -p 2222 -o BatchMode=yes root@127.0.0.1 'while :; do echo alive; sleep 1; done' > /tmp/heartbeat &
    session_pid=$!
fi
# Record service-manager requests rather than letting a container policy hide a restart.
for command in systemctl invoke-rc.d deb-systemd-invoke; do
    path="$(command -v "$command")"
    mv "$path" "$path.real"
    printf '#!/bin/sh\necho "%s $*" >> /tmp/service-actions\nexit 0\n' "$command" > "$path"
    if [ "$command" = systemctl ]; then
        # Allow offline enable/preset operations to create real unit symlinks.
        cat > "$path" <<'SH'
#!/bin/sh
echo "systemctl $*" >> /tmp/service-actions
case " $* " in
    *' preset '*|*' enable '*|*' disable '*) exec /usr/bin/systemctl.real --root=/ "$@" ;;
esac
exit 0
SH
    fi
    chmod +x "$path"
done
: > /tmp/service-actions
# Exercise debhelper's systemd branch even though PID 1 in this container is bash.
mkdir -p /run/systemd/system
apt-get install -y "$dir/"*.deb
if [ "$scenario" = reinstall ]; then
    sha256sum /etc/ssh/ssh*_config /etc/pam.d/sshd > /tmp/preserved
    apt-get install -y --reinstall "$dir/"*.deb
    sha256sum -c /tmp/preserved
fi
if grep -E '(^| )(start|stop|restart|try-restart|reload|reload-or-restart)( |$)' /tmp/service-actions; then
    echo 'Package transaction requested a service restart/stop/start' >&2; exit 1
fi
if [ "$scenario" = upgrade ]; then
    sha256sum -c /tmp/preserved
    kill -0 "$old_pid" "$session_pid"
    before="$(wc -l < /tmp/heartbeat)"
    sleep 2
    [ "$(wc -l < /tmp/heartbeat)" -gt "$before" ]
    kill "$session_pid" "$old_pid"
fi
if [ "$scenario" = fresh ] || [ "$scenario" = reinstall ]; then
    if compgen -G '/etc/ssh/ssh_host_*key' >/dev/null; then
        echo 'Package installation unexpectedly generated host keys' >&2; exit 1
    fi
fi
if [ "$scenario" = symlink-guard ]; then
    for file in /etc/ssh/ssh_config /etc/ssh/sshd_config /etc/ssh/moduli /etc/pam.d/sshd /etc/default/ssh; do
        [ "$(readlink "$file")" = /missing-config-target ] && [ ! -e "$file" ]
    done
    echo 'Dangling configuration symlinks preserved'
    exit 0
fi
ssh -V 2>&1 | grep -F "OpenSSH_$version"
dpkg --audit
# First explicit service start is responsible for generating missing host keys.
ssh-keygen -A
sshd=/usr/sbin/sshd
"$sshd" -t
"$sshd" -T | grep -i '^usepam yes$'
systemd-analyze verify /lib/systemd/system/ssh.service /lib/systemd/system/ssh.socket /lib/systemd/system/ssh@.service
# A fresh install enables the normal daemon but leaves socket activation opt-in.
if [ "$scenario" = fresh ]; then
    test -L /etc/systemd/system/multi-user.target.wants/ssh.service
    test ! -L /etc/systemd/system/sockets.target.wants/ssh.socket
fi
useradd -m -s /bin/bash sshcheck
echo 'sshcheck:Container-Test-Only-934!' | chpasswd
"$sshd" -D -p 2223 -E /tmp/new-sshd.log &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
export SSHPASS='Container-Test-Only-934!'
ssh_options=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PreferredAuthentications=password)
for ((attempt = 1; attempt <= 30; attempt++)); do
    # Expansion belongs to the remote shell, not the test runner.
    # shellcheck disable=SC2016
    if sshpass -e ssh "${ssh_options[@]}" -p 2223 sshcheck@127.0.0.1 'test "$(id -un)" = sshcheck'; then break; fi
    sleep 1
done
# This final call makes readiness timeout a hard failure and exercises PAM authentication.
sshpass -e ssh "${ssh_options[@]}" -p 2223 sshcheck@127.0.0.1 'echo transfer-ok > payload'
printf 'get payload /tmp/sftp-payload\n' | sshpass -e sftp "${ssh_options[@]}" -P 2223 sshcheck@127.0.0.1
grep -qx transfer-ok /tmp/sftp-payload
sshpass -e scp -O "${ssh_options[@]}" -P 2223 sshcheck@127.0.0.1:payload /tmp/scp-payload
cmp /tmp/sftp-payload /tmp/scp-payload
if [ "$scenario" = uninstall ]; then
    sha256sum /etc/ssh/ssh*_config /etc/ssh/ssh_host_* /etc/pam.d/sshd > /tmp/preserved
    apt-get remove -y openssh-server openssh-client openssh-sftp-server
    sha256sum -c /tmp/preserved
fi
echo "Ubuntu 22.04 OpenSSH $scenario passed"
