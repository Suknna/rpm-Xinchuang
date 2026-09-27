#!/usr/bin/env bash
# Check the PAM service files in the actual RPM payload, before publication.
set -euo pipefail

kind="${1:?usage: verify-pam-rpms.sh <openssh|sudo> <rpm-file>}"
rpmfile="${2:?missing RPM file}"
rpmfile="$(realpath "$rpmfile")"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

case "$kind" in
  openssh)
    file=/usr/share/openssh/sshd.pam
    (cd "$tmp" && rpm2cpio "$rpmfile" | cpio -id --quiet ".$file")
    (cd "$tmp" && rpm2cpio "$rpmfile" | cpio -id --quiet ./usr/share/openssh/sshd_config)
    test -s "$tmp$file" || { echo "missing SSH PAM template in RPM" >&2; exit 1; }
    rpm -qp --qf '[%{FILENAMES} %{FILEFLAGS}\n]' "$rpmfile" | \
      grep -qx '/etc/pam.d/sshd 81' || { echo "sshd PAM ghost declaration missing" >&2; exit 1; }
    grep -qx 'UsePAM yes' "$tmp/usr/share/openssh/sshd_config" || {
      echo "PAM is not enabled in the default sshd_config" >&2; exit 1;
    }
    ! grep -Eq '^[[:space:]]*[^#[:space:]].*pam_stack\.so' "$tmp$file" || {
      echo "obsolete pam_stack.so in SSH PAM template" >&2; exit 1;
    }
    grep -Eq '^auth[[:space:]]+substack[[:space:]]+password-auth$' "$tmp$file"
    grep -Eq '^account[[:space:]]+include[[:space:]]+password-auth$' "$tmp$file"
    grep -Eq '^session[[:space:]]+include[[:space:]]+password-auth$' "$tmp$file"
    # /etc/pam.d/sshd is a ghost; on a fresh install %post must copy this template.
    rpm -qp --scripts "$rpmfile" | grep -F 'ensure_template 0644 /usr/share/openssh/sshd.pam /etc/pam.d/sshd' >/dev/null
    ;;
  sudo)
    for service in sudo sudo-i; do
      (cd "$tmp" && rpm2cpio "$rpmfile" | cpio -id --quiet "./etc/pam.d/$service")
      test -s "$tmp/etc/pam.d/$service" || {
        echo "missing /etc/pam.d/$service payload in RPM" >&2; exit 1;
      }
      rpm -qp --qf '[%{FILENAMES} %{FILEFLAGS}\n]' "$rpmfile" | \
        grep -qx "/etc/pam.d/$service 17" || {
          echo "/etc/pam.d/$service is not config(noreplace)" >&2; exit 1;
        }
    done
    for phase in auth account password session; do
      grep -Eq "^$phase[[:space:]]+include[[:space:]]+system-auth$" "$tmp/etc/pam.d/sudo"
    done
    grep -Eq '^auth[[:space:]]+include[[:space:]]+sudo$' "$tmp/etc/pam.d/sudo-i"
    ;;
  *) echo "unsupported PAM package: $kind" >&2; exit 2 ;;
esac
echo "PAM payload OK: $rpmfile"
