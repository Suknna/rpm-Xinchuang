#!/usr/bin/env bash
# Metadata, complete subpackage set, checksums, ELF and service/config gates.
set -euo pipefail
export LC_ALL=C
dir="$(realpath "${1:?usage: verify-debs.sh <artifact-dir> <version>}")"
version="${2:?missing version}"
(cd "$dir" && sha256sum -c SHA256SUMS)
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
python3 - "$dir" "$version" <<'PY'
import json, pathlib, re, subprocess, sys
root, version = pathlib.Path(sys.argv[1]), sys.argv[2]
metadata = json.loads((root / 'build.json').read_text())
assert metadata['package'] == 'openssh' and metadata['platform'] == 'ubuntu2204'
assert metadata['version'] == version and metadata['architecture'] == 'amd64'
assert re.fullmatch(r'\d+ubuntu22\.04', metadata['release'])
assert metadata['deb_version'] == '1:' + version + '-' + metadata['release']
expected = {'openssh-client', 'openssh-server', 'openssh-sftp-server'}
seen = set()
for path in root.glob('*.deb'):
    values = [subprocess.check_output(['dpkg-deb', '-f', str(path), field], text=True).strip()
              for field in ('Package', 'Version', 'Architecture')]
    package, deb_version, arch = values
    assert package in expected and package not in seen, values
    assert deb_version == metadata['deb_version'] and arch == 'amd64', values
    assert path.name == f'{package}_{version}-{metadata["release"]}_amd64.deb'
    seen.add(package)
assert seen == expected, seen
lines = (root / 'SHA256SUMS').read_text().splitlines()
names = [re.fullmatch(r'[0-9a-f]{64}  \./([^/]+\.deb)', line)[1] for line in lines]
assert len(names) == 3 and set(names) == {p.name for p in root.glob('*.deb')}
PY
for deb in "$dir"/*.deb; do
    dpkg-deb -x "$deb" "$tmp/root"
done
[ ! -d "$tmp/root/etc" ] || { echo 'Unexpected /etc payload' >&2; exit 1; }
for binary in usr/bin/ssh usr/sbin/sshd usr/lib/openssh/sshd-session usr/lib/openssh/sshd-auth usr/lib/openssh/sftp-server; do
    test -x "$tmp/root/$binary"
    readelf -h "$tmp/root/$binary" | grep 'Advanced Micro Devices X86-64' >/dev/null
done
readelf -d "$tmp/root/usr/lib/openssh/sshd-session" | grep 'libpam.so' >/dev/null
grep -q '^Type=simple$' "$tmp/root/lib/systemd/system/ssh.service"
test -f "$tmp/root/lib/systemd/system/ssh.socket"
test -f "$tmp/root/lib/systemd/system/ssh@.service"
grep -q '^UsePAM yes$' "$tmp/root/usr/share/openssh/sshd_config"
grep -q '^@include common-auth$' "$tmp/root/usr/share/openssh/sshd.pam"
echo 'Ubuntu 22.04 DEB quality gates passed'
