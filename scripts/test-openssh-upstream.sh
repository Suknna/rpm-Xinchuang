#!/usr/bin/env bash
# Run OpenSSH's own regress suite on the binaries built by rpmbuild.
# Invoked only inside an ephemeral UBI build container, never on the host.
set -euo pipefail

el="${1:?usage: test-openssh-upstream.sh <el7|el8> <build-tree>}"
build="${2:?missing OpenSSH build tree}"
source "${SRC_DIR:-/src}/scripts/repos-common.sh"
"configure_repos_$el"
install_build_deps "$el" "${SRC_DIR:-/src}/spec/openssh.spec"
if [ "$el" = el7 ]; then
  yum -y -q install openssh-clients
else
  dnf -y -q install openssh-clients
fi
# Upstream's regress/sshd needs the privsep account but does not start a system service.
getent group sshd >/dev/null || groupadd -r -g 74 sshd
id sshd >/dev/null 2>&1 || useradd -r -u 74 -g sshd -d /var/empty/sshd -s /sbin/nologin -M sshd
mkdir -p /var/empty/sshd
if [ "$el" = el7 ]; then
  set +u
  . /opt/rh/devtoolset-9/enable
  set -u
fi
cd "$build"
make tests
