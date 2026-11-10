#!/usr/bin/env bash
# RPM 身份一致性校验（容器内使用，需要 rpm 命令；宿主仅做只读单元测试）。
# 断言 dist/ 下实际包的 Name/Version/Release/Arch 与目标 platform 和构建留档
# build.spec 一致：主包 <Name>-<Version>-<Release>.{x86_64,noarch}.rpm 必须存在，
# 所有非 debug 包经 rpm -qp 核对 Version/Release，Arch 属 x86_64/noarch
# （普通子包与 noarch 合理接受）。共享 el7/centos spec 的 Release 经 rpm 宏
# 展开（--define dist .<platform>，并按需定义 spec 的 %global rel）。
# 全程只读，不修改宿主/容器系统状态。
#
# 用法（source 后调用）：
#   rpm_identity_name    <build-spec>                 → Name: 字面量
#   rpm_identity_release <build-spec> <platform>     → Release 展开值（含 dist）
#   rpm_identity_verify  <dist> <build-spec> <platform> <version>

rpm_identity_name() {
	sed -n 's/^Name:[[:space:]]*//p' "$1" | head -1 | tr -d '[:space:]'
}

rpm_identity_release() { # <build-spec> <platform>
	local raw global_rel release
	local defines=(--define "dist .$2") # 数组恒非空，兼容 el7 bash 4.2 的 set -u
	raw="$(sed -n 's/^Release:[[:space:]]*//p' "$1" | head -1 | tr -d '[:space:]')"
	[ -n "$raw" ] || { echo "rpm-identity: cannot parse Release from $1" >&2; return 1; }
	# openssh 共享 spec：Release: %{rel}，展开前需带上 spec 的 %global rel 值。
	global_rel="$(sed -n 's/^%global rel \([^[:space:]]*\).*/\1/p' "$1" | head -1 | tr -d '[:space:]')"
	[ -n "$global_rel" ] && defines=(--define "rel $global_rel" "${defines[@]}")
	release="$(rpm "${defines[@]}" --eval "$raw")" ||
		{ echo "rpm-identity: cannot expand Release '$raw' for platform $2" >&2; return 1; }
	printf '%s' "$release"
}

# rpm_identity_allowed_names <build-spec> <platform>：spec 声明的全部二进制包名
# （每行一个，含 %package -n 非前缀子包，如 NTP 的 ntpdate/sntp）。
# 需要 rpmspec（rpm-build 包内的 spec 查询工具）：测试容器仅装 rpm，故按需
# 补装这一个打包工具包——与 verify-rpms 自举 cpio/binutils 同模式，
# 不安装任何编译构建依赖。解析期 %() 宏只读求值（如 source /etc/os-release）。
rpm_identity_allowed_names() {
	if ! command -v rpmspec >/dev/null 2>&1; then
		if command -v dnf >/dev/null 2>&1; then
			dnf -y -q install rpm-build
		else
			yum -y -q install rpm-build
		fi
	fi
	command -v rpmspec >/dev/null 2>&1 ||
		{ echo "rpm-identity: rpmspec unavailable (rpm-build install failed)" >&2; return 1; }
	rpmspec -q --qf '%{NAME}\n' --define "dist .$2" "$1" 2>/dev/null | sort -u
}

rpm_identity_verify() { # <dist> <build-spec> <platform> <version>
	local dist="$1" build_spec="$2" platform="$3" version="$4"
	local name release rpm info found_main=0 allowed
	local bad=0
	local nullglob_was=0
	name="$(rpm_identity_name "$build_spec")"
	[ -n "$name" ] || { echo "rpm-identity: cannot parse Name from $build_spec" >&2; return 1; }
	release="$(rpm_identity_release "$build_spec" "$platform")" || return 1
	# 归属校验：实际包名必须属于 spec 声明的二进制包集合（防同 EVR 无关包混入）。
	allowed="$(rpm_identity_allowed_names "$build_spec" "$platform")" || return 1
	[ -n "$allowed" ] || { echo "rpm-identity: no binary package names parsed from $build_spec" >&2; return 1; }
	# 主包必须以规范文件名存在（防改名/缺件；按 header 判定放在下方逐包核对）。
	shopt -q nullglob && nullglob_was=1
	shopt -s nullglob
	for rpm in "$dist/$name-$version-$release.x86_64.rpm" \
		"$dist/$name-$version-$release.noarch.rpm"; do
		[ -f "$rpm" ] && found_main=1
	done
	for rpm in "$dist"/*.rpm; do
		case "$(basename "$rpm")" in
		*-debuginfo-* | *-debugsource-*) continue ;;
		esac
		info="$(rpm -qp --qf '%{NAME} %{VERSION} %{RELEASE} %{ARCH}' "$rpm" 2>/dev/null)" || {
			echo "rpm-identity: unreadable rpm: $rpm" >&2
			bad=1
			continue
		}
		pkg_name="${info%% *}"
		pkg_version="$(printf '%s' "$info" | cut -d' ' -f2)"
		pkg_release="$(printf '%s' "$info" | cut -d' ' -f3)"
		pkg_arch="$(printf '%s' "$info" | cut -d' ' -f4)"
		if [ "$pkg_version" != "$version" ] || [ "$pkg_release" != "$release" ]; then
			echo "rpm-identity: $rpm identity mismatch: got $pkg_name-$pkg_version-$pkg_release.$pkg_arch, expected Version=$version Release=$release" >&2
			bad=1
			continue
		fi
		if [ "$(basename "$rpm")" != "$pkg_name-$pkg_version-$pkg_release.$pkg_arch.rpm" ]; then
			# 文件名必须与自身 header 身份一致（防改名冒充/错放平台目录）。
			echo "rpm-identity: filename does not match rpm header: $rpm (header says $pkg_name-$pkg_version-$pkg_release.$pkg_arch.rpm)" >&2
			bad=1
			continue
		fi
		if ! printf '%s\n' "$allowed" | grep -qxF -- "$pkg_name"; then
			echo "rpm-identity: $rpm package name '$pkg_name' is not declared by $build_spec (allowed: $(printf '%s' "$allowed" | tr '\n' ' '))" >&2
			bad=1
			continue
		fi
		case "$pkg_arch" in
		x86_64 | noarch) ;;
		*)
			echo "rpm-identity: unexpected arch in $rpm: $pkg_arch" >&2
			bad=1
			continue
			;;
		esac
		[ "$pkg_name" = "$name" ] && found_main=1
	done
	[ "$nullglob_was" = 1 ] || shopt -u nullglob
	if [ "$bad" -ne 0 ]; then
		return 1
	fi
	if [ "$found_main" -ne 1 ]; then
		echo "rpm-identity: main package $name-$version-$release.{x86_64,noarch}.rpm not found in $dist" >&2
		return 1
	fi
	echo "rpm-identity: $dist matches build.spec ($name-$version-$release, platform $platform)"
}
