#!/usr/bin/env bash
# Called only after a successful clean-container installation receipt.
set -euo pipefail
dir="${1:?missing artifact directory}"
version="${2:?missing version}"
bash "$(dirname "$0")/verify-debs.sh" "$dir" "$version"
release="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["release"])' "$dir/build.json")"
tag="openssh-ubuntu2204-$version-$release"
echo "tag=$tag" >> "${GITHUB_OUTPUT:?missing GITHUB_OUTPUT}"
files=("$dir/"*.deb "$dir/SHA256SUMS" "$dir/SOURCE-SHA256SUM" "$dir/build.json" "$dir/changelog")
if gh release view "$tag" >/dev/null 2>&1; then
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    gh release download "$tag" --dir "$tmp"
    for file in "${files[@]}"; do cmp "$file" "$tmp/$(basename "$file")"; done
else
    gh release create "$tag" "${files[@]}" \
        --title "OpenSSH $version DEB (Ubuntu 22.04, amd64)" \
        --notes 'Ubuntu 22.04 amd64 原生升级包：openssh-client、openssh-server、openssh-sftp-server。官方上游源码经固定 release key 验签；通过上游 regress、DEB 门禁和五场景安装验证。动态链接 Ubuntu 系统 OpenSSL/zlib/PAM/Kerberos。保留已有配置与 host key，安装/升级不主动重启 SSH。下载全部 deb 与 SHA256SUMS，先执行 sha256sum -c SHA256SUMS，再 sudo apt install ./*.deb。验证配置后手动 systemctl restart ssh；首次启动由服务生成缺失密钥。详细说明见 README。'
fi
