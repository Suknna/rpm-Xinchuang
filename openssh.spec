# ============================================================================
# OpenSSH portable RPM spec — built on official UBI7 / UBI8 (x86_64 only)
#
# 维护约定（与 CI 工作流保持一致）：
#   * OpenSSH 版本由 CI 自动升级：仅修改 spec 顶部 ver 宏定义，Source0 由宏生成。
#   * OpenSSL 版本固定且由维护者手动升级：修改 spec 顶部 ssl_ver 宏定义，
#     并同步更新 certs/checksums.yaml 中的 SHA256。
#     静态链接的 OpenSSL 不随系统 OpenSSL 变化，无需单独发布。
#   * 静态 OpenSSL（含 zlib），动态链接 glibc/PAM/Kerberos。
#   * 不构建图形 askpass（x11/gnome 均禁用）。
#
# 配置与主机密钥安全边界（勿改）：
#   * 严格配置保留：/etc 下不随包分发任何配置内容。配置路径以
#     %%config(noreplace) %%ghost 接管所有权（仅登记，payload 为空），
#     默认配置作为模板安装到 /usr/share/openssh/，%%post 仅在“目标缺失”时补齐。
#     因此任何升级路径 rpm 都不会改写/移动既有配置：无覆盖、无 .rpmnew、
#     无 .rpmsave；卸载同样不删除既有配置。
#   * spec 脚本段绝不生成/覆盖 /etc/ssh/ssh_host_*key；
#     缺失的密钥由 init 脚本首次启动时用 ssh-keygen -A 生成（仅生成缺失项）。
#   * 本包安装/升级绝不重启、停止或重载正在运行的 sshd。
# ============================================================================

# OpenSSH portable 版本（CI 自动更新；初始 10.0p1）
%global ver 10.0p1
# 静态链接的 OpenSSL 版本（仅手动更新）
%global ssl_ver 3.5.3
%global rel 1%{?dist}

# OpenSSH privilege separation requires a user & group ID
%global sshd_uid    74
%global sshd_gid    74

# 静态 OpenSSL 构建目录（%builddir 下，install_sw 安装到 -install 后缀目录；
# 注意 install_sw 在 64 位系统把库放到 lib64/ 子目录，%build 中动态探测）
%global ssldir %{_builddir}/openssl-%{ssl_ver}-install

Summary: The OpenSSH implementation of SSH protocol version 2.
Name: openssh
Version: %{ver}
Release: %{rel}
URL: https://www.openssh.com/portable.html
Source0: https://cloudflare.cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-%{ver}.tar.gz
Source1: https://github.com/openssl/openssl/releases/download/openssl-%{ssl_ver}/openssl-%{ssl_ver}.tar.gz
License: BSD
Group: Applications/Internet
BuildRoot: %{_tmppath}/%{name}-%{version}-buildroot
Obsoletes: ssh < %{version}

BuildRequires: make
BuildRequires: perl
BuildRequires: gcc
BuildRequires: glibc-devel
# PAM：动态链接（--with-pam）
BuildRequires: pam-devel
# 静态 OpenSSL 的 zlib 支持 + OpenSSH 二进制静态链接 zlib（不依赖系统 libz.so）
BuildRequires: zlib-devel
BuildRequires: zlib-static
%if 0%{?rhel} == 7
# OpenSSL 3.5.3 requires a C11 compiler; CentOS 7 stock GCC 4.8.5 is insufficient.
# devtoolset-9 由构建环境提供的 SCLo 仓库安装（UBI7 自带主源已 404）。
BuildRequires: devtoolset-9-gcc devtoolset-9-gcc-c++
%endif
# Kerberos5：动态链接
%global kerberos5 1
%if %{kerberos5}
BuildRequires: krb5-devel
BuildRequires: krb5-libs
%endif

%package clients
Summary: OpenSSH clients.
Requires: openssh = %{version}-%{release}
Group: Applications/Internet
Obsoletes: ssh-clients < %{version}

%package server
Summary: The OpenSSH server daemon.
Group: System Environment/Daemons
Obsoletes: ssh-server < %{version}
Requires: openssh = %{version}-%{release}, chkconfig >= 0.9
# init 脚本依赖 /etc/rc.d/init.d/functions
Requires: initscripts >= 5.20
Requires: /etc/pam.d/system-auth

%description
SSH (Secure SHell) is a program for logging into and executing
commands on a remote machine. SSH is intended to replace rlogin and
rsh, and to provide secure encrypted communications between two
untrusted hosts over an insecure network. X11 connections and
arbitrary TCP/IP ports can also be forwarded over the secure channel.

OpenSSH is OpenBSD's version of the last free version of SSH, bringing
it up to date in terms of security and features, as well as removing
all patented algorithms to separate libraries.

This package includes the core files necessary for both the OpenSSH
client and server. To make this package useful, you should also
install openssh-clients, openssh-server, or both.

Built with a statically linked OpenSSL (with zlib) and dynamically
linked glibc, PAM and Kerberos5. No graphical askpass programs.

%description clients
OpenSSH is a free version of SSH (Secure SHell), a program for logging
into and executing commands on a remote machine. This package includes
the clients necessary to make encrypted connections to SSH servers.
You'll also need to install the openssh package on OpenSSH clients.

%description server
OpenSSH is a free version of SSH (Secure SHell), a program for logging
into and executing commands on a remote machine. This package contains
the secure shell daemon (sshd). The sshd daemon allows SSH clients to
securely connect to your SSH server. You also need to have the openssh
package installed.

This package never restarts, stops or reloads a running sshd on
install or upgrade, never generates or overwrites existing host keys,
and preserves all existing configuration files under /etc/ssh.

%prep
%setup -q
tar -xzf %{SOURCE1} -C ..

%build
%if 0%{?rhel} == 7
. /opt/rh/devtoolset-9/enable
%endif

# 从源码构建静态 OpenSSL（含 zlib，不构建 shared/dso/tests），
# 安装到构建目录私有前缀，不触碰系统 OpenSSL。
pushd ../openssl-%{ssl_ver}
./config --prefix=%{ssldir} --openssldir=/etc/pki/tls \
	no-shared no-dso no-tests zlib
make -j$(nproc)
make install_sw
popd

# 静态链接 libcrypto/libssl/zlib；glibc/PAM/Kerberos 保持动态链接。
# install_sw 依据架构把静态库装到 lib/ 或 lib64/，这里探测后统一引用。
# zlib：仅含 libz.a 的专用 -L 目录在前，强制 -lz 解析到静态库。
unset CFLAGS LDFLAGS LIBS CPPFLAGS
SSL_LIB="$( [ -f %{ssldir}/lib64/libcrypto.a ] && echo %{ssldir}/lib64 || echo %{ssldir}/lib )"
ZLIB_A="$( [ -f %{_libdir}/libz.a ] && echo %{_libdir}/libz.a || echo /usr/lib/libz.a )"
mkdir -p %{_builddir}/static-zlib
ln -sf "$ZLIB_A" %{_builddir}/static-zlib/libz.a
export CFLAGS="-I%{ssldir}/include -fPIC"
export LDFLAGS="-L%{_builddir}/static-zlib -L$SSL_LIB -Wl,-z,relro -Wl,-z,now -Wl,-z,noexecstack -pie"
export LIBS="$SSL_LIB/libcrypto.a \
             $SSL_LIB/libssl.a \
             -ldl -lpthread -lz"
%configure \
	--sysconfdir=%{_sysconfdir}/ssh \
	--libexecdir=%{_libexecdir}/openssh \
	--datadir=%{_datadir}/openssh \
	--with-default-path=/usr/local/bin:/bin:/usr/bin \
	--with-superuser-path=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin \
	--with-privsep-path=%{_var}/empty/sshd \
	--mandir=%{_mandir} \
	--with-mantype=man \
	--disable-strip \
	--with-ssl-dir=%{ssldir} \
	--with-ssl-engine \
	--without-openssl-header-check \
	--with-pam \
%if %{kerberos5}
	--with-kerberos5 \
%endif

make

%install
rm -rf $RPM_BUILD_ROOT
mkdir -p -m755 $RPM_BUILD_ROOT%{_sysconfdir}/ssh
mkdir -p -m755 $RPM_BUILD_ROOT%{_libexecdir}/openssh
mkdir -p -m755 $RPM_BUILD_ROOT%{_var}/empty/sshd

make install DESTDIR=$RPM_BUILD_ROOT

install -d $RPM_BUILD_ROOT/etc/rc.d/init.d
install -d $RPM_BUILD_ROOT%{_libexecdir}/openssh

# 严格配置保留：/etc 下不随包分发内容。把上游 make install 放进
# buildroot /etc/ssh 的默认配置移作 /usr/share 模板；/etc 侧由 %ghost 登记。
install -d -m755 $RPM_BUILD_ROOT%{_datadir}/openssh
for f in sshd_config ssh_config moduli; do
	if [ -f "$RPM_BUILD_ROOT%{_sysconfdir}/ssh/$f" ]; then
		mv "$RPM_BUILD_ROOT%{_sysconfdir}/ssh/$f" \
		   "$RPM_BUILD_ROOT%{_datadir}/openssh/$f"
	fi
done
# 源码树兜底（防止上游安装策略变化导致模板缺失）
[ -f "$RPM_BUILD_ROOT%{_datadir}/openssh/sshd_config" ] || \
	install -m600 sshd_config.out "$RPM_BUILD_ROOT%{_datadir}/openssh/sshd_config"
[ -f "$RPM_BUILD_ROOT%{_datadir}/openssh/ssh_config" ] || \
	install -m644 ssh_config.out "$RPM_BUILD_ROOT%{_datadir}/openssh/ssh_config"
[ -f "$RPM_BUILD_ROOT%{_datadir}/openssh/moduli" ] || \
	install -m644 moduli "$RPM_BUILD_ROOT%{_datadir}/openssh/moduli"
# init 脚本与 PAM 配置同样只作为模板分发
install -m755 contrib/redhat/sshd.init $RPM_BUILD_ROOT%{_datadir}/openssh/sshd.init
install -m644 contrib/redhat/sshd.pam  $RPM_BUILD_ROOT%{_datadir}/openssh/sshd.pam

install -D -m 755 contrib/ssh-copy-id $RPM_BUILD_ROOT/usr/bin/ssh-copy-id
install -D -m 644 contrib/ssh-copy-id.1 $RPM_BUILD_ROOT/usr/share/man/man1/ssh-copy-id.1
perl -pi -e "s|$RPM_BUILD_ROOT||g" $RPM_BUILD_ROOT%{_mandir}/man*/*

%clean
rm -rf $RPM_BUILD_ROOT

%post
# 严格配置保留：仅当目标路径完全没有目录项（含悬空软链/FIFO）时才补模板；
# 任何已存在目录项（普通文件、软链、设备等）一律不触碰。
ensure_template() { # <mode> <template> <target>
	local mode="$1" tpl="$2" tgt="$3"
	if [ -e "$tgt" ] || [ -L "$tgt" ]; then return 0; fi
	if [ ! -f "$tpl" ]; then return 0; fi
	install -m "$mode" "$tpl" "$tgt"
}
ensure_template 0644 %{_datadir}/openssh/moduli %{_sysconfdir}/ssh/moduli || :

%post clients
# 严格配置保留：仅补缺失（同上，不触碰任何已存在目录项）。
ensure_template() { # <mode> <template> <target>
	local mode="$1" tpl="$2" tgt="$3"
	if [ -e "$tgt" ] || [ -L "$tgt" ]; then return 0; fi
	if [ ! -f "$tpl" ]; then return 0; fi
	install -m "$mode" "$tpl" "$tgt"
}
ensure_template 0644 %{_datadir}/openssh/ssh_config %{_sysconfdir}/ssh/ssh_config || :

%pre server
# 幂等创建 privsep 用户/组（已存在则忽略）
%{_sbindir}/groupadd -r -g %{sshd_gid} sshd 2>/dev/null || :
%{_sbindir}/useradd -d /var/empty/sshd -s /bin/false -u %{sshd_uid} \
	-g sshd -M -r sshd 2>/dev/null || :

%post server
# 严格配置保留：仅补缺失（同上，不触碰任何已存在目录项）。
ensure_template() { # <mode> <template> <target>
	local mode="$1" tpl="$2" tgt="$3"
	if [ -e "$tgt" ] || [ -L "$tgt" ]; then return 0; fi
	if [ ! -f "$tpl" ]; then return 0; fi
	install -m "$mode" "$tpl" "$tgt"
}
ensure_template 0600 %{_datadir}/openssh/sshd_config %{_sysconfdir}/ssh/sshd_config && \
	echo "sshd: default sshd_config installed from %{_datadir}/openssh/sshd_config" || :
ensure_template 0644 %{_datadir}/openssh/sshd.pam /etc/pam.d/sshd || :
ensure_template 0755 %{_datadir}/openssh/sshd.init /etc/rc.d/init.d/sshd || :

# 注册 SysV 服务：仅创建启动链接，绝不启动/重启 sshd。
/sbin/chkconfig --add sshd >/dev/null 2>&1 || :

# EL8：刷新 systemd 单元缓存（sysv 生成器接管 sshd.service；不会启动服务）
if [ -x /bin/systemctl ] && [ "$(ps -p 1 -o comm= 2>/dev/null)" = systemd ]; then
	/bin/systemctl daemon-reload >/dev/null 2>&1 || :
fi

# 说明：此处有意不做任何 host key 操作（不生成、不覆盖、不改权限）；
# 缺失密钥由 init 脚本首次启动时 ssh-keygen -A 生成，权限由其正确设置。

if [ "$1" -ge 2 ]; then
	# 升级场景：透明报告，不做任何自动重启/停止/重载。
	echo "openssh-server upgraded: this package did NOT restart the running sshd."
	echo "  Existing configuration files were NOT modified, moved or replaced."
	echo "  Restart manually when convenient:"
	echo "    EL7: service sshd restart    EL8: systemctl daemon-reload && systemctl restart sshd"
	if ls /etc/ssh/ssh_host_*key >/dev/null 2>&1; then
		if /usr/sbin/sshd -t >/dev/null 2>&1; then
			echo "  OK: preserved sshd_config passes the new sshd syntax check."
		else
			echo "  WARNING: 'sshd -t' FAILED against the preserved /etc/ssh/sshd_config."
			echo "  WARNING: a manual restart will fail until the config is fixed."
			echo "  WARNING: (a restart was NOT attempted by this package; older third-party"
			echo "  WARNING:  packages' scriptlets may behave differently.)"
		fi
	fi
fi

%postun server
# 升级（$1>=1）：什么都不做——旧进程继续运行，由管理员择机重启。
# 卸载（$1=0）：%preun 已停止服务，这里只清理状态文件。
if [ "$1" = 0 ]; then
	rm -f /var/lock/subsys/sshd
fi

%preun server
# 仅在真正卸载（非升级）时停止并注销服务
if [ "$1" = 0 ]; then
	/sbin/service sshd stop > /dev/null 2>&1 || :
	/sbin/chkconfig --del sshd > /dev/null 2>&1 || :
fi

%files
%defattr(-,root,root)
%doc CREDITS ChangeLog INSTALL LICENCE OVERVIEW README* PROTOCOL* TODO
%attr(0755,root,root) %{_bindir}/scp
%attr(0644,root,root) %{_mandir}/man1/scp.1*
%attr(0755,root,root) %dir %{_sysconfdir}/ssh
# /etc 下仅登记所有权（ghost），不携带内容：任何升级都不会触碰既有文件
%config(noreplace) %ghost %attr(0644,root,root) %{_sysconfdir}/ssh/moduli
# 默认配置以模板形式分发（%post 仅在缺失时补齐到 /etc）
%attr(0755,root,root) %dir %{_datadir}/openssh
%attr(0644,root,root) %{_datadir}/openssh/moduli
%attr(0755,root,root) %{_bindir}/ssh-keygen
%attr(0755,root,root) %{_bindir}/ssh-copy-id
%attr(0755,root,root) %{_libexecdir}/openssh/sshd-auth
%attr(0644,root,root) %{_mandir}/man1/ssh-copy-id.1*
%attr(0644,root,root) %{_mandir}/man1/ssh-keygen.1*
%attr(0755,root,root) %dir %{_libexecdir}/openssh
%attr(4711,root,root) %{_libexecdir}/openssh/ssh-keysign
%attr(0755,root,root) %{_libexecdir}/openssh/ssh-pkcs11-helper
%attr(0755,root,root) %{_libexecdir}/openssh/ssh-sk-helper
%attr(0644,root,root) %{_mandir}/man8/ssh-keysign.8*
%attr(0644,root,root) %{_mandir}/man8/ssh-pkcs11-helper.8*
%attr(0644,root,root) %{_mandir}/man8/ssh-sk-helper.8*

%files clients
%defattr(-,root,root)
%attr(0755,root,root) %{_bindir}/ssh
%attr(0644,root,root) %{_mandir}/man1/ssh.1*
%attr(0644,root,root) %{_mandir}/man5/ssh_config.5*
%config(noreplace) %ghost %attr(0644,root,root) %{_sysconfdir}/ssh/ssh_config
%attr(0644,root,root) %{_datadir}/openssh/ssh_config
%attr(2755,root,nobody) %{_bindir}/ssh-agent
%attr(0755,root,root) %{_bindir}/ssh-add
%attr(0755,root,root) %{_bindir}/ssh-keyscan
%attr(0755,root,root) %{_bindir}/sftp
%attr(0644,root,root) %{_mandir}/man1/ssh-agent.1*
%attr(0644,root,root) %{_mandir}/man1/ssh-add.1*
%attr(0644,root,root) %{_mandir}/man1/ssh-keyscan.1*
%attr(0644,root,root) %{_mandir}/man1/sftp.1*

%files server
%defattr(-,root,root)
%dir %attr(0111,root,root) %{_var}/empty/sshd
%attr(0755,root,root) %{_sbindir}/sshd
%attr(0755,root,root) %{_libexecdir}/openssh/sshd-session
%attr(0755,root,root) %{_libexecdir}/openssh/sftp-server
%attr(0644,root,root) %{_mandir}/man8/sshd.8*
%attr(0644,root,root) %{_mandir}/man5/moduli.5*
%attr(0644,root,root) %{_mandir}/man5/sshd_config.5*
%attr(0644,root,root) %{_mandir}/man8/sftp-server.8*
%attr(0755,root,root) %dir %{_sysconfdir}/ssh
# /etc 下仅登记所有权（ghost），不携带内容：任何升级都不会触碰既有文件
%config(noreplace) %ghost %attr(0600,root,root) %{_sysconfdir}/ssh/sshd_config
%config(noreplace) %ghost %attr(0644,root,root) /etc/pam.d/sshd
%config(noreplace) %ghost %attr(0755,root,root) /etc/rc.d/init.d/sshd
# 默认配置/脚本以模板形式分发（%post 仅在缺失时补齐到 /etc）
%attr(0600,root,root) %{_datadir}/openssh/sshd_config
%attr(0644,root,root) %{_datadir}/openssh/sshd.pam
%attr(0755,root,root) %{_datadir}/openssh/sshd.init

%changelog
* Sat Sep 12 2026 Suknna <Suknna@users.noreply.github.com> - 10.0p1-1
- Repackage for UBI7/UBI8 with static OpenSSL 3.5.3 (zlib enabled), dynamic
  glibc/PAM/Kerberos5, and no graphical askpass subpackages.
- Strict configuration preservation: /etc configs are owned via
  %config(noreplace) %ghost (no payload); stock defaults ship as templates in
  %%_datadir/openssh and %post only fills MISSING files. rpm therefore never
  overwrites, moves or deletes existing configuration on any upgrade path.
- Safety policy: scriptlets never generate/overwrite host keys (init script
  generates only missing keys via 'ssh-keygen -A' at first start); no
  automatic restart/stop/reload of a running sshd on install or upgrade;
  legacy triggers that restarted sshd or rewrote sshd_config were removed.
- Fix historically mis-dated changelog entry (3.0p1: 2000 -> 2001) so modern
  rpm's changelog order check passes.

* Mon Oct 16 2023 Fabio Pedretti <pedretti.fabio@gmail.com>
- Remove reference of dropped sshd.pam.old file
- Update openssl-devel dependency to require >= 1.1.1
- Build with --without-openssl elsewhere
- Remove ancient build6x config, intended for RHL 6.x
  (the distro predating Fedora, not RHEL)

* Thu Oct 28 2021 Damien Miller <djm@mindrot.org>
- Remove remaining traces of --with-md5-passwords

* Mon Jul 20 2020 Damien Miller <djm@mindrot.org>
- Add ssh-sk-helper and corresponding manual page.

* Sat Feb 10 2018 Darren Tucker <dtucker@dtucker.net>
- Update openssl-devel dependency to match current requirements.
- Handle Fedora >=6 openssl 1.0 compat libs.
- Remove SSH1 from description.
- Don't strip binaries at build time so that debuginfo package can be
  created.

* Sun Nov 16 2014 Nico Kadel-Garcia <nakdel@gmail.com>
- Add '--mandir' and '--with-mantype' for RHEL 5 compatibility
- Add 'dist' option to 'ver' so package names reflect OS at build time
- Always include x11-ssh-askpass tarball in SRPM
- Add openssh-x11-aspass BuildRequires for libXT-devel, imake, gtk2-devel
- Discard 'K5DIR' reporting, not usable inside 'mock' for RHEL 5 compatibility
- Discard obsolete '--with-rsh' configure option
- Update openssl-devel dependency to 0.9.8f, as found in autoconf

* Wed Jul 14 2010 Tim Rice <tim@multitalents.net>
- test for skip_x11_askpass (line 77) should have been for no_x11_askpass

* Mon Jun 2 2003 Damien Miller <djm@mindrot.org>
- Remove noip6 option. This may be controlled at run-time in client config
  file using new AddressFamily directive

* Mon May 12 2003 Damien Miller <djm@mindrot.org>
- Don't install profile.d scripts when not building with GNOME/GTK askpass
  (patch from bet@rahul.net)

* Tue Oct 01 2002 Damien Miller <djm@mindrot.org>
- Install ssh-agent setgid nobody to prevent ptrace() key theft attacks

* Mon Sep 30 2002 Damien Miller <djm@mindrot.org>
- Use contrib/ Makefile for building askpass programs

* Fri Jun 21 2002 Damien Miller <djm@ibs.com.au>
- Merge in spec changes from seba@iq.pl (Sebastian Pachuta)
- Add new {ssh,sshd}_config.5 manpages
- Add ssh-keysign program and remove setuid from ssh client

* Fri May 10 2002 Damien Miller <djm@ibs.com.au>
- Merge changes from RedHat, reorgansie a little
- Add Privsep user, group and directory

* Thu Mar  7 2002 Nalin Dahyabhai <nalin@redhat.com> 3.1p1-2
- bump and grind (through the build system)

* Thu Mar  7 2002 Nalin Dahyabhai <nalin@redhat.com> 3.1p1-1
- require sharutils for building (mindrot #137)
- require db1-devel only when building for 6.x (#55105), which probably won't
  work anyway (3.1 requires OpenSSL 0.9.6 to build), but the heck
- add Markus's patch to compile with OpenSSL 0.9.5a (from
  http://bugzilla.mindrot.org/show_bug.cgi?id=141) and apply it if we're
  building for 6.x

* Thu Mar  7 2002 Nalin Dahyabhai <nalin@redhat.com> 3.1p1-0
- update to 3.1p1

* Tue Mar  5 2002 Damien Miller <djm@mindrot.org> SNAP-20020305
- update to SNAP-20020305
- drop debug patch, fixed upstream

* Wed Feb 20 2002 Nalin Dahyabhai <nalin@redhat.com> SNAP-20020220
- update to SNAP-20020220 for testing purposes (you've been warned, if there's
  anything to be warned about, here's the place to be warned, GSSAPI patches
  won't apply, I don't mind)

* Wed Feb 13 2002 Nalin Dahyabhai <nalin@redhat.com> 3.0.2p1-3
- add patches from Simon Wilkinson and Nicolas Williams for GSSAPI key
  exchange, authentication, and named key support

* Wed Jan 23 2002 Nalin Dahyabhai <nalin@redhat.com> 3.0.2p1-2
- remove dependency on db1-devel, which has just been swallowed up whole
  by gnome-libs-devel

* Sat Dec 29 2001 Nalin Dahyabhai <nalin@redhat.com>
- adjust build dependencies so that build6x actually works right (fix
  from Hugo van der Kooij)

* Tue Dec  4 2001 Nalin Dahyabhai <nalin@redhat.com> 3.0.2p1-1
- update to 3.0.2p1

* Fri Nov 16 2001 Nalin Dahyabhai <nalin@redhat.com> 3.0.1p1-1
- update to 3.0.1p1

* Tue Nov 13 2001 Nalin Dahyabhai <nalin@redhat.com>
- update to current CVS (not for use in distribution)

* Thu Nov  8 2001 Nalin Dahyabhai <nalin@redhat.com> 3.0p1-1
- merge some of Damien Miller <djm@mindrot.org> changes from the upstream
  3.0p1 spec file and init script

* Wed Nov  7 2001 Nalin Dahyabhai <nalin@redhat.com>
- update to 3.0p1
- update to x11-askpass 1.2.4.1
- change build dependency on a file from pam-devel to the pam-devel package
- replace primes with moduli

* Thu Sep 27 2001 Nalin Dahyabhai <nalin@redhat.com> 2.9p2-9
- incorporate fix from Markus Friedl's advisory for IP-based authorization bugs

* Thu Sep 13 2001 Bernhard Rosenkraenzer <bero@redhat.com> 2.9p2-8
- Merge changes to rescue build from current sysadmin survival cd

* Thu Sep  6 2001 Nalin Dahyabhai <nalin@redhat.com> 2.9p2-7
- fix scp's server's reporting of file sizes, and build with the proper
  preprocessor define to get large-file capable open(), stat(), etc.
  (sftp has been doing this correctly all along) (#51827)
- configure without --with-ipv4-default on RHL 7.x and newer (#45987,#52247)
- pull cvs patch to fix support for /etc/nologin for non-PAM logins (#47298)
- mark profile.d scriptlets as config files (#42337)
- refer to Jason Stone's mail for zsh workaround for exit-hanging quasi-bug
- change a couple of log() statements to debug() statements (#50751)
- pull cvs patch to add -t flag to sshd (#28611)
- clear fd_sets correctly (one bit per FD, not one byte per FD) (#43221)

* Mon Aug 20 2001 Nalin Dahyabhai <nalin@redhat.com> 2.9p2-6
- add db1-devel as a BuildPrerequisite (noted by Hans Ecke)

* Thu Aug 16 2001 Nalin Dahyabhai <nalin@redhat.com>
- pull cvs patch to fix remote port forwarding with protocol 2

* Thu Aug  9 2001 Nalin Dahyabhai <nalin@redhat.com>
- pull cvs patch to add session initialization to no-pty sessions
- pull cvs patch to not cut off challengeresponse auth needlessly
- refuse to do X11 forwarding if xauth isn't there, handy if you enable
  it by default on a system that doesn't have X installed (#49263)

* Wed Aug  8 2001 Nalin Dahyabhai <nalin@redhat.com>
- don't apply patches to code we don't intend to build (spotted by Matt Galgoci)

* Mon Aug  6 2001 Nalin Dahyabhai <nalin@redhat.com>
- pass OPTIONS correctly to initlog (#50151)

* Wed Jul 25 2001 Nalin Dahyabhai <nalin@redhat.com>
- switch to x11-ssh-askpass 1.2.2

* Wed Jul 11 2001 Nalin Dahyabhai <nalin@redhat.com>
- rebuild in new environment

* Mon Jun 25 2001 Nalin Dahyabhai <nalin@redhat.com>
- disable the gssapi patch

* Mon Jun 18 2001 Nalin Dahyabhai <nalin@redhat.com>
- update to 2.9p2
- refresh to a new version of the gssapi patch

* Thu Jun  7 2001 Nalin Dahyabhai <nalin@redhat.com>
- change Copyright: BSD to License: BSD
- add Markus Friedl's unverified patch for the cookie file deletion problem
  so that we can verify it
- drop patch to check if xauth is present (was folded into cookie patch)
- don't apply gssapi patches for the errata candidate
- clear supplemental groups list at startup

* Fri May 25 2001 Nalin Dahyabhai <nalin@redhat.com>
- fix parsing of the new default sshd_config
- add a fix from Markus Friedl (via openssh-unix-dev) for ssh-keygen not
  dealing with comments right

* Thu May 24 2001 Nalin Dahyabhai <nalin@redhat.com>
- add in Simon Wilkinson's GSSAPI patch to give it a testing in-house, as it's
  a big departure from the upstream version

* Thu May  3 2001 Nalin Dahyabhai <nalin@redhat.com>
- finish marking strings in the init script for translation
- modify init script to source /etc/sysconfig/sshd and pass $OPTIONS to sshd
  at startup (change merged from openssh.com init script, originally by
  Pekka Savola)
- refuse to do X11 forwarding if xauth isn't there, handy if you enable
  it by default on a system that doesn't have X installed

* Wed May  2 2001 Nalin Dahyabhai <nalin@redhat.com>
- update to 2.9
- drop various patches that came from or went upstream or to or from CVS

* Wed Apr 18 2001 Nalin Dahyabhai <nalin@redhat.com>
- only require initscripts 5.00 on 6.2 (reported by Peter Bieringer)

* Sun Apr  8 2001 Preston Brown <pbrown@redhat.com>
- remove explicit openssl requirement, fixes builddistro issue
- make initscript stop() function wait until sshd really dead to avoid
  races in condrestart

* Mon Apr  2 2001 Nalin Dahyabhai <nalin@redhat.com>
- mention that challengereponse supports PAM, so disabling password doesn't
  limit users to pubkey and rsa auth (#34378)
- bypass the daemon() function in the init script and call initlog directly,
  because daemon() won't start a daemon it detects is already running (like
  open connections)
- require the version of openssl we had when we were built

* Fri Mar 23 2001 Nalin Dahyabhai <nalin@redhat.com>
- make do_pam_setcred() smart enough to know when to establish creds and
  when to reinitialize them
- add in a couple of other fixes from Damien for inclusion in the errata

* Thu Mar 22 2001 Nalin Dahyabhai <nalin@redhat.com>
- update to 2.5.2p2
- call setcred() again after initgroups, because the "creds" could actually
  be group memberships

* Tue Mar 20 2001 Nalin Dahyabhai <nalin@redhat.com>
- update to 2.5.2p1 (includes endianness fixes in the rijndael implementation)
- don't enable challenge-response by default until we find a way to not have
  too many userauth requests (we may make up to six pubkey and up to
  three password attempts as it is)
- remove build dependency on rsh to match openssh.com's packages more closely

* Sat Mar  3 2001 Nalin Dahyabhai <nalin@redhat.com>
- remove dependency on openssl -- would need to be too precise

* Fri Mar  2 2001 Nalin Dahyabhai <nalin@redhat.com>
- rebuild in new environment

* Mon Feb 26 2001 Nalin Dahyabhai <nalin@redhat.com>
- Revert the patch to move pam_open_session.
- Init script and spec file changes from Pekka Savola. (#28750)
- Patch sftp to recognize '-o protocol' arguments. (#29540)

* Thu Feb 22 2001 Nalin Dahyabhai <nalin@redhat.com>
- Chuck the closing patch.
- Add a trigger to add host keys for protocol 2 to the config file, now that
  configuration file syntax requires us to specify it with HostKey if we
  specify any other HostKey values, which we do.

* Tue Feb 20 2001 Nalin Dahyabhai <nalin@redhat.com>
- Redo patch to move pam_open_session after the server setuid()s to the user.
- Rework the nopam patch to use be picked up by autoconf.

* Mon Feb 19 2001 Nalin Dahyabhai <nalin@redhat.com>
- Update for 2.5.1p1.
- Add init script mods from Pekka Savola.
- Tweak the init script to match the CVS contrib script more closely.
- Redo patch to ssh-add to try to adding both identity and id_dsa to also try
  adding id_rsa.

* Fri Feb 16 2001 Nalin Dahyabhai <nalin@redhat.com>
- Update for 2.5.0p1.
- Use $RPM_OPT_FLAGS instead of -O when building gnome-ssh-askpass
- Resync with parts of Damien Miller's openssh.spec from CVS, including
  update of x11 askpass to 1.2.0.
- Only require openssl (don't prereq) because we generate keys in the init
  script now.

* Tue Feb 13 2001 Nalin Dahyabhai <nalin@redhat.com>
- Don't open a PAM session until we've forked and become the user (#25690).
- Apply Andrew Bartlett's patch for letting pam_authenticate() know which
  host the user is attempting a login from.
- Resync with parts of Damien Miller's openssh.spec from CVS.
- Don't expose KbdInt responses in debug messages (from CVS).
- Detect and handle errors in rsa_{public,private}_decrypt (from CVS).

* Wed Feb  7 2001 Trond Eivind Glomsrxd <teg@redhat.com>
- i18n-tweak to initscript.

* Tue Jan 23 2001 Nalin Dahyabhai <nalin@redhat.com>
- More gettextizing.
- Close all files after going into daemon mode (needs more testing).
- Extract patch from CVS to handle auth banners (in the client).
- Extract patch from CVS to fix compat weirdness.

* Fri Jan 19 2001 Nalin Dahyabhai <nalin@redhat.com>
- Finish with the gettextizing.

* Thu Jan 18 2001 Nalin Dahyabhai <nalin@redhat.com>
- Fix a bug in auth2-pam.c (#23877)
- Gettextize the init script.

* Wed Dec 20 2000 Nalin Dahyabhai <nalin@redhat.com>
- Incorporate a switch for using PAM configs for 6.x, just in case.

* Tue Dec  5 2000 Nalin Dahyabhai <nalin@redhat.com>
- Incorporate Bero's changes for a build specifically for rescue CDs.

* Wed Nov 29 2000 Nalin Dahyabhai <nalin@redhat.com>
- Don't treat pam_setcred() failure as fatal unless pam_authenticate() has
  succeeded, to allow public-key authentication after a failure with "none"
  authentication.  (#21268)

* Tue Nov 28 2000 Nalin Dahyabhai <nalin@redhat.com>
- Update to x11-askpass 1.1.1. (#21301)
- Don't second-guess fixpaths, which causes paths to get fixed twice. (#21290)

* Mon Nov 27 2000 Nalin Dahyabhai <nalin@redhat.com>
- Merge multiple PAM text messages into subsequent prompts when possible when
  doing keyboard-interactive authentication.

* Sun Nov 26 2000 Nalin Dahyabhai <nalin@redhat.com>
- Disable the built-in MD5 password support.  We're using PAM.
- Take a crack at doing keyboard-interactive authentication with PAM, and
  enable use of it in the default client configuration so that the client
  will try it when the server disallows password authentication.
- Build with debugging flags.  Build root policies strip all binaries anyway.

* Tue Nov 21 2000 Nalin Dahyabhai <nalin@redhat.com>
- Use DESTDIR instead of %%makeinstall.
- Remove /usr/X11R6/bin from the path-fixing patch.

* Mon Nov 20 2000 Nalin Dahyabhai <nalin@redhat.com>
- Add the primes file from the latest snapshot to the main package (#20884).
- Add the dev package to the prereq list (#19984).
- Remove the default path and mimic login's behavior in the server itself.

* Fri Nov 17 2000 Nalin Dahyabhai <nalin@redhat.com>
- Resync with conditional options in Damien Miller's .spec file for an errata.
- Change libexecdir from %%{_libexecdir}/ssh to %%{_libexecdir}/openssh.

* Tue Nov  7 2000 Nalin Dahyabhai <nalin@redhat.com>
- Update to OpenSSH 2.3.0p1.
- Update to x11-askpass 1.1.0.
- Enable keyboard-interactive authentication.

* Mon Oct 30 2000 Nalin Dahyabhai <nalin@redhat.com>
- Update to ssh-askpass-x11 1.0.3.
- Change authentication related messages to be private (#19966).

* Tue Oct 10 2000 Nalin Dahyabhai <nalin@redhat.com>
- Patch ssh-keygen to be able to list signatures for DSA public key files
  it generates.

* Thu Oct  5 2000 Nalin Dahyabhai <nalin@redhat.com>
- Add BuildRequires on /usr/include/security/pam_appl.h to be sure we always
  build PAM authentication in.
- Try setting SSH_ASKPASS if gnome-ssh-askpass is installed.
- Clean out no-longer-used patches.
- Patch ssh-add to try to add both identity and id_dsa, and to error only
  when neither exists.

* Mon Oct  2 2000 Nalin Dahyabhai <nalin@redhat.com>
- Update x11-askpass to 1.0.2. (#17835)
- Add BuildRequiress for /bin/login and /usr/bin/rsh so that configure will
  always find them in the right place. (#17909)
- Set the default path to be the same as the one supplied by /bin/login, but
  add /usr/X11R6/bin. (#17909)
- Try to handle obsoletion of ssh-server more cleanly.  Package names
  are different, but init script name isn't. (#17865)

* Wed Sep  6 2000 Nalin Dahyabhai <nalin@redhat.com>
- Update to 2.2.0p1. (#17835)
- Tweak the init script to allow proper restarting. (#18023)

* Wed Aug 23 2000 Nalin Dahyabhai <nalin@redhat.com>
- Update to 20000823 snapshot.
- Change authentication related messages to be private (#19966).

* Mon Jul 17 2000 Nalin Dahyabhai <nalin@redhat.com>
- Update to 2.1.1p4, which includes fixes for config file parsing problems.
- Move the init script back.
- Add Damien's quick fix for wackiness.

* Wed Jul 12 2000 Nalin Dahyabhai <nalin@redhat.com>
- Update to 2.1.1p3, which includes fixes for X11 forwarding and strtok().

* Thu Jul  6 2000 Nalin Dahyabhai <nalin@redhat.com>
- Move condrestart to server postun.
- Move key generation to init script.
- Actually use the right patch for moving the key generation to the init script.
- Clean up the init script a bit

* Wed Jul  5 2000 Nalin Dahyabhai <nalin@redhat.com>
- Fix X11 forwarding, from mail post by Chan Shih-Ping Richard.

* Sun Jul  2 2000 Nalin Dahyabhai <nalin@redhat.com>
- Update to 2.1.1p2
- Use of strtok() considered harmful.

* Sat Jul  1 2000 Nalin Dahyabhai <nalin@redhat.com>
- Get the build root out of the man pages.

* Thu Jun 29 2000 Nalin Dahyabhai <nalin@redhat.com>
- Add and use condrestart support in the init script.
- Add newer initscripts as a prereq.

* Tue Jun 27 2000 Nalin Dahyabhai <nalin@redhat.com>
- Build in new environment (release 2)
- Move -clients subpackage to Applications/Internet group

* Fri Jun  9 2000 Nalin Dahyabhai <nalin@redhat.com>
- Update to 2.2.1p1

* Sat Jun  3 2000 Nalin Dahyabhai <nalin@redhat.com>
- Patch to build with neither RSA nor RSAref.
- Miscellaneous FHS-compliance tweaks.
- Fix for possibly-compressed man pages.

* Wed Mar 15 2000 Damien Miller <djm@ibs.com.au>
- Updated for new location
- Updated for new gnome-ssh-askpass build

* Sun Dec 26 1999 Damien Miller <djm@mindrot.org>
- Added Jim Knoble's <jmknoble@pobox.com> askpass

* Mon Nov 15 1999 Damien Miller <djm@mindrot.org>
- Split subpackages further based on patch from jim knoble <jmknoble@pobox.com>

* Sat Nov 13 1999 Damien Miller <djm@ibs.com.au>
- Added 'Obsoletes' directives

* Tue Nov 09 1999 Damien Miller <djm@ibs.com.au>
- Use make install
- Subpackages

* Mon Nov 08 1999 Damien Miller <djm@ibs.com.au>
- Added links for slogin
- Fixed perms on manpages

* Sat Oct 30 1999 Damien Miller <djm@ibs.com.au>
- Renamed init script

* Fri Oct 29 1999 Damien Miller <djm@ibs.com.au>
- Back to old binary names

* Thu Oct 28 1999 Damien Miller <djm@ibs.com.au>
- Use autoconf
- New binary names

* Wed Oct 27 1999 Damien Miller <djm@ibs.com.au>
- Initial RPMification, based on Jan "Yenya" Kasprzak's <kas@fi.muni.cz> spec.
