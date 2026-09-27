Name: bash
%global debug_package %{nil}
Version: 5.3
Release: 1%{?dist}
Summary: The GNU Bourne Again shell
License: GPLv3+
URL: https://www.gnu.org/software/bash/
Source0: https://ftp.gnu.org/gnu/bash/bash-%{version}.tar.gz
Source1: dot-bashrc
Source2: dot-bash_profile
Source3: dot-bash_logout
BuildRequires: gcc make bison texinfo ncurses-devel
Requires: filesystem >= 3
Provides: /bin/bash
Provides: /bin/sh

%description
Bash is a shell compatible with the Bourne shell and includes interactive
features from the Korn shell and C shell.

%package devel
Summary: Development headers for bash
Requires: %{name} = %{version}-%{release}

%description devel
Headers for applications embedding bash builtins.

%package doc
Summary: Documentation for bash
Requires: %{name} = %{version}-%{release}

%description doc
Additional Bash documentation.

%prep
%setup -q

%build
%configure --with-bash-malloc=no --without-bash-malloc
make %{?_smp_mflags}

%check
LC_ALL=C make check

%install
%make_install
make install-headers DESTDIR=%{buildroot}
install -d -m 755 %{buildroot}%{_sysconfdir}/skel
install -m 644 %{SOURCE1} %{buildroot}%{_sysconfdir}/skel/.bashrc
install -m 644 %{SOURCE2} %{buildroot}%{_sysconfdir}/skel/.bash_profile
install -m 644 %{SOURCE3} %{buildroot}%{_sysconfdir}/skel/.bash_logout
ln -sf bash %{buildroot}%{_bindir}/sh
ln -sf bash.1 %{buildroot}%{_mandir}/man1/sh.1
rm -f %{buildroot}%{_infodir}/dir
%find_lang %{name}

%files -f %{name}.lang
%license COPYING
%{_bindir}/bash
%{_bindir}/sh
%{_bindir}/bashbug
%config(noreplace) %{_sysconfdir}/skel/.bashrc
%config(noreplace) %{_sysconfdir}/skel/.bash_profile
%config(noreplace) %{_sysconfdir}/skel/.bash_logout
%{_mandir}/man1/bash.1*
%{_mandir}/man1/bashbug.1*
%{_mandir}/man1/sh.1*
%{_infodir}/bash.info*
%{_libdir}/bash/

%files devel
%{_includedir}/bash/
%{_libdir}/pkgconfig/bash.pc

%files doc
%{_docdir}/bash/
