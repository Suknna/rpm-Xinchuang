#!/usr/bin/env bash
# Run from an uploaded portal/ directory on a Caddy + systemd host.
set -euo pipefail
if [ "$(id -u)" != 0 ]; then
    echo 'Run this installer as root.' >&2
    exit 1
fi
SOURCE="$(cd "$(dirname "$0")" && pwd)"
command -v caddy >/dev/null
command -v python3 >/dev/null
command -v curl >/dev/null
test -f /etc/caddy/Caddyfile
# Preparation must finish before switching the existing authenticated site.
if ! getent passwd rpm-portal >/dev/null; then
    useradd --system --home-dir /data/dist/private --shell /sbin/nologin rpm-portal
fi
install -d -m 0755 /data/dist /data/dist/app /data/dist/public
install -d -o rpm-portal -g rpm-portal -m 0700 /data/dist/private
install -d -o rpm-portal -g rpm-portal -m 0755 /data/download /data/dist/public/data
install -m 0644 "$SOURCE/sync.py" "$SOURCE/receive.py" "$SOURCE/requirements.txt" /data/dist/app/
install -m 0644 "$SOURCE/deploy/Caddy.routes" /data/dist/app/Caddy.routes
install -m 0644 "$SOURCE/public/"* /data/dist/public/
if [ ! -f /data/dist/private/config.yaml ]; then
    install -o rpm-portal -g rpm-portal -m 0600 "$SOURCE/config.example.yaml" /data/dist/private/config.yaml
fi
if [ ! -x /data/dist/venv/bin/python ]; then
    python3 -m venv /data/dist/venv
fi
/data/dist/venv/bin/python -m pip install --disable-pip-version-check -r "$SOURCE/requirements.txt"
install -m 0644 "$SOURCE/deploy/rpm-portal-sync.service" "$SOURCE/deploy/rpm-portal-sync.timer" /etc/systemd/system/
python3 - <<'PY'
from pathlib import Path
import datetime
import os
import re
import subprocess

path = Path('/etc/caddy/Caddyfile')
original = path.read_text()
directive = 'import /data/dist/app/Caddy.routes'
if directive not in original:
    # Refuse to guess about other virtual hosts or routing layouts.
    modified, count = re.subn(r'(?m)^\s*root \* /data/?\s*\n\s*file_server browse\s*$', '\n    ' + directive, original)
    if count != 1:
        raise SystemExit('Expected one /data file_server browse block. Add the Caddy.routes import inside your authenticated site, then rerun.')
    backup = Path('/var/backups/rpm-portal-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, mode=0o700)
    (backup / 'Caddyfile').write_text(original)
    candidate = path.with_name('Caddyfile.portal-candidate')
    candidate.write_text(modified)
    try:
        subprocess.run(['caddy', 'validate', '--config', str(candidate), '--adapter', 'caddyfile'], check=True)
        os.replace(candidate, path)
        try:
            subprocess.run(['systemctl', 'reload', 'caddy'], check=True)
        except subprocess.CalledProcessError:
            path.write_text(original)
            subprocess.run(['systemctl', 'reload', 'caddy'], check=True)
            raise
    finally:
        candidate.unlink(missing_ok=True)
    # Move on the same filesystem, avoiding a duplicate of large existing ISOs.
    # Old content becomes private only after the new routes have been loaded.
    legacy = backup / 'legacy'
    legacy.mkdir()
    for item in Path('/data').iterdir():
        if item.name not in ('dist', 'download'):
            item.rename(legacy / item.name)
    print('Previous site and files saved to:', backup)
else:
    subprocess.run(['caddy', 'validate', '--config', str(path)], check=True)
    subprocess.run(['systemctl', 'reload', 'caddy'], check=True)
PY
systemctl daemon-reload
systemctl enable --now rpm-portal-sync.timer
systemctl start --no-block rpm-portal-sync.service
echo 'Portal installed. Inspect: journalctl -u rpm-portal-sync.service; systemctl status rpm-portal-sync.timer'
