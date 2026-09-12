#!/usr/bin/env bash
# yum/dnf 仓库配置（build 与 test 脚本共用，source 本文件）。
#
# 原则：
#   * 基础镜像必须是官方 UBI（registry.access.redhat.com/ubi7|ubi8，CI 固定 digest）；
#   * 仅补充免费镜像源解决 UBI 缺包问题（UBI7 主源已 404；UBI8 缺 pam-devel）；
#   * 所有源一律 gpgcheck=1（不禁用签名校验）；
#   * GPG 公钥固定在本仓库 certs/ 下（指纹已对照官方页面逐一核验，
#     见各 key 上方注释），不随源同渠道动态下载，杜绝“源与 key 一起被替换”。
#   * EL7 用 CentOS 7.9.2009 vault（RHEL 7.9 二进制兼容）；EL8 补 AlmaLinux 8。

# 固定公钥（certs/ 下文件）与官方公布指纹的对应关系：
#   centos7-key.asc           6341AB2753D78A78A7C27BB124C6A8A7F4A80EB5
#                             （CentOS-7 Key (CentOS 7 Official Signing Key)）
#   centos-sclo-sig-key.asc   C4DBD535B1FBBA14F8BA64A84EB84E71F2EE9D55
#                             （CentOS SoftwareCollections SIG，devtoolset 包签名）
#   almalinux8-key.asc        5E9B8F5617B5066CE92057C3488FCF7C3ABB34F8 (旧,已过期)
#                             BC5EDDCADF502C077F1582882AE81E8ACED7258B (现用)
#                             （与 repo.almalinux.org 内容逐字节一致）

EL7_VAULT="https://mirrors.aliyun.com/centos-vault/7.9.2009"
EL8_ALMA="https://mirrors.aliyun.com/almalinux/8"
CERTS="${RC_CERTS_DIR:-/src/certs}"
KEYRING="/etc/pki/rpm-gpg/rpm-xinchuang"

# 把仓库内固定公钥落位到系统 keyring 目录，返回 file:// gpgkey 列表
install_pinned_keys() {
	mkdir -p "$KEYRING"
	install -m 644 "$CERTS/centos7-key.asc"         "$KEYRING/CentOS-7"
	install -m 644 "$CERTS/centos-sclo-sig-key.asc" "$KEYRING/CentOS-SIG-SCLo"
	install -m 644 "$CERTS/almalinux8-key.asc"      "$KEYRING/AlmaLinux-8"
}

# EL7：UBI7 自带 repo 主源 404（EOL），禁用之，改用 vault（base/updates/extras/SCLo）
configure_repos_el7() {
	install_pinned_keys
	sed -i 's/^enabled=1/enabled=0/' /etc/yum.repos.d/ubi.repo
	cat > /etc/yum.repos.d/rpm-xinchuang-el7.repo <<REPOEOF
[rc-el7-base]
name=rpm-xinchuang el7 base (CentOS 7.9.2009 vault)
baseurl=${EL7_VAULT}/os/x86_64/
enabled=1
gpgcheck=1
gpgkey=file://${KEYRING}/CentOS-7

[rc-el7-updates]
name=rpm-xinchuang el7 updates (CentOS 7.9.2009 vault)
baseurl=${EL7_VAULT}/updates/x86_64/
enabled=1
gpgcheck=1
gpgkey=file://${KEYRING}/CentOS-7

[rc-el7-extras]
name=rpm-xinchuang el7 extras (CentOS 7.9.2009 vault)
baseurl=${EL7_VAULT}/extras/x86_64/
enabled=1
gpgcheck=1
gpgkey=file://${KEYRING}/CentOS-7

[rc-el7-sclo-rh]
name=rpm-xinchuang el7 SCLo rh / devtoolset (CentOS 7.9.2009 vault)
baseurl=${EL7_VAULT}/sclo/x86_64/rh/
enabled=1
gpgcheck=1
gpgkey=file://${KEYRING}/CentOS-7
       file://${KEYRING}/CentOS-SIG-SCLo
REPOEOF
}

# EL8：保留 UBI8 自带源，补充 AlmaLinux 8（BaseOS 提供 UBI 缺失的 pam-devel）
configure_repos_el8() {
	install_pinned_keys
	cat > /etc/yum.repos.d/rpm-xinchuang-el8.repo <<REPOEOF
[rc-el8-alma-base]
name=rpm-xinchuang el8 AlmaLinux BaseOS (supplement)
baseurl=${EL8_ALMA}/BaseOS/x86_64/os/
enabled=1
gpgcheck=1
gpgkey=file://${KEYRING}/AlmaLinux-8

[rc-el8-alma-appstream]
name=rpm-xinchuang el8 AlmaLinux AppStream (supplement)
baseurl=${EL8_ALMA}/AppStream/x86_64/os/
enabled=1
gpgcheck=1
gpgkey=file://${KEYRING}/AlmaLinux-8

[rc-el8-alma-powertools]
name=rpm-xinchuang el8 AlmaLinux PowerTools (supplement)
baseurl=${EL8_ALMA}/PowerTools/x86_64/os/
enabled=1
gpgcheck=1
gpgkey=file://${KEYRING}/AlmaLinux-8
REPOEOF
}

# 安装构建依赖（rpm-build、编译器、spec 声明的 BuildRequires）
install_build_deps() {
	local el="$1"
	if [ "$el" = el7 ]; then
		yum -y -q install rpm-build yum-utils gnupg2 curl cpio
		# EL7 系统 gcc 4.8 不支持 OpenSSL 3.5 所需的 C11，必须 devtoolset-9
		yum -y -q install devtoolset-9-gcc devtoolset-9-gcc-c++
		# OpenSSL 3.x 构建需要 IPC::Cmd / Time::Piece / Data::Dumper（EL7 基础 perl 不含）
		yum -y -q install "perl(IPC::Cmd)" "perl(Time::Piece)" "perl(Data::Dumper)"
		yum-builddep -y "$2" >/dev/null
	else
		dnf -y -q install rpm-build dnf-plugins-core gnupg2 curl cpio
		# OpenSSL 3.x 构建需要的 Perl 模块
		dnf -y -q install "perl(IPC::Cmd)" "perl(Time::Piece)" "perl(Data::Dumper)"
		dnf -y -q builddep "$2"
	fi
}
