%define patchlevel 1135
%if %{?WITH_SELINUX:0}%{!?WITH_SELINUX:1}
%define WITH_SELINUX 1
%endif
%define desktop_file 1
%if %{desktop_file}
%define desktop_file_utils_version 0.2.93
%endif

%define withnetbeans 1

%define withvimspell 0
%define withhunspell 0
%define withruby 1
%define withlua 1

%define python3 python3.6m
%define python3path %{_includedir}/%{python3}

%define baseversion 9.2
%define vimdir vim92

Summary: The VIM editor
URL:     http://www.vim.org/
Name: vim
Version: 9.2.1135
Release: 1%{?dist}
License: Vim and MIT
Source0: https://github.com/vim/vim/archive/refs/tags/v%{version}.tar.gz
Source1: vim.sh
Source2: vim.csh
Source4: virc
Source5: vimrc
Source7: gvim16.png
Source8: gvim32.png
Source9: gvim48.png
Source10: gvim64.png
Source11: Changelog.rpm
%if %{withvimspell}
Source13: vim-spell-files.tar.bz2
%endif
Source14: spec-template
Source15: spec-template.new
Source16: macros.vim
#Source17: ftplugin-spec.vim
#Source18: syntax-spec.vim


# migrate shebangs in script to /usr/bin/python3 and use python2 when necessary
# 1602727 - fixed several covscan issues and backported from upstream
# 1719812 - CVE-2019-12735 vim: vim/neovim: arbitrary command execution in getchar.c [rhel-8.1.0]
# 1605095 - vim: should not re-implement crypto
# 1842755 - CVE-2019-20807
# 2004975 - CVE-2021-3796 vim: use-after-free in nv_replace() in normal.c [rhel-8.6.0]
# 2004892 - CVE-2021-3778 vim: heap-based buffer overflow in utf_ptr2char() in mbyte.c [rhel-8.6.0]
# 2028341 - CVE-2021-3984 vim: illegal memory access when C-indenting could lead to Heap Buffer Overflow [rhel-8.6.0]
# 2028430 - CVE-2021-4019 vim: heap-based buffer overflow in find_help_tags() in src/help.c [rhel-8.6.0]
# CVE-2021-4193 vim: vulnerable to Out-of-bounds Read
# CVE-2021-4192 vim: vulnerable to Use After Free
# CVE-2022-0261 vim: Heap-based Buffer Overflow in block_insert() in src/ops.c
# CVE-2022-0318 vim: heap-based buffer overflow in utf_head_off() in mbyte.c
# CVE-2022-0359 vim: heap-based buffer overflow in init_ccline() in ex_getln.c
# CVE-2022-0392 vim: heap-based buffer overflow in getexmodeline() in ex_getln.c
# CVE-2022-0413 vim: use after free in src/ex_cmds.c
# CVE-2022-0361 vim: Heap-based Buffer Overflow in GitHub repository
# 2073391 - CVE-2022-1154 vim: use after free in utf_ptr2char
# CVE-2022-1621 vim: heap buffer overflow
# CVE-2022-1629 vim: buffer over-read
# CVE-2022-1785 vim: Out-of-bounds Write
# CVE-2022-1897 vim: out-of-bounds write in vim_regsub_both() in regexp.c
# CVE-2022-1927 vim: buffer over-read in utf_ptr2char() in mbyte.c
# RHEL-112003 CVE-2025-53905 vim: Vim path traversial
# RHEL-112007 CVE-2025-53906 vim: Vim path traversal
# RHEL-147935 CVE-2026-25749 vim: Heap Overflow in Vim
# 0001-patch-9.1.2132-security-buffer-overflow-in-helpfile-.patch
# 0001-patch-9.1.2133-Another-case-of-buffer-overflow-with-.patch
# RHEL-159620 CVE-2026-33412 vim: Vim: Arbitrary code execution via command injection in glob() function
# RHEL-155428 CVE-2026-28417 vim: Vim: Arbitrary code execution via OS command injection in the netrw plugin
# 3 patches:
# 0001-runtime-netrw-upstream-snapshot-of-v179.patch - introduces NetrwValidateHostname
# 0001-patch-9.2.0073-security-possible-command-injection-u.patch - CVE patch which sanitizes hostnames
# and reports invalid characters in SSH commands
# 0001-patch-9.2.0089-netrw-does-not-take-port-into-account.patch - include portnumber in hostname checking
# RHEL-155412 CVE-2026-28421 vim: Vim: Denial of service and information disclosure via crafted swap file
# 0001-patch-9.0.1477-crash-when-recovering-from-corrupted-.patch - adds check for max page count, which fixes
# crash which happens after applying 0001-patch-9.2.0077-security-Crash-when-recovering-a-corr.patch
# 0001-patch-9.2.0077-security-Crash-when-recovering-a-corr.patch - validates line count and page count from
# untrusted swap file before passing it to read and allocation functions
# RHEL-164956 CVE-2026-34982 vim: arbitrary command execution via modeline sandbox bypass
# https://redhat.atlassian.net/browse/RHEL-164956
# first two patches include modelineexpr implementation, which is required for security fix,
# and related tests
# https://github.com/vim/vim/commit/110289e78195b6d01e1e6ad26ad450de476d41c1
# https://github.com/vim/vim/commit/076073950c44ea0e35bc39d539dc7ab41bf9c7ec
# https://github.com/vim/vim/commit/75661a66a1db1e1f3f1245c615f13a7de44c0587
# https://github.com/vim/vim/commit/8c8772c6b321d4955c8f09926e3eda2b4cd83680
# RHEL-170126 CVE-2026-35177 vim: Vim zip.vim plugin: Arbitrary file overwrite via path traversal bypass
# https://redhat.atlassian.net/browse/RHEL-170126
# https://github.com/vim/vim/commit/7088926316d8
# https://github.com/vim/vim/commit/46f530e517bd
# https://github.com/vim/vim/commit/351a16c88f56
# Changes from upstream:
# - all three: use 'echohl Error' instead of s:Mess() (not in older zip.vim)
# - 9.2.0299: 'zipfile:' URI pattern instead of 'zipfile://' (older format);
#   dropped TODO comment and pi_zip.txt version line update
# - 9.2.0304: dropped Windows regex fix in zip#Write() (code path not present)
# RHEL-171485 CVE-2026-41411 vim: Command injection via backticks in tag files
# https://redhat.atlassian.net/browse/RHEL-171485
# https://github.com/vim/vim/commit/c78194e41d5a0b05b0ddf383b6679b1503f977fb
# RHEL-178234 CVE-2026-46483 vim: command injection in tar plugin via shellescape
# https://redhat.atlassian.net/browse/RHEL-178234
# https://github.com/vim/vim/commit/3fb5e58fbc63d86a3e65f1a141b0d67af2aa38a1
# Omitted src/version.c hunk and test file (Vim9 script not available in vim 8.0)
# RHEL-185863 CVE-2026-47167 vim: Code Injection in cucumber filetype plugin
# https://redhat.atlassian.net/browse/RHEL-185863
# https://github.com/vim/vim/commit/a65a52d684bc58535ad28a4ae824d22e76399934
# Changes from upstream:
# - stripped src/version.c patchlevel hunk
# - stripped 'Last Changes' header comments from cucumber.vim
# - adapted test: replaced CheckFeature with has() guard, used mkdir 'p' flag
#   with manual cleanup instead of 'pR' (not available in vim 8.0)
# RHEL-186656 CVE-2026-47162 vim: netrw code injection via NetrwBookHistSave()
# https://redhat.atlassian.net/browse/RHEL-186656
# https://github.com/vim/vim/commit/f08ab2f4d7d2947c8dd6c179ae08ee6146a2694b
# Adapted for vim 8.0: netrw.vim path differs, setline uses (cnt+lastline),
# stripped src/version.c and Last Change comment, created minimal test file
# RHEL-186648 CVE-2026-52858 possible code execution with python3complete
# https://redhat.atlassian.net/browse/RHEL-186648
# https://github.com/vim/vim/commit/4b850457e12e1a678dd209f2868154f7553cbf8d
# stripped src/version.c hunk and omitted v0.10 changelog comments
# https://github.com/vim/vim/commit/868ad62cb8bf8038322eab2badd31bd98b02b9df
# stripped src/version.c hunk
# RHEL-192102 CVE-2026-57456 possible code execution with python complete
# https://redhat.atlassian.net/browse/RHEL-192102
# https://github.com/vim/vim/commit/cce141c42740f122dd8486ae04e21c2a81016ba8
# stripped src/version.c hunk, omitted Last Updated comment changes, created minimal test file, adapted for vim 8.0
# RHEL-191365 CVE-2026-57455 Out-of-bounds write with soundfold()
# https://redhat.atlassian.net/browse/RHEL-191365
# https://github.com/vim/vim/commit/497f931f85339d175d7f69588dd249e8ccfed41b
# stripped src/version.c hunk, adapted test to vim 8.0 (no defer/D flag), added test to Make_all.mak
# RHEL-194055 CVE-2026-55693 out-of-bounds write in tree_count_words()
# https://redhat.atlassian.net/browse/RHEL-194055
# https://github.com/vim/vim/commit/a80874d9b84a01040e3d1aef2d4a59e1934dafb7
# stripped src/version.c hunk, adapted test for vim 8.0 (replaced blob
# literals with system printf, used mkdir 'p' with manual cleanup instead
# of 'pR', added test to Make_all.mak)
# RHEL-203873 CVE-2026-59858 arbitrary Ex command execution during C omni-completion
# https://redhat.atlassian.net/browse/RHEL-203873
# https://github.com/vim/vim/commit/6b611b0d15603c52ebdad17172b0232b4f65704e
# stripped src/version.c hunk, adapted ccomplete.vim fix for vim 8.0 legacy script syntax
# RHEL-242118 CVE-2026-73076 vimball: code execution via .VimballRecord file
# https://redhat.atlassian.net/browse/RHEL-242118
# https://github.com/vim/vim/commit/581a2f3ac9c6f96a26324f6b2c8c11415fd0d452
# stripped src/version.c hunk, omitted Date header change, kept v:version < 702 check
# (upstream bumped to 900 but RHEL 8 ships Vim 8.0 = version 800),
# rewrote $'...' string interpolation to legacy Vimscript for Vim 8.0 compatibility,
# do not use <script> in expand()
# RHEL-240376 CVE-2026-73078 code injection in netrw via bookmarks
# https://redhat.atlassian.net/browse/RHEL-240376
# https://github.com/vim/vim/commit/29c6fd090d4520592f8be7d9ec81190edf25ef69
# stripped src/version.c hunk, adapted path from runtime/pack/dist/opt/netrw/ to runtime/ for vim 8.0
# RHEL-242481 CVE-2026-73072 heap buffer overflow in set_sofo()
# https://redhat.atlassian.net/browse/RHEL-242481
# https://github.com/vim/vim/commit/05c41c922309c7a11b6ec2f124be66551c90d66a
# stripped src/version.c hunk, adapted test for vim 8.0 (no blob literal syntax, uses printf)
# RHEL-215657 CVE-2026-52859 out-of-bounds read in update_snapshot()
# https://redhat.atlassian.net/browse/RHEL-215657
# https://github.com/vim/vim/commit/63680c6d3d52477817b49cd1a66e7aabe8a7aa19
# stripped src/version.c hunk, adapted test for vim 8.0 (test_terminal.vim instead of test_terminal3.vim)
# RHEL-215681 CVE-2026-59857 Stack out-of-bounds write in spell_soundfold_sal()
# https://redhat.atlassian.net/browse/RHEL-215681
# https://github.com/vim/vim/commit/d22ff1c955ff87e8273210eae125aab0e85b6c30
# stripped src/version.c hunk
# RHEL-215662 CVE-2026-55892 Stack out-of-bounds write in dump_prefixes()
# https://redhat.atlassian.net/browse/RHEL-215662
# https://github.com/vim/vim/commit/8325b193bba5f01e7a7d8241f
# stripped src/version.c hunk, adapted test for vim 8.0 (replaced CheckUnix
# with has('unix') check, replaced blob literals with system printf, used
# mkdir 'p' with manual cleanup instead of 'pR')
# RHEL-253668 CVE-2026-28420 fix backported to make test suite passing
# https://redhat.atlassian.net/browse/RHEL-253668
# https://github.com/vim/vim/commit/bb6de2105


# gcc is no longer in buildroot by default
BuildRequires: gcc

BuildRequires: python2-devel python3-devel ncurses-devel gettext perl-devel
BuildRequires: perl-generators
BuildRequires: perl(ExtUtils::Embed) perl(ExtUtils::ParseXS)
BuildRequires: libacl-devel gpm-devel autoconf file
# needed for appstream-util
BuildRequires: libappstream-glib
%if %{WITH_SELINUX}
BuildRequires: libselinux-devel
%endif
%if "%{withruby}" == "1"
BuildRequires: ruby-devel ruby
%endif
%if "%{withlua}" == "1"
BuildRequires: lua-devel
%endif
%if %{desktop_file}
# for /usr/bin/desktop-file-install
Requires: desktop-file-utils
BuildRequires: desktop-file-utils >= %{desktop_file_utils_version}
%endif

%if %{withhunspell}
BuildRequires: hunspell-devel
%endif

Epoch: 2
Conflicts: filesystem < 3

%description
VIM (VIsual editor iMproved) is an updated and improved version of the
vi editor.  Vi was the first real screen-based editor for UNIX, and is
still very popular.  VIM improves on vi by adding new features:
multiple windows, multi-level undo, block highlighting and more.

%package common
Summary: The common files needed by any version of the VIM editor
Conflicts: man-pages-fr < 0.9.7-14
Conflicts: man-pages-it < 0.3.0-17
Conflicts: man-pages-pl < 0.24-2
Requires: %{name}-filesystem
# it conflicts with older version of vim-minimal during update because of manpage
# move
Conflicts: %{name}-minimal < 2:8.0.1428-4

%description common
VIM (VIsual editor iMproved) is an updated and improved version of the
vi editor.  Vi was the first real screen-based editor for UNIX, and is
still very popular.  VIM improves on vi by adding new features:
multiple windows, multi-level undo, block highlighting and more.  The
vim-common package contains files which every VIM binary will need in
order to run.

If you are installing vim-enhanced or vim-X11, you'll also need
to install the vim-common package.

%package spell
Summary: The dictionaries for spell checking. This package is optional
Requires: vim-common = %{epoch}:%{version}-%{release}

%description spell
This subpackage contains dictionaries for vim spell checking in
many different languages.

%package minimal
Summary: A minimal version of the VIM editor
Provides: vi = %{epoch}:%{version}-%{release}
Provides: %{_bindir}/vi
# it conflicts with older version of vim-common during update because of manpage
# move
Conflicts: %{name}-common < 2:8.0.1428-4

%description minimal
VIM (VIsual editor iMproved) is an updated and improved version of the
vi editor.  Vi was the first real screen-based editor for UNIX, and is
still very popular.  VIM improves on vi by adding new features:
multiple windows, multi-level undo, block highlighting and more. The
vim-minimal package includes a minimal version of VIM, which is
installed into /bin/vi for use when only the root partition is
present. NOTE: The online help is only available when the vim-common
package is installed.

%package enhanced
Summary: A version of the VIM editor which includes recent enhancements
Requires: vim-common = %{epoch}:%{version}-%{release} which
Provides: vim = %{epoch}:%{version}-%{release}
Provides: %{_bindir}/mergetool
Provides: %{_bindir}/vim
# suggest python3, python2, lua, ruby and perl packages because of their 
# embedded functionality in Vim/GVim
Suggests: python2 python2-libs 
Suggests: python3 python3-libs
Suggests: perl(:MODULE_COMPAT_%(eval "`%{__perl} -V:version`"; echo $version)) perl-libs perl-devel
%if "%{withruby}" == "1"
Suggests: ruby-libs ruby
%endif
%if "%{withlua}" == "1"
Suggests: lua-libs
%endif

%description enhanced
VIM (VIsual editor iMproved) is an updated and improved version of the
vi editor.  Vi was the first real screen-based editor for UNIX, and is
still very popular.  VIM improves on vi by adding new features:
multiple windows, multi-level undo, block highlighting and more.  The
vim-enhanced package contains a version of VIM with extra, recently
introduced features like Python and Perl interpreters.

Install the vim-enhanced package if you'd like to use a version of the
VIM editor which includes recently added enhancements like
interpreters for the Python and Perl scripting languages.  You'll also
need to install the vim-common package.

%package filesystem
Summary: VIM filesystem layout
BuildArch: noarch
%Description filesystem
This package provides some directories which are required by other
packages that add vim files, p.e.  additional syntax files or filetypes.

%package X11
Summary: The VIM version of the vi editor for the X Window System - GVim
# needed in configure script to have correct macros enabled (#1602807)
BuildRequires: gtk3-devel
BuildRequires: libX11-devel
BuildRequires: libSM-devel
BuildRequires: libXt-devel
BuildRequires: libXpm-devel
BuildRequires: libICE-devel

Requires: vim-common = %{epoch}:%{version}-%{release} libattr >= 2.4 gtk3 
Provides: gvim = %{epoch}:%{version}-%{release}
Provides: %{_bindir}/mergetool
Provides: %{_bindir}/gvim
Requires: perl(:MODULE_COMPAT_%(eval "`%{__perl} -V:version`"; echo $version))
Requires: hicolor-icon-theme
# suggest python3, python2, lua, ruby and perl packages because of their 
# embedded functionality in Vim/GVim
Suggests: python2 python2-libs 
Suggests: python3 python3-libs
Suggests: perl(:MODULE_COMPAT_%(eval "`%{__perl} -V:version`"; echo $version)) perl-libs perl-devel
%if "%{withruby}" == "1"
Suggests: ruby-libs ruby
%endif
%if "%{withlua}" == "1"
Suggests: lua-libs
%endif

%description X11
VIM (VIsual editor iMproved) is an updated and improved version of the
vi editor.  Vi was the first real screen-based editor for UNIX, and is
still very popular.  VIM improves on vi by adding new features:
multiple windows, multi-level undo, block highlighting and
more. VIM-X11 is a version of the VIM editor which will run within the
X Window System.  If you install this package, you can run VIM as an X
application with a full GUI interface and mouse support by command gvim.

Install the vim-X11 package if you'd like to try out a version of vi
with graphics and mouse capabilities.  You'll also need to install the
vim-common package.

%prep
%setup -q -n vim-%{version}

#use %%{__python3} macro for defining shebang in python3 tests

# fix rogue dependencies from sample code
chmod -x runtime/tools/mve.awk
%if %{withhunspell}
%endif
perl -pi -e "s,bin/nawk,bin/awk,g" runtime/tools/mve.awk

# install spell files
%if %{withvimspell}
%{__tar} xjf %{SOURCE13}
%endif

#patch3009 -p1


%build
export LDFLAGS="${LDFLAGS:-} -pthread"
%if 0%{?rhel} > 7
export RHEL_ALLOW_PYTHON2_FOR_BUILD=1
%endif

cd src
# The official release archive includes src/auto/configure; regenerating it
# needs Autoconf 2.71, which is not available in EL8.

sed -e "s+VIMRCLOC	= \$(VIMLOC)+VIMRCLOC	= /etc+" Makefile > Makefile.tmp
mv -f Makefile.tmp Makefile

export CFLAGS="%{optflags} -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64 -D_FORTIFY_SOURCE=2 -I%{python3path}"
export CXXFLAGS="%{optflags} -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64 -D_FORTIFY_SOURCE=2 -I%{python3path}"

cp -f os_unix.h os_unix.h.save
cp -f ex_cmds.c ex_cmds.c.save

perl -pi -e "s/vimrc/virc/"  os_unix.h
%configure --prefix=%{_prefix} --with-features=small --with-x=no \
  --enable-multibyte \
  --disable-netbeans \
%if %{WITH_SELINUX}
  --enable-selinux \
%else
  --disable-selinux \
%endif
  --disable-pythoninterp --disable-perlinterp --disable-tclinterp \
  --with-tlib=ncurses --enable-gui=no --disable-gpm --exec-prefix=/ \
  --enable-fips-warning \
  --with-compiledby="<bugzilla@redhat.com>" \
  --with-modified-by="<bugzilla@redhat.com>"

make VIMRCLOC=/etc VIMRUNTIMEDIR=/usr/share/vim/%{vimdir} %{?_smp_mflags}
cp vim minimal-vim
make clean

mv -f os_unix.h.save os_unix.h
mv -f ex_cmds.c.save ex_cmds.c

%configure --with-features=huge \
  --enable-pythoninterp=dynamic \
  --enable-python3interp=dynamic \
  --enable-perlinterp=dynamic \
  --disable-tclinterp --with-x=yes \
  --enable-xim --enable-multibyte \
  --with-tlib=ncurses \
  --enable-gtk3-check --enable-gui=gtk3 \
  --enable-fips-warning \
  --with-compiledby="<bugzilla@redhat.com>" --enable-cscope \
  --with-modified-by="<bugzilla@redhat.com>" \
%if "%{withnetbeans}" == "1"
  --enable-netbeans \
%else
  --disable-netbeans \
%endif
%if %{WITH_SELINUX}
  --enable-selinux \
%else
  --disable-selinux \
%endif
%if "%{withruby}" == "1"
  --enable-rubyinterp=dynamic \
%else
  --disable-rubyinterp \
%endif
%if "%{withlua}" == "1"
  --enable-luainterp=dynamic \
%else
  --disable-luainterp \
%endif
  --enable-termtruecolor

make VIMRCLOC=/etc VIMRUNTIMEDIR=/usr/share/vim/%{vimdir} %{?_smp_mflags}
cp vim gvim
make clean

%configure --prefix=%{_prefix} --with-features=huge \
 --enable-pythoninterp=dynamic \
 --enable-python3interp=dynamic \
 --enable-perlinterp=dynamic \
 --disable-tclinterp \
 --with-x=no \
 --enable-gui=no --exec-prefix=%{_prefix} --enable-multibyte \
 --enable-cscope --with-modified-by="<bugzilla@redhat.com>" \
 --with-tlib=ncurses \
  --enable-fips-warning \
 --with-compiledby="<bugzilla@redhat.com>" \
%if "%{withnetbeans}" == "1"
  --enable-netbeans \
%else
  --disable-netbeans \
%endif
%if %{WITH_SELINUX}
  --enable-selinux \
%else
  --disable-selinux \
%endif
%if "%{withruby}" == "1"
  --enable-rubyinterp=dynamic \
%else
  --disable-rubyinterp \
%endif
%if "%{withlua}" == "1"
  --enable-luainterp=dynamic \
%else
  --disable-luainterp \
%endif
  --enable-termtruecolor

make VIMRCLOC=/etc VIMRUNTIMEDIR=/usr/share/vim/%{vimdir} %{?_smp_mflags}
cp vim enhanced-vim

%check
# Test the final huge (non-GUI) binary while upstream runtime/doc still exists.
make -C src/testdir test_normal.res test_vim9_script.res

%install
mkdir -p %{buildroot}/%{_bindir}
mkdir -p %{buildroot}/%{_datadir}/%{name}/vimfiles/{after,autoload,colors,compiler,doc,ftdetect,ftplugin,indent,keymap,lang,plugin,print,spell,syntax,tutor}
mkdir -p %{buildroot}/%{_datadir}/%{name}/vimfiles/after/{autoload,colors,compiler,doc,ftdetect,ftplugin,indent,keymap,lang,plugin,print,spell,syntax,tutor}
cp -f %{SOURCE11} .
%if %{?fedora}%{!?fedora:0} >= 16 || %{?rhel}%{!?rhel:0} >= 6
cp -f %{SOURCE15} %{buildroot}/%{_datadir}/%{name}/vimfiles/template.spec
%else
cp -f %{SOURCE14} %{buildroot}/%{_datadir}/%{name}/vimfiles/template.spec
%endif
cp runtime/doc/uganda.txt LICENSE
# Those aren't Linux info files but some binary files for Amiga:
rm -f README*.info


cd src
# Adding STRIP=/bin/true, because Vim wants to strip the binary by himself -
# build system does it for us
make install DESTDIR=%{buildroot} BINDIR=%{_bindir} VIMRCLOC=/etc VIMRUNTIMEDIR=/usr/share/vim/%{vimdir} STRIP=/bin/true
make installgtutorbin  DESTDIR=%{buildroot} BINDIR=%{_bindir} VIMRCLOC=/etc VIMRUNTIMEDIR=/usr/share/vim/%{vimdir}
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/{16x16,32x32,48x48,64x64}/apps
install -m755 minimal-vim %{buildroot}%{_bindir}/vi
install -m755 enhanced-vim %{buildroot}%{_bindir}/vim
install -m755 gvim %{buildroot}%{_bindir}/gvim
install -p -m644 %{SOURCE7} \
   %{buildroot}%{_datadir}/icons/hicolor/16x16/apps/gvim.png
install -p -m644 %{SOURCE8} \
   %{buildroot}%{_datadir}/icons/hicolor/32x32/apps/gvim.png
install -p -m644 %{SOURCE9} \
   %{buildroot}%{_datadir}/icons/hicolor/48x48/apps/gvim.png
install -p -m644 %{SOURCE10} \
   %{buildroot}%{_datadir}/icons/hicolor/64x64/apps/gvim.png
#cp -f %{SOURCE17} %{buildroot}/%{_datadir}/%{name}/%{vimdir}/ftplugin/spec.vim
#cp -f %{SOURCE18} %{buildroot}/%{_datadir}/%{name}/%{vimdir}/syntax/spec.vim

# Register as an application to be visible in the software center
#
# NOTE: It would be *awesome* if this file was maintained by the upstream
# project, translated and installed into the right place during `make install`.
#
# See http://www.freedesktop.org/software/appstream/docs/ for more details.
#
mkdir -p $RPM_BUILD_ROOT%{_datadir}/metainfo
cat > $RPM_BUILD_ROOT%{_datadir}/metainfo/gvim.appdata.xml <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!-- Copyright 2014 Richard Hughes <richard@hughsie.com> -->
<!--
EmailAddress: Bram@moolenaar.net>
SentUpstream: 2014-05-22
-->
<application>
  <id type="desktop">gvim.desktop</id>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>Vim</project_license>
  <description>
    <p>
     Vim is an advanced text editor that seeks to provide the power of the
     de-facto Unix editor 'Vi', with a more complete feature set.
     It's useful whether you're already using vi or using a different editor.
    </p>
    <p>
     Vim is a highly configurable text editor built to enable efficient text
     editing.
     Vim is often called a "programmer's editor," and so useful for programming
     that many consider it an entire IDE. It is not just for programmers, though.
     Vim is perfect for all kinds of text editing, from composing email to
     editing configuration files.
    </p>
  </description>
  <screenshots>
    <screenshot type="default">
      <image>https://raw.githubusercontent.com/zdohnal/vim/zdohnal-screenshot/gvim16_9.png</image>
    </screenshot>
  </screenshots>
  <url type="homepage">http://www.vim.org/</url>
</application>
EOF

( cd %{buildroot}
  ln -sf vi ./%{_bindir}/rvi
  ln -sf vi ./%{_bindir}/rview
  ln -sf vi ./%{_bindir}/view
  ln -sf vi ./%{_bindir}/ex
  ln -sf vim ./%{_bindir}/rvim
  ln -sf vim ./%{_bindir}/vimdiff
  perl -pi -e "s,%{buildroot},," .%{_mandir}/man1/vim.1 .%{_mandir}/man1/vimtutor.1
  rm -f .%{_mandir}/man1/rvim.1
  cp -p .%{_mandir}/man1/vim.1 .%{_mandir}/man1/vi.1
  ln -sf vi.1.gz .%{_mandir}/man1/rvi.1.gz
  ln -sf vim.1.gz .%{_mandir}/man1/vimdiff.1.gz
  ln -sf gvim ./%{_bindir}/gview
  ln -sf gvim ./%{_bindir}/gex
  ln -sf gvim ./%{_bindir}/evim
  ln -sf gvim ./%{_bindir}/gvimdiff
  ln -sf gvim ./%{_bindir}/vimx
  %if "%{desktop_file}" == "1"
    mkdir -p %{buildroot}/%{_datadir}/applications
    desktop-file-install \
    %if 0%{?fedora} && 0%{?fedora} < 19
        --vendor fedora \
    %endif
        --dir %{buildroot}/%{_datadir}/applications \
        %{_builddir}/vim-%{version}/runtime/gvim.desktop
        # --add-category "Development;TextEditor;X-Red-Hat-Base" D\
  %else
    mkdir -p ./%{_sysconfdir}/X11/applnk/Applications
    cp %{_builddir}/vim-%{version}/runtime/gvim.desktop ./%{_sysconfdir}/X11/applnk/Applications/gvim.desktop
  %endif
  # ja_JP.ujis is obsolete, ja_JP.eucJP is recommended.
  ( cd ./%{_datadir}/%{name}/%{vimdir}/lang; \
    ln -sf menu_ja_jp.ujis.vim menu_ja_jp.eucjp.vim )
)

appstream-util validate-relax --nonet %{buildroot}/%{_datadir}/metainfo/*.appdata.xml

# Upstream now ships UTF-8 tutor files directly; the legacy conversion input
# names no longer exist.

# Dependency cleanups
chmod 644 %{buildroot}/%{_datadir}/%{name}/%{vimdir}/doc/vim2html.pl \
 %{buildroot}/%{_datadir}/%{name}/%{vimdir}/tools/*.pl \
 %{buildroot}/%{_datadir}/%{name}/%{vimdir}/tools/vim132
chmod 644 ../runtime/doc/vim2html.pl

mkdir -p %{buildroot}/%{_sysconfdir}/profile.d
cp %{SOURCE1} %{buildroot}/%{_sysconfdir}/profile.d/vim.sh
cp %{SOURCE2} %{buildroot}/%{_sysconfdir}/profile.d/vim.csh
chmod 0644 %{buildroot}/%{_sysconfdir}/profile.d/vim.*
install -p -m644 %{SOURCE4} %{buildroot}/%{_sysconfdir}/virc
install -p -m644 %{SOURCE5} %{buildroot}/%{_sysconfdir}/vimrc

# if Vim isn't built for Fedora, use redhat augroup
%if 0%{?rhel} >= 7
sed -i -e "s/augroup fedora/augroup redhat/" %{buildroot}/%{_sysconfdir}/vimrc
sed -i -e "s/augroup fedora/augroup redhat/" %{buildroot}/%{_sysconfdir}/virc
%endif

mkdir -p %{buildroot}%{_rpmconfigdir}/macros.d/
install -p -m644 %{SOURCE16} %{buildroot}%{_rpmconfigdir}/macros.d/

(cd ../runtime; rm -rf doc; ln -svf ../../vim/%{vimdir}/doc docs;) 
rm -f %{buildroot}/%{_datadir}/vim/%{vimdir}/macros/maze/maze*.c
rm -rf %{buildroot}/%{_datadir}/vim/%{vimdir}/tools
rm -rf %{buildroot}/%{_datadir}/vim/%{vimdir}/doc/vim2html.pl
rm -f %{buildroot}/%{_datadir}/vim/%{vimdir}/tutor/tutor.gr.utf-8~

# Remove not UTF-8 manpages
for i in pl.ISO8859-2 it.ISO8859-1 ru.KOI8-R fr.ISO8859-1; do
  rm -rf %{buildroot}/%{_mandir}/$i
done

# use common man1/ru directory
mv %{buildroot}/%{_mandir}/ru.UTF-8 %{buildroot}/%{_mandir}/ru

# Remove duplicate man pages
for i in fr.UTF-8 it.UTF-8 pl.UTF-8; do
  rm -rf %{buildroot}/%{_mandir}/$i
done

for i in rvim.1 gvim.1 gex.1 gview.1 vimx.1; do 
  echo ".so man1/vim.1" > %{buildroot}/%{_mandir}/man1/$i
done
echo ".so man1/vimdiff.1" > %{buildroot}/%{_mandir}/man1/gvimdiff.1
echo ".so man1/vimtutor.1" > %{buildroot}/%{_mandir}/man1/gvimtutor.1
mkdir -p %{buildroot}/%{_mandir}/man5
echo ".so man1/vim.1" > %{buildroot}/%{_mandir}/man5/vimrc.5
echo ".so man1/vi.1" > %{buildroot}/%{_mandir}/man5/virc.5
touch %{buildroot}/%{_datadir}/%{name}/vimfiles/doc/tags

# Refresh documentation helptags
%transfiletriggerin common -- %{_datadir}/%{name}/vimfiles/doc
%{_bindir}/vim -c ":helptags %{_datadir}/%{name}/vimfiles/doc" -c :q &> /dev/null || :

%transfiletriggerpostun common -- %{_datadir}/%{name}/vimfiles/doc
> %{_datadir}/%{name}/vimfiles/doc/tags || :
%{_bindir}/vim -c ":helptags %{_datadir}/%{name}/vimfiles/doc" -c :q &> /dev/null || :

%files common
%config(noreplace) %{_sysconfdir}/vimrc
%{!?_licensedir:%global license %%doc}
%license LICENSE
%doc README*
%doc runtime/docs
%doc Changelog.rpm
%dir %{_datadir}/%{name}
%{_datadir}/%{name}/vimfiles/template.spec
%dir %{_datadir}/%{name}/%{vimdir}
%{_datadir}/%{name}/%{vimdir}/LICENSE
%{_datadir}/%{name}/%{vimdir}/README.txt
%{_datadir}/%{name}/%{vimdir}/import
%{_datadir}/%{name}/%{vimdir}/lang/*/LC_MESSAGES/*.mo
%{_mandir}/*/man1/*
%{_datadir}/%{name}/%{vimdir}/autoload
%{_datadir}/%{name}/%{vimdir}/colors
%{_datadir}/%{name}/%{vimdir}/compiler
%{_datadir}/%{name}/%{vimdir}/pack
%{_datadir}/%{name}/%{vimdir}/doc
%{_datadir}/%{name}/%{vimdir}/*.vim
%{_datadir}/%{name}/%{vimdir}/ftplugin
%{_datadir}/%{name}/%{vimdir}/indent
%{_datadir}/%{name}/%{vimdir}/keymap
%{_datadir}/%{name}/%{vimdir}/lang/*.vim
%{_datadir}/%{name}/%{vimdir}/lang/*.txt
%dir %{_datadir}/%{name}/%{vimdir}/lang
%{_datadir}/%{name}/%{vimdir}/macros
%{_datadir}/%{name}/%{vimdir}/plugin
%{_datadir}/%{name}/%{vimdir}/print
%{_datadir}/%{name}/%{vimdir}/syntax
%{_datadir}/%{name}/%{vimdir}/tutor
%if ! %{withvimspell}
%{_datadir}/%{name}/%{vimdir}/spell
%endif
%lang(af) %{_datadir}/%{name}/%{vimdir}/lang/af
%lang(ca) %{_datadir}/%{name}/%{vimdir}/lang/ca
%lang(cs) %{_datadir}/%{name}/%{vimdir}/lang/cs
%lang(cs.cp1250) %{_datadir}/%{name}/%{vimdir}/lang/cs.cp1250
%lang(de) %{_datadir}/%{name}/%{vimdir}/lang/de
%lang(en_GB) %{_datadir}/%{name}/%{vimdir}/lang/en_GB
%lang(eo) %{_datadir}/%{name}/%{vimdir}/lang/eo
%lang(es) %{_datadir}/%{name}/%{vimdir}/lang/es
%lang(fi) %{_datadir}/%{name}/%{vimdir}/lang/fi
%lang(fr) %{_datadir}/%{name}/%{vimdir}/lang/fr
%lang(ga) %{_datadir}/%{name}/%{vimdir}/lang/ga
%lang(it) %{_datadir}/%{name}/%{vimdir}/lang/it
%lang(ja) %{_datadir}/%{name}/%{vimdir}/lang/ja
%lang(ja.euc-jp) %{_datadir}/%{name}/%{vimdir}/lang/ja.euc-jp
%lang(ja.sjis) %{_datadir}/%{name}/%{vimdir}/lang/ja.sjis
%lang(ko) %{_datadir}/%{name}/%{vimdir}/lang/ko
%lang(ko) %{_datadir}/%{name}/%{vimdir}/lang/ko.UTF-8
%lang(lv) %{_datadir}/%{name}/%{vimdir}/lang/lv
%lang(nb) %{_datadir}/%{name}/%{vimdir}/lang/nb
%lang(nl) %{_datadir}/%{name}/%{vimdir}/lang/nl
%lang(no) %{_datadir}/%{name}/%{vimdir}/lang/no
%lang(pl) %{_datadir}/%{name}/%{vimdir}/lang/pl
%lang(pl.UTF-8) %{_datadir}/%{name}/%{vimdir}/lang/pl.UTF-8
%lang(pl.cp1250) %{_datadir}/%{name}/%{vimdir}/lang/pl.cp1250
%lang(pt_BR) %{_datadir}/%{name}/%{vimdir}/lang/pt_BR
%lang(ru) %{_datadir}/%{name}/%{vimdir}/lang/ru
%lang(ru.cp1251) %{_datadir}/%{name}/%{vimdir}/lang/ru.cp1251
%lang(sk) %{_datadir}/%{name}/%{vimdir}/lang/sk
%lang(sk.cp1250) %{_datadir}/%{name}/%{vimdir}/lang/sk.cp1250
%lang(sr) %{_datadir}/%{name}/%{vimdir}/lang/sr
%lang(sv) %{_datadir}/%{name}/%{vimdir}/lang/sv
%lang(uk) %{_datadir}/%{name}/%{vimdir}/lang/uk
%lang(uk.cp1251) %{_datadir}/%{name}/%{vimdir}/lang/uk.cp1251
%lang(vi) %{_datadir}/%{name}/%{vimdir}/lang/vi
%lang(zh_CN) %{_datadir}/%{name}/%{vimdir}/lang/zh_CN
%lang(zh_CN.cp936) %{_datadir}/%{name}/%{vimdir}/lang/zh_CN.cp936
%lang(zh_TW) %{_datadir}/%{name}/%{vimdir}/lang/zh_TW
%lang(zh_CN.UTF-8) %{_datadir}/%{name}/%{vimdir}/lang/zh_CN.UTF-8
%lang(zh_TW.UTF-8) %{_datadir}/%{name}/%{vimdir}/lang/zh_TW.UTF-8
/%{_bindir}/xxd
%{_mandir}/man1/gex.*
%{_mandir}/man1/gview.*
%{_mandir}/man1/gvim*
%{_mandir}/man1/rvim.*
%{_mandir}/man1/vim.*
%{_mandir}/man1/vimdiff.*
%{_mandir}/man1/vimtutor.*
%{_mandir}/man1/vimx.*
%{_mandir}/man1/xxd.*
%{_mandir}/man5/vimrc.*
%lang(fr) %{_mandir}/fr/man1/*
%lang(it) %{_mandir}/it/man1/*
%lang(ja) %{_mandir}/ja/man1/*
%lang(pl) %{_mandir}/pl/man1/*
%lang(ru) %{_mandir}/ru/man1/*

%if %{withvimspell}
%files spell
%dir %{_datadir}/%{name}/%{vimdir}/spell
%{_datadir}/%{name}/vim70/spell/cleanadd.vim
%lang(af) %{_datadir}/%{name}/%{vimdir}/spell/af.*
%lang(am) %{_datadir}/%{name}/%{vimdir}/spell/am.*
%lang(bg) %{_datadir}/%{name}/%{vimdir}/spell/bg.*
%lang(ca) %{_datadir}/%{name}/%{vimdir}/spell/ca.*
%lang(cs) %{_datadir}/%{name}/%{vimdir}/spell/cs.*
%lang(cy) %{_datadir}/%{name}/%{vimdir}/spell/cy.*
%lang(da) %{_datadir}/%{name}/%{vimdir}/spell/da.*
%lang(de) %{_datadir}/%{name}/%{vimdir}/spell/de.*
%lang(el) %{_datadir}/%{name}/%{vimdir}/spell/el.*
%lang(en) %{_datadir}/%{name}/%{vimdir}/spell/en.*
%lang(eo) %{_datadir}/%{name}/%{vimdir}/spell/eo.*
%lang(es) %{_datadir}/%{name}/%{vimdir}/spell/es.*
%lang(fo) %{_datadir}/%{name}/%{vimdir}/spell/fo.*
%lang(fr) %{_datadir}/%{name}/%{vimdir}/spell/fr.*
%lang(ga) %{_datadir}/%{name}/%{vimdir}/spell/ga.*
%lang(gd) %{_datadir}/%{name}/%{vimdir}/spell/gd.*
%lang(gl) %{_datadir}/%{name}/%{vimdir}/spell/gl.*
%lang(he) %{_datadir}/%{name}/%{vimdir}/spell/he.*
%lang(hr) %{_datadir}/%{name}/%{vimdir}/spell/hr.*
%lang(hu) %{_datadir}/%{name}/%{vimdir}/spell/hu.*
%lang(id) %{_datadir}/%{name}/%{vimdir}/spell/id.*
%lang(it) %{_datadir}/%{name}/%{vimdir}/spell/it.*
%lang(ku) %{_datadir}/%{name}/%{vimdir}/spell/ku.*
%lang(la) %{_datadir}/%{name}/%{vimdir}/spell/la.*
%lang(lt) %{_datadir}/%{name}/%{vimdir}/spell/lt.*
%lang(lv) %{_datadir}/%{name}/%{vimdir}/spell/lv.*
%lang(mg) %{_datadir}/%{name}/%{vimdir}/spell/mg.*
%lang(mi) %{_datadir}/%{name}/%{vimdir}/spell/mi.*
%lang(ms) %{_datadir}/%{name}/%{vimdir}/spell/ms.*
%lang(nb) %{_datadir}/%{name}/%{vimdir}/spell/nb.*
%lang(nl) %{_datadir}/%{name}/%{vimdir}/spell/nl.*
%lang(nn) %{_datadir}/%{name}/%{vimdir}/spell/nn.*
%lang(ny) %{_datadir}/%{name}/%{vimdir}/spell/ny.*
%lang(pl) %{_datadir}/%{name}/%{vimdir}/spell/pl.*
%lang(pt) %{_datadir}/%{name}/%{vimdir}/spell/pt.*
%lang(ro) %{_datadir}/%{name}/%{vimdir}/spell/ro.*
%lang(ru) %{_datadir}/%{name}/%{vimdir}/spell/ru.*
%lang(rw) %{_datadir}/%{name}/%{vimdir}/spell/rw.*
%lang(sk) %{_datadir}/%{name}/%{vimdir}/spell/sk.*
%lang(sl) %{_datadir}/%{name}/%{vimdir}/spell/sl.*
%lang(sr) %{_datadir}/%{name}/%{vimdir}/spell/sr.*
%lang(sv) %{_datadir}/%{name}/%{vimdir}/spell/sv.*
%lang(sw) %{_datadir}/%{name}/%{vimdir}/spell/sw.*
%lang(tet) %{_datadir}/%{name}/%{vimdir}/spell/tet.*
%lang(th) %{_datadir}/%{name}/%{vimdir}/spell/th.*
%lang(tl) %{_datadir}/%{name}/%{vimdir}/spell/tl.*
%lang(tn) %{_datadir}/%{name}/%{vimdir}/spell/tn.*
%lang(uk) %{_datadir}/%{name}/%{vimdir}/spell/uk.*
%lang(yi) %{_datadir}/%{name}/%{vimdir}/spell/yi.*
%lang(yi-tr) %{_datadir}/%{name}/%{vimdir}/spell/yi-tr.*
%lang(zu) %{_datadir}/%{name}/%{vimdir}/spell/zu.*
%endif

%files minimal
%config(noreplace) %{_sysconfdir}/virc
%{_bindir}/ex
%{_bindir}/vi
%{_bindir}/view
%{_bindir}/rvi
%{_bindir}/rview
%{_mandir}/man1/vi.*
%{_mandir}/man1/ex.*
%{_mandir}/man1/rvi.*
%{_mandir}/man1/rview.*
%{_mandir}/man1/view.*
%{_mandir}/man5/virc.*

%files enhanced
%{_bindir}/vim
%{_bindir}/rvim
%{_bindir}/vimdiff
%{_bindir}/vimtutor
%config(noreplace) %{_sysconfdir}/profile.d/vim.*

%files filesystem
%{_rpmconfigdir}/macros.d/macros.vim
%dir %{_datadir}/%{name}/vimfiles
%dir %{_datadir}/%{name}/vimfiles/after
%dir %{_datadir}/%{name}/vimfiles/after/*
%dir %{_datadir}/%{name}/vimfiles/autoload
%dir %{_datadir}/%{name}/vimfiles/colors
%dir %{_datadir}/%{name}/vimfiles/compiler
%dir %{_datadir}/%{name}/vimfiles/doc
%ghost %{_datadir}/%{name}/vimfiles/doc/tags
%dir %{_datadir}/%{name}/vimfiles/ftdetect
%dir %{_datadir}/%{name}/vimfiles/ftplugin
%dir %{_datadir}/%{name}/vimfiles/indent
%dir %{_datadir}/%{name}/vimfiles/keymap
%dir %{_datadir}/%{name}/vimfiles/lang
%dir %{_datadir}/%{name}/vimfiles/plugin
%dir %{_datadir}/%{name}/vimfiles/print
%dir %{_datadir}/%{name}/vimfiles/spell
%dir %{_datadir}/%{name}/vimfiles/syntax
%dir %{_datadir}/%{name}/vimfiles/tutor

%files X11
%if "%{desktop_file}" == "1"
%{_datadir}/metainfo/*.appdata.xml
/%{_datadir}/applications/*
%exclude /%{_datadir}/applications/vim.desktop
%else
/%{_sysconfdir}/X11/applnk/*/gvim.desktop
%endif
%{_bindir}/gvimtutor
%{_bindir}/gvim
%{_bindir}/gvimdiff
%{_bindir}/gview
%{_bindir}/gex
%{_bindir}/vimtutor
%{_bindir}/vimx
%{_bindir}/evim
%{_mandir}/man1/evim.*
%{_datadir}/icons/hicolor/*/apps/*
%{_datadir}/icons/locolor/*/apps/*

%changelog
* Fri Sep 04 2026 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-31.7
- RHEL-253666 CVE-2026-28420 buffer overflow in terminal emulator

* Fri Sep 04 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-31.6
- RHEL-215662 CVE-2026-55892 vim: stack out-of-bounds write in
  dump_prefixes()

* Fri Sep 04 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-31.5
- RHEL-215681 CVE-2026-59857 vim: stack out-of-bounds write in
  spell_soundfold_sal()

* Fri Sep 04 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-31.4
- RHEL-215657 CVE-2026-52859 vim: out-of-bounds read in terminal
  cell.chars[] loop

* Wed Aug 19 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-31.3
- CVE-2026-73072 vim: heap buffer overflow in set_sofo()

* Wed Aug 19 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-31.2
- CVE-2026-73078 vim: code injection in netrw via bookmarks

* Sat Aug 15 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-31.1
- CVE-2026-73076 vim: code execution via .VimballRecord file

* Tue Jul 14 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-31
- RHEL-203873 CVE-2026-59858 vim: arbitrary Ex command execution in
  C omni-completion

* Mon Jul 13 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-30
- RHEL-194055 CVE-2026-55693 vim: out-of-bounds write in
  tree_count_words()

* Mon Jul 13 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-29
- RHEL-191365 CVE-2026-57455 vim: Out-of-bounds write with soundfold()

* Sat Jul 04 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-28
- RHEL-192102 CVE-2026-57456 vim: possible code execution with python
  complete via crafted docstrings

* Wed Jul 01 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-27
- RHEL-186656 CVE-2026-47162 vim: netrw code injection via NetrwBookHistSave
- RHEL-186648 CVE-2026-52858 vim: possible code execution with python3complete

* Tue Jun 30 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-26
- CVE-2026-47167 vim: Code Injection in cucumber filetype plugin

* Wed Jun 03 2026 RHEL Packaging Agent <redhat-ymir-agent@redhat.com> - 2:8.0.1763-25
- RHEL-178234 CVE-2026-46483 vim: command injection in tar plugin via
  shellescape

* Thu May 21 2026 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-24
- CVE-2026-41411 vim: Command injection via backticks in tag files

* Wed May 20 2026 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-23
- RHEL-170126 CVE-2026-35177 vim: Vim zip.vim plugin: Arbitrary file overwrite
  via path traversal bypass

* Fri Apr 17 2026 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-22.3
- Relates: RHEL-164956 vim: arbitrary command execution via modeline sandbox bypass

* Mon Apr 13 2026 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-22.2
- Resolves: RHEL-164956 vim: arbitrary command execution via modeline sandbox bypass

* Tue Mar 31 2026 Petr Dancak   <pdancak@redhat.com> - 2:8.0.1763-22.1
- RHEL-159620 CVE-2026-33412 vim: Vim: Arbitrary code execution via command injection in glob() function
- RHEL-155428 CVE-2026-28417 vim: Vim: Arbitrary code execution via OS command injection in the netrw plugin
- RHEL-155412 CVE-2026-28421 vim: Vim: Denial of service and information disclosure via crafted swap file

* Fri Feb 27 2026 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-22
- RHEL-147935 CVE-2026-25749 vim: Heap Overflow in Vim

* Wed Sep 17 2025 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-21
- RHEL-112003 CVE-2025-53905 vim: Vim path traversial
- RHEL-112007 CVE-2025-53906 vim: Vim path traversal

* Tue Jun 14 2022 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-19.4
- fix issue reported by covscan

* Mon Jun 13 2022 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-19.3
- CVE-2022-1785 vim: Out-of-bounds Write
- CVE-2022-1897 vim: out-of-bounds write in vim_regsub_both() in regexp.c
- CVE-2022-1927 vim: buffer over-read in utf_ptr2char() in mbyte.c

* Sat May 14 2022 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-19.2
- CVE-2022-1621 vim: heap buffer overflow
- CVE-2022-1629 vim: buffer over-read

* Sat Apr 09 2022 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-19.1
- CVE-2022-1154 vim: use after free in utf_ptr2char

* Tue Feb 08 2022 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-19
- CVE-2022-0361 vim: Heap-based Buffer Overflow in GitHub repository

* Mon Feb 07 2022 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-18
- CVE-2022-0392 vim: heap-based buffer overflow in getexmodeline() in ex_getln.c
- CVE-2022-0413 vim: use after free in src/ex_cmds.c

* Thu Jan 27 2022 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-18
- fix test suite after fix for CVE-2022-0318
- CVE-2022-0359 vim: heap-based buffer overflow in init_ccline() in ex_getln.c

* Wed Jan 12 2022 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-18
- CVE-2022-0261 vim: Heap-based Buffer Overflow in block_insert() in src/ops.c
- CVE-2022-0318 vim: heap-based buffer overflow in utf_head_off() in mbyte.c

* Wed Jan 12 2022 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-18
- CVE-2021-4193 vim: vulnerable to Out-of-bounds Read
- CVE-2021-4192 vim: vulnerable to Use After Free

* Fri Dec 03 2021 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-18
- 2028341 - CVE-2021-3984 vim: illegal memory access when C-indenting could lead to Heap Buffer Overflow [rhel-8.6.0]
- 2028430 - CVE-2021-4019 vim: heap-based buffer overflow in find_help_tags() in src/help.c [rhel-8.6.0]

* Tue Oct 26 2021 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-17
- 2016201 - CVE-2021-3872 vim: heap-based buffer overflow in win_redr_status() drawscreen.c [rhel-8.6.0]

* Thu Sep 23 2021 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-16
- 2004975 - CVE-2021-3796 vim: use-after-free in nv_replace() in normal.c [rhel-8.6.0]
- 2004892 - CVE-2021-3778 vim: heap-based buffer overflow in utf_ptr2char() in mbyte.c [rhel-8.6.0]

* Tue Jun 02 2020 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-15
- 1842755 - CVE-2019-20807

* Mon Feb 10 2020 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-14
- 1745476 - manpage of vim is garbled in Japanese locale

* Tue Jul 23 2019 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-13
- fixing covscan issues raised by previous commit

* Tue Jul 23 2019 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-12
- 1605095 - vim: should not re-implement crypto

* Fri Jun 14 2019 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-11
- 1719812 - CVE-2019-12735 vim: vim/neovim: arbitrary command execution in getchar.c [rhel-8.1.0]

* Thu Dec 06 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-10
- do not strip binaries before build system strips them

* Tue Nov 27 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-9
- 1602727 - Please review important issues found by covscan in "vim-8.0.1763-2.el8+7" package

* Fri Oct 19 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-8
- 1640919 - augroup fedora, test case failure: /CoreOS/vim/Regression/bz241308-use-augroup-for-rh-autocmds

* Tue Jul 24 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-7
- correcting license

* Thu Jul 19 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-6
- 1602807 - vim-X11 doesn't provide the gui

* Wed Jul 11 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-5
- remove fedora update script

* Wed Jul 11 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-4
- use %%{__python3} macro for defining shebang in python3 tests

* Tue Jul 10 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1763-3
- 1599660 - Conflicting manpages rvi.1.gz and vi.1.gz during update

* Wed Jun 13 2018 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1763-2
- 1576470 - Suggest correct packages to get embedded interpreters working
- add libappstream-glib for appstream-util
- 1576483 - Vim needs Python2 to build

* Wed Apr 25 2018 Karsten Hopp <karsten@redhat.com> 8.0.1763-1
- patchlevel 1763

* Tue Apr 24 2018 Karsten Hopp <karsten@redhat.com> 8.0.1755-1
- patchlevel 1755

* Fri Apr 13 2018 Karsten Hopp <karsten@redhat.com> 8.0.1704-1
- patchlevel 1704

* Mon Apr 09 2018 Karsten Hopp <karsten@redhat.com> 8.0.1679-1
- patchlevel 1679

* Fri Apr 06 2018 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1666-2
- suggests ruby-libs, python2-libs, python3-libs, perl-libs and lua-libs for vim and gvim(bug #1562057)

* Fri Apr 06 2018 Karsten Hopp <karsten@redhat.com> 8.0.1666-1
- patchlevel 1666

* Thu Apr 05 2018 Karsten Hopp <karsten@redhat.com> 8.0.1661-1
- patchlevel 1661

* Fri Mar 23 2018 Karsten Hopp <karsten@redhat.com> 8.0.1630-1
- patchlevel 1630

* Thu Mar 22 2018 Karsten Hopp <karsten@redhat.com> 8.0.1626-1
- patchlevel 1626

* Wed Mar 21 2018 Karsten Hopp <karsten@redhat.com> 8.0.1625-1
- patchlevel 1625

* Wed Mar 14 2018 Karsten Hopp <karsten@redhat.com> 8.0.1605-1
- patchlevel 1605

* Tue Mar 13 2018 Karsten Hopp <karsten@redhat.com> 8.0.1603-1
- patchlevel 1603

* Mon Mar 12 2018 Karsten Hopp <karsten@redhat.com> 8.0.1599-1
- patchlevel 1599

* Fri Mar 09 2018 Karsten Hopp <karsten@redhat.com> 8.0.1591-1
- patchlevel 1591

* Thu Mar 08 2018 Karsten Hopp <karsten@redhat.com> 8.0.1589-1
- patchlevel 1589

* Wed Mar 07 2018 Karsten Hopp <karsten@redhat.com> 8.0.1587-1
- patchlevel 1587

* Tue Mar 06 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1573-2
- vim-update.sh - unify if condition style

* Tue Mar 06 2018 Karsten Hopp <karsten@redhat.com> 8.0.1573-1
- patchlevel 1573

* Tue Mar 06 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1569-2
- update spec
- f28 got enabled in bodhi

* Mon Mar 05 2018 Karsten Hopp <karsten@redhat.com> 8.0.1569-1
- patchlevel 1569

* Wed Feb 28 2018 Karsten Hopp <karsten@redhat.com> 8.0.1553-1
- added Serbian localization files
- patchlevel 1553

* Wed Feb 28 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.1543-2
- fix vim-update.sh - bodhi update wasn't created

* Tue Feb 27 2018 Karsten Hopp <karsten@redhat.com> 8.0.1543-1
- patchlevel 1543

* Mon Feb 26 2018 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1527-3
- add Provides for vim, gvim and correcting paths to /usr/bin

* Wed Feb 21 2018 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1527-2
- adapt vim-update.sh for Fedora 28 and adding check for bodhi enablement

* Tue Feb 20 2018 Karsten Hopp <karsten@redhat.com> 8.0.1527-1
- patchlevel 1527

* Mon Feb 19 2018 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1523-2
- gcc is no longer in buildroot by default
- 1546116 - make vim-filesystem noarch package
- remove %%{_libdir}/vim, because it is unused

* Mon Feb 19 2018 Karsten Hopp <karsten@redhat.com> 8.0.1523-1
- patchlevel 1523

* Wed Feb 14 2018 Karsten Hopp <karsten@redhat.com> 8.0.1520-1
- patchlevel 1520

* Tue Feb 13 2018 Karsten Hopp <karsten@redhat.com> 8.0.1509-1
- patchlevel 1509

* Mon Feb 12 2018 Karsten Hopp <karsten@redhat.com> 8.0.1505-1
- patchlevel 1505

* Fri Feb 09 2018 Karsten Hopp <karsten@redhat.com> 8.0.1478-1
- patchlevel 1478

* Thu Feb 08 2018 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1475-2
- remove old stuff

* Wed Feb 07 2018 Karsten Hopp <karsten@redhat.com> 8.0.1475-1
- patchlevel 1475

* Mon Feb 05 2018 Karsten Hopp <karsten@redhat.com> 8.0.1473-1
- patchlevel 1473

* Thu Feb 01 2018 Karsten Hopp <karsten@redhat.com> 8.0.1451-1
- patchlevel 1451

* Mon Jan 29 2018 Karsten Hopp <karsten@redhat.com> 8.0.1438-1
- patchlevel 1438

* Tue Jan 23 2018 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1428-4
- throw vim.1.gz out from vim-minimal and other manpages from vim-common
- appdata should be in metainfo folder now

* Fri Jan 19 2018 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1428-3
- 1525506 - gvim goes into infinite loop when blink_state is OFF

* Fri Jan 12 2018 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1428-2
- removing old icon cache update

* Wed Jan 03 2018 Karsten Hopp <karsten@redhat.com> 8.0.1428-1
- patchlevel 1428

* Tue Jan 02 2018 Karsten Hopp <karsten@redhat.com> 8.0.1427-1
- patchlevel 1427

* Tue Dec 19 2017 Karsten Hopp <karsten@redhat.com> 8.0.1406-1
- patchlevel 1406

* Mon Dec 18 2017 Karsten Hopp <karsten@redhat.com> 8.0.1401-1
- patchlevel 1401

* Fri Dec 15 2017 Karsten Hopp <karsten@redhat.com> 8.0.1390-1
- patchlevel 1390

* Fri Dec 15 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1389-2
- fixing vim-update.sh

* Wed Dec 13 2017 Karsten Hopp <karsten@redhat.com> 8.0.1389-1
- patchlevel 1389

* Tue Dec 12 2017 Karsten Hopp <karsten@redhat.com> 8.0.1387-1
- patchlevel 1387

* Mon Dec 11 2017 Karsten Hopp <karsten@redhat.com> 8.0.1386-1
- patchlevel 1386

* Fri Dec 08 2017 Karsten Hopp <karsten@redhat.com> 8.0.1379-1
- patchlevel 1379

* Wed Dec 06 2017 Karsten Hopp <karsten@redhat.com> 8.0.1376-1
- patchlevel 1376

* Mon Dec 04 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1367-2
- fix regexp in vim-update.sh

* Mon Dec 04 2017 Karsten Hopp <karsten@redhat.com> 8.0.1367-1
- patchlevel 1367

* Fri Dec 01 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1360-2
- fix in vim-update.sh

* Fri Dec 01 2017 Karsten Hopp <karsten@redhat.com> 8.0.1360-1
- patchlevel 1360

* Fri Dec 01 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1359-3
- rewrite vim-update to update from the newest branch to the oldest

* Thu Nov 30 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1359-2
- 1508629 - missing full path and safe guards in file triggers in -common

* Thu Nov 30 2017 Karsten Hopp <karsten@redhat.com> 8.0.1359-1
- patchlevel 1359

* Wed Nov 29 2017 Karsten Hopp <karsten@redhat.com> 8.0.1358-1
- patchlevel 1358
- fix error in vim-update.sh

* Tue Nov 28 2017 Karsten Hopp <karsten@redhat.com> 8.0.1351-1
- patchlevel 1351

* Mon Nov 27 2017 Karsten Hopp <karsten@redhat.com> 8.0.1349-1
- patchlevel 1349

* Mon Nov 27 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1330-2
- removing vim-8.0-beval-pro.patch and stop updating f25

* Wed Nov 22 2017 Karsten Hopp <karsten@redhat.com> 8.0.1330-1
- patchlevel 1330

* Tue Nov 21 2017 Karsten Hopp <karsten@redhat.com> 8.0.1326-1
- patchlevel 1326

* Mon Nov 20 2017 Karsten Hopp <karsten@redhat.com> 8.0.1322-1
- patchlevel 1322

* Fri Nov 10 2017 Karsten Hopp <karsten@redhat.com> 8.0.1283-1
- patchlevel 1283

* Tue Nov 07 2017 Karsten Hopp <karsten@redhat.com> 8.0.1274-1
- patchlevel 1274

* Mon Nov 06 2017 Karsten Hopp <karsten@redhat.com> 8.0.1272-1
- patchlevel 1272

* Fri Nov 03 2017 Karsten Hopp <karsten@redhat.com> 8.0.1257-1
- patchlevel 1257

* Wed Nov 01 2017 Karsten Hopp <karsten@redhat.com> 8.0.1241-1
- patchlevel 1241

* Tue Oct 31 2017 Karsten Hopp <karsten@redhat.com> 8.0.1240-1
- patchlevel 1240

* Mon Oct 30 2017 Karsten Hopp <karsten@redhat.com> 8.0.1238-1
- patchlevel 1238

* Fri Oct 27 2017 Karsten Hopp <karsten@redhat.com> 8.0.1226-1
- patchlevel 1226

* Thu Oct 26 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1216-2
- mention GVim in Summary and Description of vim-x11 subpackage

* Wed Oct 25 2017 Karsten Hopp <karsten@redhat.com> 8.0.1216-1
- patchlevel 1216

* Mon Oct 23 2017 Karsten Hopp <karsten@redhat.com> 8.0.1213-1
- patchlevel 1213

* Fri Oct 20 2017 Karsten Hopp <karsten@redhat.com> 8.0.1207-1
- patchlevel 1207

* Mon Oct 16 2017 Karsten Hopp <karsten@redhat.com> 8.0.1203-1
- patchlevel 1203

* Fri Oct 13 2017 Karsten Hopp <karsten@redhat.com> 8.0.1187-1
- patchlevel 1187

* Mon Oct 09 2017 Karsten Hopp <karsten@redhat.com> 8.0.1184-1
- patchlevel 1184

* Fri Oct 06 2017 Karsten Hopp <karsten@redhat.com> 8.0.1176-1
- patchlevel 1176

* Thu Oct 05 2017 Karsten Hopp <karsten@redhat.com> 8.0.1175-1
- patchlevel 1175

* Tue Oct 03 2017 Karsten Hopp <karsten@redhat.com> 8.0.1173-1
- patchlevel 1173

* Mon Oct 02 2017 Karsten Hopp <karsten@redhat.com> 8.0.1171-1
- patchlevel 1171

* Wed Sep 27 2017 Karsten Hopp <karsten@redhat.com> 8.0.1155-1
- patchlevel 1155

* Tue Sep 26 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1144-2
- removing README.patches

* Mon Sep 25 2017 Karsten Hopp <karsten@redhat.com> 8.0.1144-1
- patchlevel 1144

* Fri Sep 22 2017 Karsten Hopp <karsten@redhat.com> 8.0.1132-1
- patchlevel 1132

* Wed Sep 20 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1129-2
- vim-update.sh - update was in bad form

* Wed Sep 20 2017 Karsten Hopp <karsten@redhat.com> 8.0.1129-1
- patchlevel 1129

* Wed Sep 20 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1127-2
- vim-update.sh - update script tried to push for previous version

* Tue Sep 19 2017 Karsten Hopp <karsten@redhat.com> 8.0.1127-1
- patchlevel 1127

* Tue Sep 19 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1123-2
- vim-update.sh - fixing bug with submiting update (update got submitted for previous version)

* Mon Sep 18 2017 Karsten Hopp <karsten@redhat.com> 8.0.1123-1
- patchlevel 1123

* Thu Sep 14 2017 Karsten Hopp <karsten@redhat.com> 8.0.1102-1
- vim-update.sh - add test for succesful build and fixing grepping of update's list
- patchlevel 1102

* Wed Sep 13 2017 Karsten Hopp <karsten@redhat.com> 8.0.1098-1
- editing vim-update.sh - check updates for newer releases and create update
- patchlevel 1098

* Tue Sep 12 2017 Karsten Hopp <karsten@redhat.com> 8.0.1097-1
- patchlevel 1097
- editing vim-update.sh - wrong condition for checking fedkpg push return value

* Mon Sep 11 2017 Karsten Hopp <karsten@redhat.com> 8.0.1092-1
- editing vim-update.sh for building package
- patchlevel 1092
- 1487175 - VIm conflicts in man pages

* Fri Sep 08 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1071-2
- fixing merge and push in vim-update.sh

* Fri Sep 08 2017 Karsten Hopp <karsten@redhat.com> 8.0.1071-1
- patchlevel 1071

* Fri Sep 08 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.1067-2
- editing vim-update.sh to do whole update automatically

* Thu Sep 07 2017 Karsten Hopp <karsten@redhat.com> 8.0.1067-1
- patchlevel 1067

* Wed Sep 06 2017 Karsten Hopp <karsten@redhat.com> 8.0.1064-1
- patchlevel 1064

* Tue Sep 05 2017 Karsten Hopp <karsten@redhat.com> 8.0.1056-1
- patchlevel 1056

* Mon Sep 04 2017 Karsten Hopp <karsten@redhat.com> 8.0.1052-1
- patchlevel 1052

* Fri Sep 01 2017 Karsten Hopp <karsten@redhat.com> 8.0.1030-1
- patchlevel 1030

* Thu Aug 24 2017 Karsten Hopp <karsten@redhat.com> 8.0.992-1
- patchlevel 992

* Wed Aug 23 2017 Karsten Hopp <karsten@redhat.com> 8.0.987-1
- patchlevel 987

* Tue Aug 22 2017 Karsten Hopp <karsten@redhat.com> 8.0.983-1
- patchlevel 983

* Fri Aug 18 2017 Karsten Hopp <karsten@redhat.com> 8.0.956-1
- patchlevel 956

* Tue Aug 15 2017 Karsten Hopp <karsten@redhat.com> 8.0.946-1
- patchlevel 946

* Mon Aug 14 2017 Karsten Hopp <karsten@redhat.com> 8.0.938-1
- patchlevel 938

* Fri Aug 11 2017 Karsten Hopp <karsten@redhat.com> 8.0.896-1
- patchlevel 896

* Thu Aug 10 2017 Karsten Hopp <karsten@redhat.com> 8.0.895-1
- patchlevel 895

* Wed Aug 09 2017 Karsten Hopp <karsten@redhat.com> 8.0.893-1
- patchlevel 893

* Wed Aug 09 2017 Zdenek Dohnal <zdohnal@redhat.com> 8.0.891-2
- editing vim-update.sh - now it takes branch name as argument for switching and run mockbuild

* Tue Aug 08 2017 Karsten Hopp <karsten@redhat.com> 8.0.891-1
- patchlevel 891

* Mon Aug 07 2017 Karsten Hopp <karsten@redhat.com> 8.0.885-1
- patchlevel 885

* Thu Aug 03 2017 Fedora Release Engineering <releng@fedoraproject.org> - 2:8.0.844-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Binutils_Mass_Rebuild

* Thu Aug 03 2017 Karsten Hopp <karsten@redhat.com> 8.0.844-1
- patchlevel 844

* Tue Aug 01 2017 Karsten Hopp <karsten@redhat.com> 8.0.826-1
- patchlevel 826

* Mon Jul 31 2017 Karsten Hopp <karsten@redhat.com> 8.0.823-1
- patchlevel 823

* Thu Jul 27 2017 Fedora Release Engineering <releng@fedoraproject.org> - 2:8.0.739-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Mass_Rebuild

* Fri Jul 21 2017 Karsten Hopp <karsten@redhat.com> 8.0.739-1
- patchlevel 739

* Thu Jul 20 2017 Karsten Hopp <karsten@redhat.com> 8.0.738-1
- patchlevel 738

* Wed Jul 19 2017 Karsten Hopp <karsten@redhat.com> 8.0.730-1
- patchlevel 730

* Tue Jul 18 2017 Karsten Hopp <karsten@redhat.com> 8.0.728-1
- patchlevel 728

* Thu Jul 13 2017 Karsten Hopp <karsten@redhat.com> 8.0.711-1
- patchlevel 711

* Tue Jul 11 2017 Karsten Hopp <karsten@redhat.com> 8.0.705-1
- patchlevel 705

* Fri Jun 30 2017 Karsten Hopp <karsten@redhat.com> 8.0.691-1
- patchlevel 691

* Thu Jun 29 2017 Karsten Hopp <karsten@redhat.com> 8.0.688-1
- patchlevel 688

* Thu Jun 29 2017 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.685-3
- update python dependencies accordingly Fedora Guidelines for Python (python-devel -> python2-devel)

* Wed Jun 28 2017 Karsten Hopp <karsten@redhat.com> 8.0.685-1
- patchlevel 685

* Mon Jun 26 2017 Karsten Hopp <karsten@redhat.com> 8.0.679-1
- patchlevel 679

* Fri Jun 23 2017 Karsten Hopp <karsten@redhat.com> 8.0.662-1
- patchlevel 662

* Tue Jun 20 2017 Karsten Hopp <karsten@redhat.com> 8.0.648-1
- patchlevel 648

* Mon Jun 19 2017 Karsten Hopp <karsten@redhat.com> 8.0.647-1
- patchlevel 647

* Thu Jun 15 2017 Karsten Hopp <karsten@redhat.com> 8.0.642-1
- patchlevel 642

* Mon Jun 12 2017 Karsten Hopp <karsten@redhat.com> 8.0.636-1
- patchlevel 636, removing perl ftbfs patch

* Fri Jun 09 2017 Karsten Hopp <karsten@redhat.com> 8.0.628-1
- patchlevel 628

* Wed Jun 07 2017 Jitka Plesnikova <jplesnik@redhat.com> - 2:8.0.627-2
- Perl 5.26 re-rebuild of bootstrapped packages

* Wed Jun 07 2017 Karsten Hopp <karsten@redhat.com> 8.0.627-1
- patchlevel 627

* Mon Jun 05 2017 Karsten Hopp <karsten@redhat.com> 8.0.617-1
- patchlevel 617

* Sun Jun 04 2017 Jitka Plesnikova <jplesnik@redhat.com> - 2:8.0.606-3
- Perl 5.26 rebuild

* Mon May 29 2017 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.606-2
- 1456455 - vim-8.0.600-1.fc27 FTBFS with Perl 5.26.0 

* Mon May 29 2017 Karsten Hopp <karsten@redhat.com> 8.0.606-1
- patchlevel 606

* Thu May 25 2017 Karsten Hopp <karsten@redhat.com> 8.0.604-1
- patchlevel 604

* Fri May 19 2017 Karsten Hopp <karsten@redhat.com> 8.0.600-1
- patchlevel 600

* Wed May 17 2017 Karsten Hopp <karsten@redhat.com> 8.0.599-1
- patchlevel 599

* Tue May 16 2017 Karsten Hopp <karsten@redhat.com> 8.0.598-1
- patchlevel 598

* Mon May 15 2017 Karsten Hopp <karsten@redhat.com> 8.0.597-1
- patchlevel 597

* Tue May 02 2017 Karsten Hopp <karsten@redhat.com> 8.0.596-1
- patchlevel 596

* Mon Apr 24 2017 Karsten Hopp <karsten@redhat.com> 8.0.586-1
- patchlevel 586

* Tue Apr 18 2017 Karsten Hopp <karsten@redhat.com> 8.0.566-1
- patchlevel 566

* Thu Apr 13 2017 Karsten Hopp <karsten@redhat.com> 8.0.563-1
- patchlevel 563

* Tue Apr 11 2017 Karsten Hopp <karsten@redhat.com> 8.0.562-1
- patchlevel 562

* Mon Apr 10 2017 Karsten Hopp <karsten@redhat.com> 8.0.559-1
- patchlevel 559

* Thu Apr 06 2017 Karsten Hopp <karsten@redhat.com> 8.0.543-1
- patchlevel 543

* Mon Apr 03 2017 Karsten Hopp <karsten@redhat.com> 8.0.540-1
- patchlevel 540

* Fri Mar 31 2017 Karsten Hopp <karsten@redhat.com> 8.0.529-1
- patchlevel 529

* Thu Mar 30 2017 Karsten Hopp <karsten@redhat.com> 8.0.525-1
- patchlevel 525

* Wed Mar 29 2017 Karsten Hopp <karsten@redhat.com> 8.0.517-1
- patchlevel 517
- enhance rhbz#1436124

* Tue Mar 28 2017 Karsten Hopp <karsten@redhat.com> 8.0.515-1
- patchlevel 515

* Mon Mar 27 2017 Karsten Hopp <karsten@redhat.com> 8.0.514-1
- patchlevel 514
- 1436124 - VIM chooses ft=bindzone for sudoedit /etc/named.conf

* Fri Mar 24 2017 Karsten Hopp <karsten@redhat.com> 8.0.503-1
- patchlevel 503

* Wed Mar 22 2017 Karsten Hopp <karsten@redhat.com> 8.0.502-1
- patchlevel 502

* Tue Mar 21 2017 Karsten Hopp <karsten@redhat.com> 8.0.497-1
- patchlevel 497

* Mon Mar 20 2017 Karsten Hopp <karsten@redhat.com> 8.0.494-1
- patchlevel 494

* Wed Mar 15 2017 Karsten Hopp <karsten@redhat.com> 8.0.458-1
- patchlevel 458

* Tue Mar 14 2017 Karsten Hopp <karsten@redhat.com> 8.0.456-1
- patchlevel 456

* Fri Mar 10 2017 Karsten Hopp <karsten@redhat.com> 8.0.442-1
- patchlevel 442

* Wed Mar 08 2017 Karsten Hopp <karsten@redhat.com> 8.0.430-1
- patchlevel 430

* Tue Mar 07 2017 Karsten Hopp <karsten@redhat.com> 8.0.427-1
- patchlevel 427

* Mon Mar 06 2017 Karsten Hopp <karsten@redhat.com> 8.0.425-1
- patchlevel 425

* Fri Mar 03 2017 Karsten Hopp <karsten@redhat.com> 8.0.402-1
- patchlevel 402

* Thu Mar 02 2017 Karsten Hopp <karsten@redhat.com> 8.0.398-1
- patchlevel 398

* Wed Mar 01 2017 Karsten Hopp <karsten@redhat.com> 8.0.388-1
- patchlevel 388

* Tue Feb 28 2017 Karsten Hopp <karsten@redhat.com> 8.0.386-1
- patchlevel 386

* Mon Feb 27 2017 Karsten Hopp <karsten@redhat.com> 8.0.381-1
- patchlevel 381

* Fri Feb 24 2017 Karsten Hopp <karsten@redhat.com> 8.0.363-1
- patchlevel 363
- removing vim-8.0-gtk-render.patch

* Fri Feb 24 2017 Karsten Hopp <karsten@redhat.com> 8.0.347-1
- patchlevel 347
- 1405234 - Gvim fails to properly render after Openbox desktop switch
- 1426296 - vim: FTBFS with python3-3.6.0-18.fc26

* Tue Feb 21 2017 Karsten Hopp <karsten@redhat.com> 8.0.344-1
- patchlevel 344

* Mon Feb 20 2017 Karsten Hopp <karsten@redhat.com> 8.0.342-1
- patchlevel 342

* Thu Feb 16 2017 Zdenek Dohnal <zdohnal@redhat.com> 8.0.329-1
- 1422833 - Syntax error in tex.vim: missing bracket

* Mon Feb 13 2017 Karsten Hopp <karsten@redhat.com> 8.0.329-1
- patchlevel 329

* Fri Feb 10 2017 Karsten Hopp <karsten@redhat.com> 8.0.324-1
- patchlevel 324

* Thu Feb 09 2017 Karsten Hopp <karsten@redhat.com> 8.0.318-1
- patchlevel 318

* Tue Feb 07 2017 Karsten Hopp <karsten@redhat.com> 8.0.314-1
- patchlevel 314, added screenshot to appdata and testing validity of appdata.xml

* Mon Feb 06 2017 Karsten Hopp <karsten@redhat.com> 8.0.311-1
- patchlevel 311

* Fri Feb 03 2017 Karsten Hopp <karsten@redhat.com> 8.0.297-1
- patchlevel 297

* Wed Feb 01 2017 Karsten Hopp <karsten@redhat.com> 8.0.275-1
- patchlevel 275

* Tue Jan 31 2017 Karsten Hopp <karsten@redhat.com> 8.0.273-1
- patchlevel 273

* Mon Jan 30 2017 Karsten Hopp <karsten@redhat.com> 8.0.271-1
- patchlevel 271

* Thu Jan 26 2017 Karsten Hopp <karsten@redhat.com> 8.0.238-1
- patchlevel 238

* Thu Jan 19 2017 Karsten Hopp <karsten@redhat.com> 8.0.206-1
- patchlevel 206

* Tue Jan 17 2017 Karsten Hopp <karsten@redhat.com> 8.0.197-1
- patchlevel 197
- update runtime files

* Mon Jan 16 2017 Karsten Hopp <karsten@redhat.com> 8.0.194-1
- patchlevel 194

* Fri Jan 13 2017 Karsten Hopp <karsten@redhat.com> 8.0.176-1
- patchlevel 176

* Thu Jan 12 2017 Karsten Hopp <karsten@redhat.com> 8.0.172-1
- patchlevel 172

* Wed Jan 11 2017 Karsten Hopp <karsten@redhat.com> 8.0.170-1
- patchlevel 170

* Mon Jan 09 2017 Karsten Hopp <karsten@redhat.com> 8.0.160-1
- patchlevel 160

* Tue Jan 03 2017 Karsten Hopp <karsten@redhat.com> 8.0.142-1
- patchlevel 142

* Mon Dec 19 2016 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.134-2
- f24->f25 vim: copy paste no longer works (bug #1401410) - fixing error in prep

* Mon Dec 19 2016 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.134-2
- f24->f25 vim: copy paste no longer works (bug #1401410) - deleting mouse setting block from defaults.vim

* Mon Dec 19 2016 Karsten Hopp <karsten@redhat.com> 8.0.134-1
- patchlevel 134
- f24->f25 vim: copy paste no longer works (bug #1401410) - revert previous changes, set mouse=v in defaults.vim

* Thu Dec 15 2016 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.133-2
- f24->f25 vim: copy paste no longer works (bug #1401410) - change mouse default setting to 'v'

* Thu Dec 15 2016 Karsten Hopp <karsten@redhat.com> - 8.0.133-2
- fix fstab syntax highlighting (rhbz#1365258)

* Mon Dec 12 2016 Karsten Hopp <karsten@redhat.com> 8.0.133-1
- patchlevel 133

* Mon Dec 05 2016 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.124-2
- add new sources

* Mon Dec 05 2016 Karsten Hopp <karsten@redhat.com> 8.0.124-1
- patchlevel 124

* Fri Dec 02 2016 Karsten Hopp <karsten@redhat.com> 8.0.118-1
- patchlevel 118

* Mon Nov 28 2016 Zdenek Dohnal <zdohnal@redhat.com> - 2:8.0.104-2
- do not ship vim.desktop

* Mon Nov 28 2016 Karsten Hopp <karsten@redhat.com> 8.0.104-1
- patchlevel 104

* Thu Nov 24 2016 Karsten Hopp <karsten@redhat.com> 8.0.095-1
- patchlevel 095

* Thu Nov 24 2016 Karsten Hopp <karsten@redhat.com> 8.0.095-1
- patchlevel 095

* Thu Nov 24 2016 Karsten Hopp <karsten@redhat.com> 8.0.095-1
- patchlevel 095

* Thu Nov 24 2016 Karsten Hopp <karsten@redhat.com> 8.0.095-2
- disable download of spec.vim, main sources are newer

* Tue Nov 22 2016 Karsten Hopp <karsten@redhat.com> 8.0.095-1
- patchlevel 095

* Mon Nov 21 2016 Karsten Hopp <karsten@redhat.com> 8.0.094-1
- patchlevel 094

* Wed Nov 16 2016 Karsten Hopp <karsten@redhat.com> 8.0.086-1
- patchlevel 086

* Tue Nov 15 2016 Karsten Hopp <karsten@redhat.com> 8.0.085-1
- patchlevel 085

* Mon Nov 14 2016 Karsten Hopp <karsten@redhat.com> 8.0.084-1
- patchlevel 084

* Mon Nov 14 2016 Zdenek Dohnal <zdohnal@redhat.com> - 8.0.070-1
- patchlevel 070

* Mon Nov 14 2016 Karsten Hopp <karsten@redhat.com> 8.0.000-1
- patchlevel 000

* Wed Nov 09 2016 Karsten Hopp <karsten@redhat.com> 8.0.057-1
- patchlevel 057

* Mon Nov 07 2016 Vít Ondruch <vondruch@redhat.com> - 8.0.037-2
- Add RPM file triggers support.

* Wed Oct 19 2016 Karsten Hopp <karsten@redhat.com> 8.0.037-1
- patchlevel 037

* Wed Oct 19 2016 Karsten Hopp <karsten@redhat.com> 8.0.018-1
- switch to gtk3

* Thu Oct 06 2016 Karsten Hopp <karsten@redhat.com> 8.0.018-1
- patchlevel 018

* Tue Sep 13 2016 Karsten Hopp <karsten@redhat.com> 8.0.003-1
- patchlevel 003

* Wed Sep 07 2016 Karsten Hopp <karsten@redhat.com> 7.4.2342-1
- patchlevel 2342

* Mon Sep 05 2016 Karsten Hopp <karsten@redhat.com> 7.4.2330-1
- patchlevel 2330

* Thu Aug 04 2016 Karsten Hopp <karsten@redhat.com> 7.4.1989-2
- redo patches, some upstream updates broke them

* Tue Jul 05 2016 Karsten Hopp <karsten@redhat.com> 7.4.1989-1
- patchlevel 1989

* Mon Jul 04 2016 Karsten Hopp <karsten@redhat.com> 7.4.1988-1
- patchlevel 1988

* Thu Jun 02 2016 Karsten Hopp <karsten@redhat.com> 7.4.1868-1
- patchlevel 1868

* Wed May 25 2016 Karsten Hopp <karsten@redhat.com> 7.4.1842-1
- patchlevel 1842

* Tue May 24 2016 Karsten Hopp <karsten@redhat.com> - 7.4.1835-2
- compile perl support as a dynamic module (rhbz#1327755)

* Tue May 24 2016 Karsten Hopp <karsten@redhat.com> 7.4.1835-1
- patchlevel 1835

* Tue May 24 2016 Karsten Hopp <karsten@redhat.com> - 7.4.1830-3
- mv vim.sh and vim.csh to source files
- sh profile.d improvements: don't leak $ID, don't fail on nounset
  (rhbz#1339106 Ville Skyttä)

* Sun May 15 2016 Jitka Plesnikova <jplesnik@redhat.com> - 2:7.4.1830-2
- Perl 5.24 rebuild

* Fri May 13 2016 Karsten Hopp <karsten@redhat.com> 7.4.1830-1
- patchlevel 1830

* Mon May 02 2016 Karsten Hopp <karsten@redhat.com> 7.4.1816-1
- patchlevel 1816

* Fri Apr 29 2016 Karsten Hopp <karsten@redhat.com> - 7.4.1797-3
- use uncompressed help files. vimtutor and vi will access those when
  vim-common is installed.  (rhbz#1262182)
  No hard requirement vim-minimal -> vim-common added, to allow minimal
  installations

* Fri Apr 29 2016 Karsten Hopp <karsten@redhat.com> - 7.4.1797-2
- merge git branches and rebuild

* Fri Apr 29 2016 Karsten Hopp <karsten@redhat.com> 7.4.1797-1
- patchlevel 1797

* Tue Apr 26 2016 Karsten Hopp <karsten@redhat.com> 7.4.1786-1
- patchlevel 1786

* Tue Apr 26 2016 Karsten Hopp <karsten@redhat.com> - 7.4.1775-2
- fix error in spec.vim (rhbz#1318991)

* Mon Apr 25 2016 Karsten Hopp <karsten@redhat.com> - 7.4.1320-2
- update ftplugin/spec.vim, syntax/spec.vim (rhbz#1297746)

* Fri Apr 22 2016 Karsten Hopp <karsten@redhat.com> 7.4.1775-1
- patchlevel 1775

* Tue Apr 12 2016 Karsten Hopp <karsten@redhat.com> - 7.4.1718-2
- add vimfiles_root macro (rhbz#844975)
- add %%_libdir/vim  directory for plugins (rhbz#1193230)
- vi, rvi, rview, ex, view don't read vimrc anymore. They use virc instead
  (rhbz#1045815)
- fix dates in changelogs when spec.vim is used and locale != 'C'

* Fri Apr 08 2016 Karsten Hopp <karsten@redhat.com> 7.4.1718-1
- patchlevel 1718

* Tue Mar 15 2016 Karsten Hopp <karsten@redhat.com> 7.4.1570-1
- patchlevel 1570

* Wed Feb 17 2016 Karsten Hopp <karsten@redhat.com> 7.4.1344-1
- patchlevel 1344

* Mon Feb 15 2016 Karsten Hopp <karsten@redhat.com> 7.4.1320-1
- patchlevel 1320

* Sun Feb 14 2016 Karsten Hopp <karsten@redhat.com> 7.4.1317-1
- patchlevel 1317

* Sat Feb 13 2016 Karsten Hopp <karsten@redhat.com> 7.4.1308-1
- patchlevel 1308

* Fri Feb 12 2016 Karsten Hopp <karsten@redhat.com> 7.4.1304-1
- patchlevel 1304

* Thu Feb 11 2016 Karsten Hopp <karsten@redhat.com> 7.4.1301-1
- patchlevel 1301

* Wed Feb 10 2016 Karsten Hopp <karsten@redhat.com> 7.4.1297-1
- patchlevel 1297

* Tue Feb 09 2016 Karsten Hopp <karsten@redhat.com> 7.4.1293-1
- patchlevel 1293

* Mon Feb 08 2016 Karsten Hopp <karsten@redhat.com> 7.4.1290-1
- patchlevel 1290

* Sun Feb 07 2016 Karsten Hopp <karsten@redhat.com> 7.4.1273-1
- patchlevel 1273

* Sat Feb 06 2016 Karsten Hopp <karsten@redhat.com> 7.4.1265-1
- patchlevel 1265

* Fri Feb 05 2016 Fedora Release Engineering <releng@fedoraproject.org> - 2:7.4.1229-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_24_Mass_Rebuild

* Mon Feb 01 2016 Karsten Hopp <karsten@redhat.com> 7.4.1229-1
- patchlevel 1229

* Sat Jan 23 2016 Karsten Hopp <karsten@redhat.com> 7.4.1153-1
- patchlevel 1153

* Fri Jan 22 2016 Karsten Hopp <karsten@redhat.com> 7.4.1152-1
- patchlevel 1152

* Thu Jan 21 2016 Karsten Hopp <karsten@redhat.com> 7.4.1147-1
- patchlevel 1147

* Wed Jan 20 2016 Karsten Hopp <karsten@redhat.com> 7.4.1143-1
- patchlevel 1143

* Tue Jan 19 2016 Karsten Hopp <karsten@redhat.com> 7.4.1142-1
- patchlevel 1142

* Tue Jan 19 2016 Karsten Hopp <karsten@redhat.com> 7.4.1131-1
- patchlevel 1131

* Mon Jan 18 2016 Karsten Hopp <karsten@redhat.com> 7.4.1129-1
- patchlevel 1129

* Sun Jan 17 2016 Karsten Hopp <karsten@redhat.com> 7.4.1112-1
- patchlevel 1112

* Sat Jan 16 2016 Karsten Hopp <karsten@redhat.com> 7.4.1101-1
- patchlevel 1101

* Fri Jan 15 2016 Karsten Hopp <karsten@redhat.com> 7.4.1090-1
- patchlevel 1090

* Wed Jan 13 2016 Karsten Hopp <karsten@redhat.com> 7.4.1089-1
- patchlevel 1089

* Tue Jan 12 2016 Karsten Hopp <karsten@redhat.com> - 7.4.1087-2
- fix ssh syntax files
- fix %%global in spec.vim (rhbz#1058041)

* Mon Jan 11 2016 Karsten Hopp <karsten@redhat.com> 7.4.1087-1
- patchlevel 1087

* Sun Dec 20 2015 Karsten Hopp <karsten@redhat.com> 7.4.979-1
- patchlevel 979

* Fri Dec 18 2015 Karsten Hopp <karsten@redhat.com> 7.4.977-1
- patchlevel 977

* Mon Dec 14 2015 Karsten Hopp <karsten@redhat.com> 7.4.972-1
- patchlevel 972

* Sun Dec 13 2015 Karsten Hopp <karsten@redhat.com> 7.4.970-1
- patchlevel 970

* Sat Dec 12 2015 Karsten Hopp <karsten@redhat.com> 7.4.969-1
- patchlevel 969

* Mon Dec 07 2015 Karsten Hopp <karsten@redhat.com> 7.4.963-1
- patchlevel 963

* Sun Dec 06 2015 Karsten Hopp <karsten@redhat.com> 7.4.962-1
- patchlevel 962

* Fri Dec 04 2015 Karsten Hopp <karsten@redhat.com> 7.4.960-1
- patchlevel 960

* Wed Dec 02 2015 Karsten Hopp <karsten@redhat.com> 7.4.947-1
- patchlevel 947

* Tue Dec 01 2015 Karsten Hopp <karsten@redhat.com> 7.4.945-1
- patchlevel 945

* Mon Nov 30 2015 Karsten Hopp <karsten@redhat.com> 7.4.944-1
- patchlevel 944

* Thu Nov 26 2015 Karsten Hopp <karsten@redhat.com> 7.4.942-1
- patchlevel 942

* Wed Nov 25 2015 Karsten Hopp <karsten@redhat.com> 7.4.941-1
- patchlevel 941

* Mon Nov 23 2015 Karsten Hopp <karsten@redhat.com> 7.4.936-1
- patchlevel 936

* Sun Nov 22 2015 Karsten Hopp <karsten@redhat.com> 7.4.934-1
- patchlevel 934

* Fri Nov 20 2015 Karsten Hopp <karsten@redhat.com> 7.4.930-1
- patchlevel 930

* Wed Nov 11 2015 Karsten Hopp <karsten@redhat.com> 7.4.922-1
- patchlevel 922

* Tue Nov 10 2015 Karsten Hopp <karsten@redhat.com> 7.4.917-1
- patchlevel 917

* Wed Nov 04 2015 Karsten Hopp <karsten@redhat.com> 7.4.909-1
- patchlevel 909
- Fedora vim now uses tarballs created from upstream git instead
  of just upstream patches. Now runtime files will have fixes, too.

* Tue Nov 03 2015 Karsten Hopp <karsten@redhat.com> 7.4.908-1
- patchlevel 908

* Mon Nov 02 2015 Karsten Hopp <karsten@redhat.com> 7.4.903-1
- patchlevel 903

* Sat Oct 31 2015 Karsten Hopp <karsten@redhat.com> 7.4.902-1
- patchlevel 902

* Mon Oct 26 2015 Karsten Hopp <karsten@redhat.com> 7.4.900-1
- patchlevel 900

* Wed Oct 14 2015 Karsten Hopp <karsten@redhat.com> 7.4.898-1
- patchlevel 898

* Thu Oct 08 2015 Karsten Hopp <karsten@redhat.com> 7.4.891-1
- patchlevel 891

* Wed Oct 07 2015 Karsten Hopp <karsten@redhat.com> 7.4.890-1
- patchlevel 890

* Wed Sep 30 2015 Karsten Hopp <karsten@redhat.com> 7.4.889-1
- patchlevel 889

* Sat Sep 26 2015 Karsten Hopp <karsten@redhat.com> 7.4.884-1
- patchlevel 884

* Tue Sep 22 2015 Karsten Hopp <karsten@redhat.com> 7.4.873-2
- fix garbled xxd manpage in Japanese locale (bugzilla #1035606), Masayuki Oshima

* Tue Sep 22 2015 Karsten Hopp <karsten@redhat.com> 7.4.873-1
- add Provides: mergetool for bugzilla #990444

* Fri Sep 18 2015 Karsten Hopp <karsten@redhat.com> 7.4.873-1
- patchlevel 873

* Wed Sep 16 2015 Karsten Hopp <karsten@redhat.com> 7.4.871-1
- patchlevel 871

* Thu Sep 10 2015 Karsten Hopp <karsten@redhat.com> 7.4.865-1
- patchlevel 865

* Wed Sep 09 2015 Karsten Hopp <karsten@redhat.com> 7.4.861-1
- patchlevel 861

* Wed Sep 02 2015 Karsten Hopp <karsten@redhat.com> 7.4.854-1
- patchlevel 854

* Fri Aug 28 2015 Karsten Hopp <karsten@redhat.com> 7.4.843-1
- patchlevel 843

* Thu Aug 27 2015 Karsten Hopp <karsten@redhat.com> 7.4.841-1
- patchlevel 841

* Wed Aug 26 2015 Karsten Hopp <karsten@redhat.com> 7.4.838-1
- patchlevel 838

* Wed Aug 19 2015 Karsten Hopp <karsten@redhat.com> 7.4.827-1
- patchlevel 827
- re-enable lua
- enable python3

* Fri Jul 10 2015 Lubomir Rintel <lkundrak@v3.sk> 7.4.769-3
- drop forcing background, vim detects this since 7.4.757, rhbz#1159920

* Sat Jul 04 2015 Karsten Hopp <karsten@redhat.com> 7.4.769-1
- patchlevel 769

* Fri Jul 03 2015 Karsten Hopp <karsten@redhat.com> 7.4.768-1
- patchlevel 768

* Mon Jun 29 2015 Karsten Hopp <karsten@redhat.com> 7.4.764-1
- patchlevel 764

* Sun Jun 28 2015 Karsten Hopp <karsten@redhat.com> 7.4.763-1
- patchlevel 763

* Fri Jun 26 2015 Karsten Hopp <karsten@redhat.com> 7.4.761-1
- patchlevel 761

* Thu Jun 25 2015 Karsten Hopp <karsten@redhat.com> 7.4.757-1
- patchlevel 757

* Mon Jun 22 2015 Karsten Hopp <karsten@redhat.com> 7.4.752-1
- patchlevel 752

* Fri Jun 19 2015 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 2:7.4.737-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_23_Mass_Rebuild

* Wed Jun 10 2015 Karsten Hopp <karsten@redhat.com> 7.4.737-1
- patchlevel 737

* Thu May 14 2015 Karsten Hopp <karsten@redhat.com> 7.4.729-1
- patchlevel 729

* Wed May 06 2015 Karsten Hopp <karsten@redhat.com> 7.4.728-1
- patchlevel 728

* Tue May 05 2015 Karsten Hopp <karsten@redhat.com> 7.4.726-1
- patchlevel 726

* Mon May 04 2015 Karsten Hopp <karsten@redhat.com> 7.4.723-1
- patchlevel 723

* Thu Apr 23 2015 Karsten Hopp <karsten@redhat.com> 7.4.712-1
- patchlevel 712

* Wed Apr 22 2015 Karsten Hopp <karsten@redhat.com> 7.4.711-1
- patchlevel 711

* Tue Apr 21 2015 Karsten Hopp <karsten@redhat.com> 7.4.708-1
- patchlevel 708

* Sat Apr 18 2015 Karsten Hopp <karsten@redhat.com> 7.4.703-1
- patchlevel 703

* Fri Apr 17 2015 Karsten Hopp <karsten@redhat.com> 7.4.702-1
- patchlevel 702

* Wed Apr 15 2015 Karsten Hopp <karsten@redhat.com> 7.4.701-1
- patchlevel 701

* Tue Apr 14 2015 Karsten Hopp <karsten@redhat.com> 7.4.699-1
- patchlevel 699

* Mon Apr 13 2015 Karsten Hopp <karsten@redhat.com> 7.4.698-1
- patchlevel 698

* Fri Apr 10 2015 Karsten Hopp <karsten@redhat.com> 7.4.692-1
- patchlevel 692

* Sat Apr 04 2015 Karsten Hopp <karsten@redhat.com> 7.4.691-1
- patchlevel 691

* Fri Apr 03 2015 Karsten Hopp <karsten@redhat.com> 7.4.690-1
- patchlevel 690

* Wed Apr 01 2015 Karsten Hopp <karsten@redhat.com> 7.4.688-1
- patchlevel 688

* Tue Mar 31 2015 Karsten Hopp <karsten@redhat.com> 7.4.686-1
- patchlevel 686

* Thu Mar 26 2015 Karsten Hopp <karsten@redhat.com> 7.4.683-1
- patchlevel 683

* Wed Mar 25 2015 Karsten Hopp <karsten@redhat.com> 7.4.682-1
- patchlevel 682

* Tue Mar 24 2015 Karsten Hopp <karsten@redhat.com> 7.4.681-1
- patchlevel 681

* Sun Mar 22 2015 Karsten Hopp <karsten@redhat.com> 7.4.674-1
- patchlevel 674

* Sat Mar 21 2015 Karsten Hopp <karsten@redhat.com> 7.4.672-1
- patchlevel 672

* Fri Mar 20 2015 Karsten Hopp <karsten@redhat.com> 7.4.668-1
- patchlevel 668

* Thu Mar 19 2015 Jitka Plesnikova <jplesnik@redhat.com> - 7.4.663-3
- Perl 5.22 rebuild

* Wed Mar 18 2015 Richard Hughes <rhughes@redhat.com> - 7.4.663-2
- Add an AppData file for the software center

* Sat Mar 14 2015 Karsten Hopp <karsten@redhat.com> 7.4.663-1
- patchlevel 663

* Fri Mar 13 2015 Karsten Hopp <karsten@redhat.com> 7.4.662-1
- patchlevel 662

* Sun Mar 08 2015 Karsten Hopp <karsten@redhat.com> 7.4.658-1
- patchlevel 658

* Sat Mar 07 2015 Karsten Hopp <karsten@redhat.com> 7.4.657-1
- patchlevel 657

* Fri Mar 06 2015 Karsten Hopp <karsten@redhat.com> 7.4.656-1
- patchlevel 656

* Thu Mar 05 2015 Karsten Hopp <karsten@redhat.com> 7.4.652-1
- patchlevel 652

* Sat Feb 28 2015 Karsten Hopp <karsten@redhat.com> 7.4.648-1
- patchlevel 648

* Fri Feb 27 2015 Karsten Hopp <karsten@redhat.com> 7.4.643-1
- patchlevel 643

* Fri Feb 27 2015 Dave Airlie <airlied@redhat.com> 7.4.640-4
- fix vimrc using wrong comment character

* Thu Feb 26 2015 Karsten Hopp <karsten@redhat.com> 7.4.640-3
- bump release

* Thu Feb 26 2015 Karsten Hopp <karsten@redhat.com> 7.4.640-2
- set background to dark in gnome-terminal, rhbz#1159920

* Wed Feb 25 2015 Karsten Hopp <karsten@redhat.com> 7.4.640-1
- patchlevel 640

* Sat Feb 21 2015 Till Maas <opensource@till.name> - 7.4.629-2
- Rebuilt for Fedora 23 Change
  https://fedoraproject.org/wiki/Changes/Harden_all_packages_with_position-independent_code

* Wed Feb 11 2015 Karsten Hopp <karsten@redhat.com> 7.4.629-2
- fix syntax highlighting for some ssh_config sshd_config keywords

* Wed Feb 11 2015 Karsten Hopp <karsten@redhat.com> 7.4.629-1
- patchlevel 629

* Fri Feb 06 2015 Karsten Hopp <karsten@redhat.com> 7.4.622-1
- patchlevel 622

* Thu Feb 05 2015 Karsten Hopp <karsten@redhat.com> 7.4.621-1
- patchlevel 621

* Wed Feb 04 2015 Karsten Hopp <karsten@redhat.com> 7.4.618-1
- patchlevel 618

* Tue Feb 03 2015 Karsten Hopp <karsten@redhat.com> 7.4.615-1
- patchlevel 615

* Wed Jan 28 2015 Karsten Hopp <karsten@redhat.com> 7.4.608-1
- patchlevel 608

* Tue Jan 27 2015 Karsten Hopp <karsten@redhat.com> 7.4.604-1
- patchlevel 604

* Fri Jan 23 2015 Karsten Hopp <karsten@redhat.com> 7.4.591-1
- patchlevel 591

* Wed Jan 21 2015 Karsten Hopp <karsten@redhat.com> 7.4.589-1
- patchlevel 589

* Tue Jan 20 2015 Karsten Hopp <karsten@redhat.com> 7.4.586-1
- patchlevel 586

* Sun Jan 18 2015 Karsten Hopp <karsten@redhat.com> 7.4.582-1
- patchlevel 582

* Thu Jan 15 2015 Karsten Hopp <karsten@redhat.com> 7.4.580-1
- patchlevel 580

* Wed Jan 14 2015 Karsten Hopp <karsten@redhat.com> 7.4.576-1
- patchlevel 576

* Mon Jan 12 2015 Karsten Hopp <karsten@redhat.com> 7.4.567-1
- use %%make_install in spec-template.new (rhbz#919270)

* Thu Jan 08 2015 Karsten Hopp <karsten@redhat.com> 7.4.567-1
- patchlevel 567

* Wed Jan 07 2015 Karsten Hopp <karsten@redhat.com> 7.4.566-1
- patchlevel 566

* Thu Dec 18 2014 Karsten Hopp <karsten@redhat.com> 7.4.560-1
- patchlevel 560

* Wed Dec 17 2014 Karsten Hopp <karsten@redhat.com> 7.4.557-1
- patchlevel 557

* Sun Dec 14 2014 Karsten Hopp <karsten@redhat.com> 7.4.552-1
- patchlevel 552

* Sat Dec 13 2014 Karsten Hopp <karsten@redhat.com> 7.4.546-1
- patchlevel 546

* Mon Dec 08 2014 Karsten Hopp <karsten@redhat.com> 7.4.542-1
- patchlevel 542

* Sun Dec 07 2014 Karsten Hopp <karsten@redhat.com> 7.4.541-1
- patchlevel 541

* Mon Dec 01 2014 Karsten Hopp <karsten@redhat.com> 7.4.540-1
- patchlevel 540

* Sun Nov 30 2014 Karsten Hopp <karsten@redhat.com> 7.4.539-1
- patchlevel 539

* Fri Nov 28 2014 Karsten Hopp <karsten@redhat.com> 7.4.537-1
- patchlevel 537

* Thu Nov 27 2014 Karsten Hopp <karsten@redhat.com> 7.4.534-1
- patchlevel 534

* Sun Nov 23 2014 Karsten Hopp <karsten@redhat.com> 7.4.527-1
- patchlevel 527

* Fri Nov 21 2014 Karsten Hopp <karsten@redhat.com> 7.4.526-1
- patchlevel 526

* Thu Nov 20 2014 Karsten Hopp <karsten@redhat.com> 7.4.525-1
- patchlevel 525

* Wed Nov 19 2014 Karsten Hopp <karsten@redhat.com> 7.4.521-1
- patchlevel 521

* Thu Nov 13 2014 Karsten Hopp <karsten@redhat.com> 7.4.516-1
- patchlevel 516

* Wed Nov 12 2014 Karsten Hopp <karsten@redhat.com> 7.4.512-1
- patchlevel 512

* Thu Nov 06 2014 Karsten Hopp <karsten@redhat.com> 7.4.507-1
- patchlevel 507

* Wed Nov 05 2014 Karsten Hopp <karsten@redhat.com> 7.4.502-1
- patchlevel 502

* Sat Nov 01 2014 Karsten Hopp <karsten@redhat.com> 7.4.492-1
- patchlevel 492

* Fri Oct 31 2014 Karsten Hopp <karsten@redhat.com> 7.4.491-1
- patchlevel 491

* Thu Oct 23 2014 Karsten Hopp <karsten@redhat.com> 7.4.488-1
- patchlevel 488

* Wed Oct 22 2014 Karsten Hopp <karsten@redhat.com> 7.4.487-1
- patchlevel 487

* Tue Oct 21 2014 Karsten Hopp <karsten@redhat.com> 7.4.483-1
- patchlevel 483

* Fri Oct 17 2014 Karsten Hopp <karsten@redhat.com> 7.4.481-1
- patchlevel 481

* Thu Oct 16 2014 Karsten Hopp <karsten@redhat.com> 7.4.480-1
- patchlevel 480

* Wed Oct 15 2014 Karsten Hopp <karsten@redhat.com> 7.4.477-1
- patchlevel 477

* Mon Oct 13 2014 Karsten Hopp <karsten@redhat.com> 7.4.475-2
- add support for %%license macro (Petr Šabata)

* Sat Oct 11 2014 Karsten Hopp <karsten@redhat.com> 7.4.475-1
- patchlevel 475

* Fri Oct 10 2014 Karsten Hopp <karsten@redhat.com> 7.4.473-1
- patchlevel 473

* Thu Oct 09 2014 Karsten Hopp <karsten@redhat.com> 7.4.471-1
- patchlevel 471

* Tue Oct 07 2014 Karsten Hopp <karsten@redhat.com> 7.4.465-1
- patchlevel 465

* Tue Sep 30 2014 Karsten Hopp <karsten@redhat.com> 7.4.463-1
- patchlevel 463

* Mon Sep 29 2014 Karsten Hopp <karsten@redhat.com> 7.4.462-1
- patchlevel 462

* Sat Sep 27 2014 Karsten Hopp <karsten@redhat.com> 7.4.461-1
- patchlevel 461

* Wed Sep 24 2014 Karsten Hopp <karsten@redhat.com> 7.4.460-1
- patchlevel 460

* Wed Sep 24 2014 Karsten Hopp <karsten@redhat.com> 7.4.458-1
- patchlevel 458

* Tue Sep 23 2014 Karsten Hopp <karsten@redhat.com> 7.4.457-1
- patchlevel 457

* Sat Sep 20 2014 Karsten Hopp <karsten@redhat.com> 7.4.453-1
- patchlevel 453

* Tue Sep 16 2014 Karsten Hopp <karsten@redhat.com> 7.4.444-1
- patchlevel 444

* Mon Sep 15 2014 Karsten Hopp <karsten@redhat.com> 7.4.443-1
- patchlevel 443

* Wed Sep 10 2014 Karsten Hopp <karsten@redhat.com> 7.4.442-1
- patchlevel 442

* Tue Aug 26 2014 Jitka Plesnikova <jplesnik@redhat.com> - 2:7.4.417-2
- Perl 5.20 rebuild

* Tue Aug 26 2014 Karsten Hopp <karsten@redhat.com> 7.4.417-1
- patchlevel 417

* Fri Aug 22 2014 Karsten Hopp <karsten@redhat.com> 7.4.410-1
- patchlevel 410
- xsubpp-path patch is obsolete now

* Fri Aug 22 2014 Karsten Hopp <karsten@redhat.com> 7.4.402-3
- fix help file names

* Mon Aug 18 2014 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 2:7.4.402-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_21_22_Mass_Rebuild


* Wed Aug 13 2014 Karsten Hopp <karsten@redhat.com> 7.4.402-1
- patchlevel 402

* Tue Aug 12 2014 Karsten Hopp <karsten@redhat.com> 7.4.401-1
- patchlevel 401

* Wed Aug  6 2014 Tom Callaway <spot@fedoraproject.org> 2:7.4.373-2
- fix license handling

* Tue Jul 22 2014 Karsten Hopp <karsten@redhat.com> 7.4.373-1
- patchlevel 373

* Sun Jun 08 2014 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 2:7.4.307-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_21_Mass_Rebuild

* Tue May 27 2014 Karsten Hopp <karsten@redhat.com> 7.4.307-1
- patchlevel 307

* Tue Apr 29 2014 Vít Ondruch <vondruch@redhat.com> - 2:7.4.258-2
- Rebuilt for https://fedoraproject.org/wiki/Changes/Ruby_2.1

* Wed Apr 16 2014 Karsten Hopp <karsten@redhat.com> 7.4.258-1
- patchlevel 258

* Mon Apr 07 2014 Karsten Hopp <karsten@redhat.com> 7.4.253-1
- patchlevel 253

* Wed Mar 12 2014 Karsten Hopp <karsten@redhat.com> 7.4.204-1
- patchlevel 204

* Mon Feb 24 2014 Karsten Hopp <karsten@redhat.com> 7.4.192-1
- patchlevel 192

* Tue Feb 18 2014 Karsten Hopp <karsten@redhat.com> 7.4.182-1
- patchlevel 182

* Tue Feb 18 2014 Karsten Hopp <karsten@redhat.com> 7.4.179-2
- enable dynamic lua interpreter

* Sat Feb 15 2014 Karsten Hopp <karsten@redhat.com> 7.4.179-1
- patchlevel 179

* Wed Jan 29 2014 Karsten Hopp <karsten@redhat.com> 7.4.160-1
- patchlevel 160

* Tue Dec 17 2013 Karsten Hopp <karsten@redhat.com> 7.4.131-1
- patchlevel 131

* Wed Nov 20 2013 Karsten Hopp <karsten@redhat.com> 7.4.094-1
- patchlevel 094

* Tue Oct 15 2013 Karsten Hopp <karsten@redhat.com> 7.4.052-1
- patchlevel 052

* Wed Sep 11 2013 Karsten Hopp <karsten@redhat.com> 7.4.027-2
- update vim icons (#1004788)
- check if 'id -u' returns empty string (vim.sh)

* Wed Sep 11 2013 Karsten Hopp <karsten@redhat.com> 7.4.027-1
- patchlevel 027

* Wed Sep 04 2013 Karsten Hopp <karsten@redhat.com> 7.4.016-1
- patchlevel 016

* Wed Aug 28 2013 Karsten Hopp <karsten@redhat.com> 7.4.009-1
- patchlevel 009
  mkdir("foo/bar/", "p") gives an error message
  creating a preview window on startup messes up the screen
  new regexp engine can't be interrupted
  too easy to write a file was not decrypted (yet)

* Wed Aug 21 2013 Karsten Hopp <karsten@redhat.com> 7.4.5-1
- patchlevel 5
- when closing a window fails ":bwipe" may hang
- "vaB" while 'virtualedit' is set selects the wrong area

* Wed Aug 21 2013 Karsten Hopp <karsten@redhat.com> 7.4.3-1
- patchlevel 3, memory access error in Ruby syntax highlighting

* Wed Aug 21 2013 Karsten Hopp <karsten@redhat.com> 7.4.2-1
- patchlevel 2, pattern with two alternative look-behind matches doesn't match

* Wed Aug 21 2013 Karsten Hopp <karsten@redhat.com> 7.4.1-1
- patchlevel 1, 'ic' doesn't work for patterns such as [a-z]

* Mon Aug 12 2013 Karsten Hopp <karsten@redhat.com> 7.4.0-1
- update to vim-7.4

* Sun Aug 04 2013 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 2:7.3.1314-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_20_Mass_Rebuild

* Fri Jul 26 2013 Karsten Hopp <karsten@redhat.com> 7.3.1314-2
- document gex and vimx in man page
- fix gvimdiff and gvimtutor man page redirects

* Wed Jul 17 2013 Petr Pisar <ppisar@redhat.com> - 2:7.3.1314-2
- Perl 5.18 rebuild

* Tue Jul 09 2013 Karsten Hopp <karsten@redhat.com> 7.3.1314-1
- patchlevel 1314

* Thu Jul 04 2013 Karsten Hopp <karsten@redhat.com> 7.3.1293-1
- patchlevel 1293

* Fri Jun 14 2013 Karsten Hopp <karsten@redhat.com> 7.3.1189-1
- patchlevel 1189

* Tue Jun 04 2013 Karsten Hopp <karsten@redhat.com> 7.3.1109-1
- patchlevel 1109

* Wed May 22 2013 Karsten Hopp <karsten@redhat.com> 7.3.1004-1
- patchlevel 1004

* Wed May 22 2013 Karsten Hopp <karsten@redhat.com> 7.3.1000-1
- patchlevel 1000 !

* Tue May 21 2013 Karsten Hopp <karsten@redhat.com> 7.3.987-1
- patchlevel 987

* Tue May 21 2013 Karsten Hopp <karsten@redhat.com> 7.3.944-2
- consistent use of macros in spec file
- add some links to man pages

* Tue May 14 2013 Karsten Hopp <karsten@redhat.com> 7.3.944-1
- patchlevel 944

* Mon May 13 2013 Karsten Hopp <karsten@redhat.com> 7.3.943-2
- add BR perl(ExtUtils::ParseXS)

* Mon May 13 2013 Karsten Hopp <karsten@redhat.com> 7.3.943-1
- patchlevel 943

* Wed May 08 2013 Karsten Hopp <karsten@redhat.com> 7.3.931-1
- patchlevel 931

* Wed May 08 2013 Karsten Hopp <karsten@redhat.com> 7.3.903-1
- fix ruby version check

* Fri Apr 19 2013 Karsten Hopp <karsten@redhat.com> 7.3.903-1
- drop crv patch
- update 7.3.838 patch, it was broken upstream

* Mon Apr 15 2013 Karsten Hopp <karsten@redhat.com> 7.3.903-1
- patchlevel 903

* Mon Feb 18 2013 Karsten Hopp <karsten@redhat.com> 7.3.822-1
- patchlevel 822

* Fri Feb 15 2013 Toshio Kuratomi <toshio@fedoraproject.org> - 7.3.797-2
- Only use --vendor for desktop-file-install on F18 or less

* Thu Jan 31 2013 Karsten Hopp <karsten@redhat.com> 7.3.797-1
- patchlevel 797

* Mon Jan 28 2013 Karsten Hopp <karsten@redhat.com> 7.3.785-1
- patchlevel 785

* Tue Nov 20 2012 Karsten Hopp <karsten@redhat.com> 7.3.715-1
- patchlevel 715

* Mon Nov 12 2012 Karsten Hopp <karsten@redhat.com> 7.3.712-1
- patchlevel 712

* Mon Nov 12 2012 Karsten Hopp <karsten@redhat.com> 7.3.682-2
- fix vim.csh syntax

* Tue Oct 23 2012 Karsten Hopp <karsten@redhat.com> 7.3.712-1
- patchlevel 712

* Mon Oct 15 2012 Karsten Hopp <karsten@redhat.com> 7.3.691-1
- patchlevel 691

* Fri Oct 05 2012 Karsten Hopp <karsten@redhat.com> 7.3.682-1
- patchlevel 682
- use --enable-rubyinterp=dynamic and --enable-pythoninterp=dynamic

* Mon Sep 03 2012 Karsten Hopp <karsten@redhat.com> 7.3.646-1
- patchlevel 646

* Tue Aug 28 2012 Karsten Hopp <karsten@redhat.com> 7.3.638-2
- fix some man page typos (#668894, #675480)
- own usr/share/vim/vimfiles/doc/tags (#845564)
- add path to csope database (#844843)

* Tue Aug 28 2012 Karsten Hopp <karsten@redhat.com> 7.3.638-1
- patchlevel 638

# vim:nrformats-=octal
