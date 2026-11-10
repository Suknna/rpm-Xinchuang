Name: telnet
Version: 2.8
Release: 1%{?dist}
Summary: Telnet client from GNU inetutils
License: GPLv3+
URL: https://www.gnu.org/software/inetutils/
Source0: https://ftp.gnu.org/gnu/inetutils/inetutils-%{version}.tar.gz
Source1: telnet@.service
Source2: telnet.socket
BuildRequires: gcc make ncurses-devel systemd

%description
Telnet client built from the official GNU inetutils source.

%package server
Summary: Telnet server from GNU inetutils
Requires: systemd

%description server
Telnet server with a socket-activated systemd unit. This service is disabled
by default because Telnet traffic is unencrypted.

%prep
%setup -q -n inetutils-%{version}

%build
export CFLAGS="%{optflags} -Wformat"
%configure \
    --disable-ftpd --disable-inetd --disable-rexecd --disable-rlogind \
    --disable-rshd --disable-syslogd --disable-talkd --disable-tftpd \
    --disable-uucpd --disable-ftp --disable-dnsdomainname \
    --disable-hostname --disable-ping --disable-ping6 --disable-rcp \
    --disable-rexec --disable-rlogin --disable-rsh --disable-logger \
    --disable-talk --disable-tftp --disable-whois --disable-ifconfig \
    --disable-traceroute
make %{?_smp_mflags}

%check
make check

%install
%make_install
rm -f %{buildroot}%{_infodir}/dir
install -d %{buildroot}%{_unitdir}
install -m 644 %{SOURCE1} %{buildroot}%{_unitdir}/telnet@.service
install -m 644 %{SOURCE2} %{buildroot}%{_unitdir}/telnet.socket

%post server
systemctl daemon-reload >/dev/null 2>&1 || :

%postun server
systemctl daemon-reload >/dev/null 2>&1 || :

%files
%license COPYING
%{_bindir}/telnet
%{_mandir}/man1/telnet.1*
%{_infodir}/inetutils.info*

%files server
%{_libexecdir}/telnetd
%{_mandir}/man8/telnetd.8*
%{_unitdir}/telnet@.service
%{_unitdir}/telnet.socket
