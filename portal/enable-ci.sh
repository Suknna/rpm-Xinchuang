#!/usr/bin/env bash
# Install a dedicated public key; the private key belongs in GitHub Secrets.
set -euo pipefail
if [ "$(id -u)" != 0 ] || [ "$#" != 1 ]; then
    echo 'Usage (as root): bash portal/enable-ci.sh /path/to/dedicated-key.pub' >&2
    exit 1
fi
test -f /data/dist/app/receive.py
ssh-keygen -lf "$1" >/dev/null
install -d -o rpm-portal -g rpm-portal -m 0700 /data/dist/private/.ssh
python3 - "$1" <<'PY'
from pathlib import Path
import re
import sys

key = Path(sys.argv[1]).read_text().strip()
if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+={0,3}(?: [^\n]*)?', key):
    raise SystemExit('A dedicated ed25519 public key is required')
path = Path('/data/dist/private/.ssh/authorized_keys')
lines = path.read_text().splitlines() if path.exists() else []
lines = [line for line in lines if not line.endswith(' rpm-portal-ci')]
restricted = 'restrict,command="/data/dist/venv/bin/python /data/dist/app/receive.py" '
lines.append(restricted + ' '.join(key.split()[:2]) + ' rpm-portal-ci')
path.write_text('\n'.join(lines) + '\n')
(path.parent.parent / 'ci-key.pub').write_text(' '.join(key.split()[:2]) + ' rpm-portal-ci\n')
PY
chown rpm-portal:rpm-portal /data/dist/private/.ssh/authorized_keys
chmod 0600 /data/dist/private/.ssh/authorized_keys
# sshd executes even a forced command through the account shell. Password login
# remains locked; the installed key disallows PTY, forwarding and arbitrary exec.
usermod --shell /bin/sh rpm-portal
echo 'Restricted CI key installed.'
