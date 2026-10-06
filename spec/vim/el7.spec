%define patchlevel 1167
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
%define withlua 0

%define baseversion 9.2
%define vimdir vim92

Summary: The VIM editor
URL:     http://www.vim.org/
Name: vim
Version: 9.2.1167
Release: 1%{?dist}
License: Vim
Group: Applications/Editors
Source0: https://github.com/vim/vim/archive/refs/tags/v%{version}.tar.gz
Source3: gvim.desktop
Source4: vimrc
Source7: gvim16.png
Source8: gvim32.png
Source9: gvim48.png
Source10: gvim64.png
Source11: Changelog.rpm
Source12: vi_help.txt
%if %{withvimspell}
Source13: vim-spell-files.tar.bz2
%endif
Source14: spec-template
Source15: spec-template.new
# rhbz#1083924 https://github.com/vim-jp/vim-cpp/blob/master/syntax/cpp.vim
Source16: cpp.vim
Patch0: vim-gtk2-image-scale.patch

%if %{withhunspell}
BuildRequires: hunspell-devel
%endif
# If you're as lazy as me, generate the list using
# for i in `seq 1 14`; do printf "Patch%03d: ftp://ftp.vim.org/pub/vim/patches/7.4/7.4.%03d\n" $i $i; done

# 1267826 - Include c++11 syntax highlighting in vim
# 1377316 - [RFE] make _remote_ vim doing the right decisions about 'set background'
# merged patch of 7.4.{757,761,762,766,770, update-help-files} commits from upstream
# 1719964 - CVE-2019-12735 arbitrary command execution in getchar.c [rhel-7.7]
# 1833186 - gvim consums 100% cpu under certain condition

Buildroot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildRequires: python-devel ncurses-devel gettext perl-devel
BuildRequires: perl(ExtUtils::Embed) perl(ExtUtils::ParseXS)
BuildRequires: libacl-devel gpm-devel autoconf
%if %{WITH_SELINUX}
BuildRequires: libselinux-devel
%endif
%if "%{withruby}" == "1"
Buildrequires: ruby-devel ruby
%endif
%if "%{withlua}" == "1"
Buildrequires: lua-devel
%endif
%if %{desktop_file}
# for /usr/bin/desktop-file-install
Requires: desktop-file-utils
BuildRequires: desktop-file-utils >= %{desktop_file_utils_version}
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
Group: Applications/Editors
Conflicts: man-pages-fr < 0.9.7-14
Conflicts: man-pages-it < 0.3.0-17
Conflicts: man-pages-pl < 0.24-2
Requires: %{name}-filesystem

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
Group: Applications/Editors
Requires: vim-common = %{epoch}:%{version}-%{release}

%description spell
This subpackage contains dictionaries for vim spell checking in
many different languages.

%package minimal
Summary: A minimal version of the VIM editor
Group: Applications/Editors
Provides: vi = %{version}-%{release}
Provides: /bin/vi

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
Group: Applications/Editors
Requires: vim-common = %{epoch}:%{version}-%{release} which
Provides: vim = %{version}-%{release}
Requires: perl(:MODULE_COMPAT_%(eval "`%{__perl} -V:version`"; echo $version))

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
Group: Applications/Editors

%Description filesystem
This package provides some directories which are required by other
packages that add vim files, p.e.  additional syntax files or filetypes.

%package X11
Summary: The VIM version of the vi editor for the X Window System
Group: Applications/Editors
Requires: vim-common = %{epoch}:%{version}-%{release} libattr >= 2.4 gtk2 >= 2.6
Provides: gvim = %{version}-%{release}
BuildRequires: gtk2-devel libSM-devel libXt-devel libXpm-devel
Requires: perl(:MODULE_COMPAT_%(eval "`%{__perl} -V:version`"; echo $version))
Requires: hicolor-icon-theme

%description X11
VIM (VIsual editor iMproved) is an updated and improved version of the
vi editor.  Vi was the first real screen-based editor for UNIX, and is
still very popular.  VIM improves on vi by adding new features:
multiple windows, multi-level undo, block highlighting and
more. VIM-X11 is a version of the VIM editor which will run within the
X Window System.  If you install this package, you can run VIM as an X
application with a full GUI interface and mouse support.

Install the vim-X11 package if you'd like to try out a version of vi
with graphics and mouse capabilities.  You'll also need to install the
vim-common package.

%prep
%setup -q -n vim-%{version}
# Keep the native EL7 GTK2 ABI. Older versions lack this image-scaling guard;
# skip the compatibility patch once upstream changes it, without a GTK upgrade.
if grep -Fxq '#if defined(FEAT_GUI_GTK) && defined(FEAT_IMAGE)' src/vim.h; then
%patch0 -p1
fi
# fix rogue dependencies from sample code
chmod -x runtime/tools/mve.awk
%if %{withhunspell}
%endif
perl -pi -e "s,bin/nawk,bin/awk,g" runtime/tools/mve.awk

# Base patches...
# for i in `seq 1 14`; do printf "%%patch%03d -p0 \n" $i; done

# install spell files
%if %{withvimspell}
%{__tar} xjf %{SOURCE13}
%endif


# 1833186 - gvim consums 100% cpu under certain condition

perl -pi -e "s/test71.out//" src/testdir/Makefile

%build
export LDFLAGS="${LDFLAGS:-} -pthread"
cd src
# Use the pre-generated configure script shipped by the upstream release.

sed -e "s+VIMRCLOC	= \$(VIMLOC)+VIMRCLOC	= /etc+" Makefile > Makefile.tmp
mv -f Makefile.tmp Makefile

# 1490927 - added -D__linux__ and -D_REENTRANT, because we don't want to use alternative stack for signals (it caused segfault) 
export CFLAGS="%{optflags} -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64 -D_FORTIFY_SOURCE=2 -D__linux__ -D_REENTRANT"
export CXXFLAGS="%{optflags} -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64 -D_FORTIFY_SOURCE=2 -D__linux__ -D_REENTRANT"

cp -f os_unix.h os_unix.h.save
cp -f ex_cmds.c ex_cmds.c.save

perl -pi -e "s/help.txt/vi_help.txt/"  os_unix.h ex_cmds.c
perl -pi -e "s/\/etc\/vimrc/\/etc\/virc/"  os_unix.h
%configure --prefix=%{_prefix} --with-features=small --with-x=no \
  --enable-multibyte \
  --disable-netbeans \
%if %{WITH_SELINUX}
  --enable-selinux \
%else
  --disable-selinux \
%endif
  --disable-pythoninterp --disable-perlinterp --disable-tclinterp \
  --with-tlib=tinfo --enable-gui=no --disable-gpm --exec-prefix=/ \
  --with-compiledby="<bugzilla@redhat.com>" \
  --with-modified-by="<bugzilla@redhat.com>"

make VIMRCLOC=/etc VIMRUNTIMEDIR=/usr/share/vim/%{vimdir} %{?_smp_mflags}
cp vim minimal-vim
make clean

mv -f os_unix.h.save os_unix.h
mv -f ex_cmds.c.save ex_cmds.c

%configure --with-features=huge \
  --enable-pythoninterp=dynamic \
  --enable-perlinterp \
  --disable-tclinterp --with-x=yes \
  --enable-xim --enable-multibyte \
  --with-tlib=ncurses \
  --enable-gtk2-check --enable-gui=gtk2 \
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

make VIMRCLOC=/etc VIMRUNTIMEDIR=/usr/share/vim/%{vimdir} %{?_smp_mflags}
cp vim gvim
make clean

%configure --prefix=%{_prefix} --with-features=huge \
 --enable-pythoninterp=dynamic \
 --enable-perlinterp \
 --disable-tclinterp \
 --with-x=no \
 --enable-gui=no --exec-prefix=%{_prefix} --enable-multibyte \
 --enable-cscope --with-modified-by="<bugzilla@redhat.com>" \
 --with-tlib=ncurses \
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

make VIMRCLOC=/etc VIMRUNTIMEDIR=/usr/share/vim/%{vimdir} %{?_smp_mflags}
cp vim enhanced-vim

%check
# Run upstream tests against the final huge (non-GUI) binary before packaging
# relocates runtime/doc.  The complete upstream suite needs a richer tty/GUI
# environment and is tracked separately from these deterministic gates.
make -C src/testdir test_normal.res test_vim9_script.res

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/%{_bindir}
mkdir -p %{buildroot}/%{_datadir}/%{name}/vimfiles/{after,autoload,colors,compiler,doc,ftdetect,ftplugin,indent,keymap,lang,plugin,print,spell,syntax,tutor}
mkdir -p %{buildroot}/%{_datadir}/%{name}/vimfiles/after/{autoload,colors,compiler,doc,ftdetect,ftplugin,indent,keymap,lang,plugin,print,spell,syntax,tutor}
cp -f %{SOURCE11} .
%if %{?fedora}%{!?fedora:0} >= 16 || %{?rhel}%{!?rhel:0} >= 6
cp -f %{SOURCE15} %{buildroot}/%{_datadir}/%{name}/vimfiles/template.spec
%else
cp -f %{SOURCE14} %{buildroot}/%{_datadir}/%{name}/vimfiles/template.spec
%endif
cp -f %{SOURCE16} runtime/syntax/
cp runtime/doc/uganda.txt LICENSE
# Those aren't Linux info files but some binary files for Amiga:
rm -f README*.info


cd src
make install DESTDIR=%{buildroot} BINDIR=%{_bindir} VIMRCLOC=/etc VIMRUNTIMEDIR=/usr/share/vim/%{vimdir}
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

( cd %{buildroot}
  ln -sf vi ./%{_bindir}/rvi
  ln -sf vi ./%{_bindir}/rview
  ln -sf vi ./%{_bindir}/view
  ln -sf vi ./%{_bindir}/ex
  ln -sf vim ./%{_bindir}/rvim
  ln -sf vim ./%{_bindir}/vimdiff
  perl -pi -e "s,%{buildroot},," .%{_mandir}/man1/vim.1 .%{_mandir}/man1/vimtutor.1
  rm -f .%{_mandir}/man1/rvim.1
  ln -sf vim.1.gz .%{_mandir}/man1/vi.1.gz
  ln -sf vim.1.gz .%{_mandir}/man1/rvi.1.gz
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
        %{SOURCE3}
        # --add-category "Development;TextEditor;X-Red-Hat-Base" D\
  %else
    mkdir -p ./%{_sysconfdir}/X11/applnk/Applications
    cp %{SOURCE3} ./%{_sysconfdir}/X11/applnk/Applications/gvim.desktop
  %endif
  # ja_JP.ujis is obsolete, ja_JP.eucJP is recommended.
  ( cd ./%{_datadir}/%{name}/%{vimdir}/lang; \
    ln -sf menu_ja_jp.ujis.vim menu_ja_jp.eucjp.vim )
)

# Upstream now ships UTF-8 tutor files directly.

# Dependency cleanups
chmod 644 %{buildroot}/%{_datadir}/%{name}/%{vimdir}/doc/vim2html.pl \
 %{buildroot}/%{_datadir}/%{name}/%{vimdir}/tools/*.pl \
 %{buildroot}/%{_datadir}/%{name}/%{vimdir}/tools/vim132
chmod 644 ../runtime/doc/vim2html.pl

mkdir -p %{buildroot}/%{_sysconfdir}/profile.d
cat >%{buildroot}/%{_sysconfdir}/profile.d/vim.sh <<EOF
if [ -n "\$BASH_VERSION" -o -n "\$KSH_VERSION" -o -n "\$ZSH_VERSION" ]; then
  [ -x %{_bindir}/id ] || return
  ID=\`/usr/bin/id -u\`
  [ -n "\$ID" -a "\$ID" -le 200 ] && return
  # for bash and zsh, only if no alias is already set
  alias vi >/dev/null 2>&1 || alias vi=vim
fi
EOF
cat >%{buildroot}/%{_sysconfdir}/profile.d/vim.csh <<EOF
if ( -x /usr/bin/id ) then
    if ( "\`/usr/bin/id -u\`" > 200 ) then
        alias vi vim
    endif
endif
EOF
chmod 0644 %{buildroot}/%{_sysconfdir}/profile.d/*
install -p -m644 %{SOURCE4} %{buildroot}/%{_sysconfdir}/vimrc
install -p -m644 %{SOURCE4} %{buildroot}/%{_sysconfdir}/virc
%if %{?rhel}%{!?rhel:0} >= 7
sed -i -e "s/augroup fedora/augroup redhat/" %{buildroot}/%{_sysconfdir}/vimrc
sed -i -e "s/augroup fedora/augroup redhat/" %{buildroot}/%{_sysconfdir}/virc
%endif
(cd %{buildroot}/%{_datadir}/%{name}/%{vimdir}/doc;
 gzip -n -9 *.txt
 gzip -n -d help.txt.gz version7.txt.gz sponsor.txt.gz
 cp %{SOURCE12} .
 cat tags | sed -e 's/\t\(.*.txt\)\t/\t\1.gz\t/;s/\thelp.txt.gz\t/\thelp.txt\t/;s/\tversion7.txt.gz\t/\tversion7.txt\t/;s/\tsponsor.txt.gz\t/\tsponsor.txt\t/' > tags.new; mv -f tags.new tags
cat >> tags << EOF
vi_help.txt	vi_help.txt	/*vi_help.txt*
vi-author.txt	vi_help.txt	/*vi-author*
vi-Bram.txt	vi_help.txt	/*vi-Bram*
vi-Moolenaar.txt	vi_help.txt	/*vi-Moolenaar*
vi-credits.txt	vi_help.txt	/*vi-credits*
EOF
LANG=C sort tags > tags.tmp; mv tags.tmp tags
 )
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
for i in virc.5 vimrc.5; do 
  echo ".so man1/vim.1" > %{buildroot}/%{_mandir}/man5/$i
done
touch %{buildroot}/%{_datadir}/%{name}/vimfiles/doc/tags

%post X11
touch --no-create %{_datadir}/icons/hicolor
if [ -x /%{_bindir}/gtk-update-icon-cache ]; then
  gtk-update-icon-cache --ignore-theme-index -q %{_datadir}/icons/hicolor
fi
update-desktop-database &> /dev/null ||:

%postun X11
touch --no-create %{_datadir}/icons/hicolor
if [ -x /%{_bindir}/gtk-update-icon-cache ]; then
  gtk-update-icon-cache --ignore-theme-index -q %{_datadir}/icons/hicolor
fi
update-desktop-database &> /dev/null ||:

%clean
rm -rf %{buildroot}

%files common
%defattr(-,root,root)
%config(noreplace) %{_sysconfdir}/vimrc
%doc README* LICENSE 
%doc runtime/docs
%doc Changelog.rpm
%dir %{_datadir}/%{name}
%{_datadir}/%{name}/vimfiles/template.spec
%dir %{_datadir}/%{name}/%{vimdir}
%{_datadir}/%{name}/%{vimdir}/LICENSE
%{_datadir}/%{name}/%{vimdir}/README.txt
%{_datadir}/%{name}/%{vimdir}/import
%{_datadir}/%{name}/%{vimdir}/pack
%{_datadir}/%{name}/%{vimdir}/lang/*/LC_MESSAGES/*.mo
%{_mandir}/*/man1/*
%{_datadir}/%{name}/%{vimdir}/autoload
%{_datadir}/%{name}/%{vimdir}/colors
%{_datadir}/%{name}/%{vimdir}/compiler
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
%{_mandir}/man1/ex.*
%{_mandir}/man1/gex.*
%{_mandir}/man1/gview.*
%{_mandir}/man1/gvim*
%{_mandir}/man1/rvi.*
%{_mandir}/man1/rview.*
%{_mandir}/man1/rvim.*
%{_mandir}/man1/vi.*
%{_mandir}/man1/view.*
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
%defattr(-,root,root)
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
%defattr(-,root,root)
%config(noreplace) %{_sysconfdir}/virc
%{_bindir}/ex
%{_bindir}/vi
%{_bindir}/view
%{_bindir}/rvi
%{_bindir}/rview
%{_mandir}/man1/vim.*
%{_mandir}/man1/vi.*
%{_mandir}/man1/ex.*
%{_mandir}/man1/rvi.*
%{_mandir}/man1/rview.*
%{_mandir}/man1/view.*
%{_mandir}/man5/virc.*

%files enhanced
%defattr(-,root,root)
%{_bindir}/vim
%{_bindir}/rvim
%{_bindir}/vimdiff
%{_bindir}/vimtutor
%config(noreplace) %{_sysconfdir}/profile.d/vim.*

%files filesystem
%defattr(-,root,root)
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
%{_datadir}/icons/locolor/*/apps/*
%defattr(-,root,root)
%if "%{desktop_file}" == "1"
/%{_datadir}/applications/*
%else
/%{_sysconfdir}/X11/applnk/*/gvim.desktop
%endif
%{_bindir}/gvimtutor
%{_bindir}/gvim
%{_bindir}/gvimdiff
%{_bindir}/gview
%{_bindir}/gex
%{_bindir}/vimx
%{_bindir}/evim
%{_mandir}/man1/evim.*
%{_datadir}/icons/hicolor/*/apps/*

%changelog
* Wed Sep 30 2020 Zdenek Dohnal <zdohnal@redhat.com> - 2:7.4.629-8
- 1833186 - gvim consums 100% cpu under certain condition

* Tue Jan 21 2020 Zdenek Dohnal <zdohnal@redhat.com> - 2:7.4.629-7
- 1743070 - manpage of vim is garbled in Japanese locale

* Fri Jun 14 2019 Zdenek Dohnal <zdohnal@redhat.com> - 2:7.4.629-6
- increment release enough to get CVE fix 1719964 for clients migrated from RHEL6 

* Fri Jun 14 2019 Zdenek Dohnal <zdohnal@redhat.com> - 2:7.4.629-3
- 1719964 - CVE-2019-12735 arbitrary command execution in getchar.c [rhel-7.7]

* Mon Jan 21 2019 Zdenek Dohnal <zdohnal@redhat.com> - 2:7.4.629-2
- adding several additional changes for #1377316 from upstream

* Wed Jan 16 2019 Zdenek Dohnal <zdohnal@redhat.com> - 2:7.4.629-1
- 1563419 - Vim in RHEL 7 is older than VIM in RHEL 6 (Rebase)
- 1377316 - [RFE] make _remote_ vim doing the right decisions about 'set background'

* Mon Jun 18 2018 Zdenek Dohnal <zdohnal@redhat.com> - 2:7.4.160-5
- 1490927 - vim dumps core when system reboots

* Tue Sep 05 2017 Zdenek Dohnal <zdohnal@redhat.com> - 2:7.4.160-4
- fixed upstream tests, which failed after last build

* Wed Aug 23 2017 Zdenek Dohnal <zdohnal@redhat.com> - 2:7.4.160-3
- 1267826 - Include c++11 syntax highlighting in vim
- 1319760 - [RFE] Vim should support blowfish2, plus ensure that RHEL6 encrypted files can be opened in RHEL7

* Fri Jan 20 2017 Zdenek Dohnal <zdohnal@redhat.com> - 2:7.4.160-2
- 1383902 - CPU spikes to 100% and timeouts observed in strace when opening yaml extensions using vim

* Mon Dec 12 2016 Karsten Hopp <karsten@redhat.com> 7.4.160-1.1
- add fix for CVE-2016-1248

* Wed Jan 29 2014 Karsten Hopp <karsten@redhat.com> 7.4.160-1
- patchlevel 160
- Resolves: rhbz#1059321

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
