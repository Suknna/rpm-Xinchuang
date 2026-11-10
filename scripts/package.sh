#!/usr/bin/env bash
# 统一构建/验证/测试宿主入口：本地（local-* 转发）与 CI 共用同一实现。
#
# 用法:
#   scripts/package.sh build <platform> <package> [version] [url]
#       在平台容器内构建并执行产物门禁（RPM: verify-rpms；DEB 门禁内置于
#       build-openssh-deb.sh 末尾的 verify-debs）。openssh 可省略 version/url
#       （默认取自共享 spec / 固定官方源）；upstream 组件必须提供 version 与
#       https url。
#   scripts/package.sh test <platform> <package> [scenario...]
#       在独立干净容器中做安装行为测试：openssh 跑 5 场景（缺省全跑），
#       upstream 组件跑单容器 smoke（不接场景参数）。
#       测试版本一律读该目标 dist/ 的构建元数据（RPM: build.spec 的实际版本；
#       DEB: build.json），缺失/与目标不符/格式非法直接失败，绝不回退源 spec——
#       因为 build 允许显式新版本而源 spec 保持旧值。
#
# 平台/包元数据由 scripts/project_config.py（宿主解析 platforms/<id>/platform.yaml）
# 以 `shell <platform> <package>` 输出 shlex.quote 的环境变量赋值提供；
# 容器内脚本不读 YAML、不依赖 Python，只消费注入的环境变量。
#
# 词表契约：PACKAGE_KIND=openssh-rpm|upstream-rpm|openssh-deb（由
# scripts/project_config.py 按 包名+family 派生），非法值直接报错。
#
# 输出契约: dist/<platform>/<package>/（DIST_DIR 由配置下发）内含包产物、
# SHA256SUMS、SOURCE-SHA256SUM 与本次构建的 spec 副本 build.spec（RPM）；
# DEB 另有 build.json / changelog 作为发布凭据。源 spec 永不修改。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

usage() {
	cat >&2 <<'EOF'
usage: scripts/package.sh build <platform> <package> [version] [url]
       scripts/package.sh test <platform> <package> [scenario...]
EOF
	exit 2
}

[ $# -ge 3 ] || usage
ACTION="$1"
shift
case "$ACTION" in
build | test) ;;
*) usage ;;
esac
PLATFORM="$1"
shift
PACKAGE="$1"
shift

die() { echo "package.sh: $*" >&2; exit 2; }

# 宿主 Python 解释器统一入口：workflow/CI 可显式注入 PYTHON=/usr/bin/python3
# （系统解释器才装了 PyYAML），避免 PATH 上其他 Python 缺依赖。
# 仅宿主侧生效；容器内脚本仍用容器自带的 python3。
PYTHON="${PYTHON:-/usr/bin/python3}"
command -v "$PYTHON" >/dev/null 2>&1 || {
	die "PYTHON interpreter not found: '$PYTHON' (set PYTHON=/usr/bin/python3)"
}

# 平台/包配置（宿主解析 YAML；输出已 shlex.quote，可安全 eval）。
CONFIG_OUTPUT="$("$PYTHON" scripts/project_config.py shell "$PLATFORM" "$PACKAGE")"
eval "$CONFIG_OUTPUT"

: "${BUILD_PLATFORM:?project_config did not export BUILD_PLATFORM}"
: "${PACKAGE_KIND:?project_config did not export PACKAGE_KIND}"
: "${PACKAGE_FAMILY:?project_config did not export PACKAGE_FAMILY}"
: "${BUILD_IMAGE:?project_config did not export BUILD_IMAGE}"
: "${SPEC_PATH:?project_config did not export SPEC_PATH}"
: "${DIST_DIR:?project_config did not export DIST_DIR}"
[ "$BUILD_PLATFORM" = "$PLATFORM" ] || {
	echo "project_config platform mismatch: BUILD_PLATFORM=$BUILD_PLATFORM, requested $PLATFORM" >&2
	exit 2
}
PACKAGING_EL="${PACKAGING_EL:-}"
ASSETS_PATH="${ASSETS_PATH:-}"
PACKAGING_PATH="${PACKAGING_PATH:-}"
AUX_SOURCE="${AUX_SOURCE:-}"
PRE_BUILD="${PRE_BUILD:-}"

# 包种类（契约词表，非法值立即报错）。
KIND="$PACKAGE_KIND"
case "$KIND" in
openssh-rpm | upstream-rpm | openssh-deb) ;;
*)
	echo "unsupported PACKAGE_KIND: $PACKAGE_KIND (expect openssh-rpm|upstream-rpm|openssh-deb)" >&2
	exit 2
	;;
esac

case "$KIND" in
*-deb) ;; # DEB 容器自行处理 apt 源
*)
	[ -n "$PACKAGING_EL" ] || { echo "PACKAGING_EL missing for rpm kind $KIND" >&2; exit 2; }
	;;
esac

DOCKER=(docker)
docker info >/dev/null 2>&1 || DOCKER=(sudo docker)

# 统一容器参数：构建可写挂载、门禁/测试只读挂载；DEB 平台显式 amd64。
run_container() { # run_container <rw|ro> <command...>
	local mode="$1"
	shift
	local mount="$REPO_ROOT:/src"
	[ "$mode" = ro ] && mount="$REPO_ROOT:/src:ro"
	local -a args=(run --rm -v "$mount")
	[ "$KIND" = openssh-deb ] && args+=(--platform linux/amd64)
	args+=(
		-e SRC_DIR=/src
		-e "BUILD_PLATFORM=$PLATFORM"
		-e "PACKAGE=$PACKAGE"
		-e "PACKAGE_KIND=$PACKAGE_KIND"
		-e "PACKAGE_FAMILY=$PACKAGE_FAMILY"
		-e "PACKAGING_EL=$PACKAGING_EL"
		-e "SPEC_PATH=$SPEC_PATH"
		-e "ASSETS_PATH=$ASSETS_PATH"
		-e "PACKAGING_PATH=$PACKAGING_PATH"
		-e "AUX_SOURCE=$AUX_SOURCE"
		-e "PRE_BUILD=$PRE_BUILD"
		-e "DIST_DIR=$DIST_DIR"
		-e "VERSION=$VERSION"
	)
	[ -n "${BUILD_SOURCE_CACHE:-}" ] && args+=(-e "BUILD_SOURCE_CACHE=$BUILD_SOURCE_CACHE")
	"${DOCKER[@]}" "${args[@]}" "$BUILD_IMAGE" "$@"
}

# 配置触发的宿主预构建步骤（如 NTP 静态 OpenSSL 预取）。
# pre_build 是钩子名（token），映射到 scripts/prebuild/<token>.sh。
run_pre_build() {
	[ -n "$PRE_BUILD" ] || return 0
	local target="$REPO_ROOT/scripts/prebuild/$PRE_BUILD.sh"
	if [ ! -f "$target" ]; then
		die "PRE_BUILD step not found: $PRE_BUILD -> $target"
	fi
	echo "== [$PLATFORM/$PACKAGE] pre-build: $PRE_BUILD"
	SRC_DIR="$REPO_ROOT" BUILD_PLATFORM="$PLATFORM" PACKAGE="$PACKAGE" \
		SPEC_PATH="$SPEC_PATH" bash "$target" "$REPO_ROOT" "$PLATFORM"
}

# ---- 构建阶段：源 spec 宏只是缺省值（build 会把版本写进副本）----
spec_ver_macro() { # %global ver（OpenSSH 共享 spec 的版本宏）
	sed -n 's/^%global ver[[:space:]]\+//p' "$SPEC_PATH" | head -1 | tr -d '[:space:]'
}

valid_openssh_version() { [[ "$1" =~ ^[0-9]+\.[0-9]+p[0-9]+$ ]]; }

# ---- 测试阶段：版本一律来自该目标的构建元数据，绝不回退源 spec ----
# （build 允许显式新版本而源 spec 保持旧值，测试必须对齐实际产物版本。）
build_spec_version() { # 从 dist/<platform>/<package>/build.spec 解析；$1=行首标记
	local build_spec="$REPO_ROOT/$DIST_DIR/build.spec"
	[ -f "$build_spec" ] || die "missing build metadata: $DIST_DIR/build.spec (run 'scripts/package.sh build $PLATFORM $PACKAGE' first)"
	local version
	version="$(sed -n "s/^$1[[:space:]]\+//p" "$build_spec" | head -1 | tr -d '[:space:]')"
	[ -n "$version" ] || die "cannot parse version from $DIST_DIR/build.spec"
	printf '%s' "$version"
}

deb_dist_version() { # DEB 实际版本与目标归属来自 build.json（发布 receipt）
	local meta="$REPO_ROOT/$DIST_DIR/build.json"
	[ -f "$meta" ] || die "missing build metadata: $DIST_DIR/build.json (run 'scripts/package.sh build $PLATFORM $PACKAGE' first)"
	local out version package platform
	out="$("$PYTHON" -c 'import json, sys; d = json.load(open(sys.argv[1])); print(d.get("version", ""), d.get("package", ""), d.get("platform", ""))' "$meta" 2>/dev/null)" \
		|| die "unreadable build metadata: $DIST_DIR/build.json"
	read -r version package platform <<<"$out"
	[ -n "$version" ] || die "missing version in $DIST_DIR/build.json"
	[ "$package" = "$PACKAGE" ] && [ "$platform" = "$PLATFORM" ] \
		|| die "$DIST_DIR/build.json does not match target $PLATFORM/$PACKAGE (package=$package, platform=$platform)"
	printf '%s' "$version"
}

VERSION=""
SOURCE_URL=""
SCENARIOS=()
if [ "$ACTION" = build ]; then
	[ $# -le 2 ] || usage
	[ $# -ge 1 ] && VERSION="$1"
	[ $# -ge 2 ] && SOURCE_URL="$2"
	case "$KIND" in
	openssh-rpm | openssh-deb)
		[ -z "$SOURCE_URL" ] || die "build $KIND does not take a URL argument (sources and mirrors are pinned)"
		[ -n "$VERSION" ] || VERSION="$(spec_ver_macro)"
		# 显式版本与缺省版本都在创建目录/启动容器前完成校验。
		valid_openssh_version "$VERSION" || die "invalid OpenSSH version: $VERSION (expect X.YpZ)"
		;;
	upstream-rpm)
		[ -n "$VERSION" ] && [ -n "$SOURCE_URL" ] || die "upstream build requires <version> and <url>"
		[[ "$VERSION" =~ ^[0-9][A-Za-z0-9._+~-]*$ ]] || die "invalid version: $VERSION"
		[[ "$SOURCE_URL" == https://* && "$SOURCE_URL" != *..* ]] || die "invalid source URL: $SOURCE_URL"
		;;
	esac
else
	SCENARIOS=("$@")
	case "$KIND" in
	openssh-rpm)
		VERSION="$(build_spec_version '%global ver')"
		valid_openssh_version "$VERSION" || die "$DIST_DIR/build.spec version malformed: $VERSION"
		;;
	openssh-deb)
		VERSION="$(deb_dist_version)"
		valid_openssh_version "$VERSION" || die "$DIST_DIR/build.json version malformed: $VERSION"
		;;
	upstream-rpm)
		[ "${#SCENARIOS[@]}" -eq 0 ] || die "upstream packages run a single smoke test; scenario arguments are not accepted"
		VERSION="$(build_spec_version 'Version:')"
		[[ "$VERSION" =~ ^[0-9][A-Za-z0-9._+~-]*$ ]] || die "$DIST_DIR/build.spec version malformed: $VERSION"
		;;
	esac
	if [ "$KIND" != openssh-deb ]; then
		# 宿主侧 Name 字面量识别（本仓 spec 均为字面 Name，不做通用宏展开）；
		# 容器内 rpm -qp 的完整身份核对在 rpm-identity.sh。
		spec_name="$(sed -n 's/^Name:[[:space:]]*//p' "$REPO_ROOT/$DIST_DIR/build.spec" | head -1 | tr -d '[:space:]')"
		[ "$spec_name" = "$PACKAGE" ] || die "$DIST_DIR/build.spec Name '$spec_name' does not match target package '$PACKAGE'"
	fi
fi

if [ "$ACTION" = build ]; then
	# 先以 runner 身份建好产物目录，避免容器内以 root 创建导致 CI 无法追加。
	mkdir -p "$REPO_ROOT/$DIST_DIR"
	run_pre_build
	case "$KIND" in
	openssh-rpm)
		echo "== [$PLATFORM/$PACKAGE] 容器内构建（含上游 regress 测试）"
		run_container rw bash /src/scripts/build-in-container.sh
		echo "== [$PLATFORM/$PACKAGE] RPM 产物门禁"
		run_container ro bash /src/scripts/verify-rpms.sh "$PLATFORM"
		;;
	upstream-rpm)
		echo "== [$PLATFORM/$PACKAGE] 容器内构建"
		run_container rw bash /src/scripts/build-upstream.sh \
			"$PACKAGE" "$PLATFORM" "$VERSION" "$SOURCE_URL"
		;;
	openssh-deb)
		echo "== [$PLATFORM/$PACKAGE] 容器内构建（含 DEB 门禁）"
		run_container rw bash /src/scripts/build-openssh-deb.sh "$VERSION"
		;;
	esac
	echo "== [$PLATFORM/$PACKAGE] build 完成: $DIST_DIR"
else
	FAIL=0
	case "$KIND" in
	openssh-rpm | openssh-deb)
		[ "${#SCENARIOS[@]}" -gt 0 ] || SCENARIOS=(fresh upgrade reinstall uninstall symlink-guard)
		for scenario in "${SCENARIOS[@]}"; do
			echo "########## $PLATFORM/$PACKAGE / $scenario ##########"
			if [ "$KIND" = openssh-rpm ]; then
				run_container ro bash /src/scripts/test-install.sh "$PLATFORM" "$scenario" || FAIL=1
			else
				run_container ro bash /src/scripts/test-openssh-deb.sh "$scenario" "$VERSION" || FAIL=1
			fi
		done
		;;
	upstream-rpm)
		echo "########## $PLATFORM/$PACKAGE smoke ##########"
		run_container ro bash /src/scripts/test-upstream-install.sh \
			"$PACKAGE" "$PLATFORM" "$VERSION" || FAIL=1
		;;
	esac
	if [ "$FAIL" -eq 0 ]; then
		echo "== [$PLATFORM/$PACKAGE] test 通过"
	else
		echo "== [$PLATFORM/$PACKAGE] test 失败" >&2
	fi
	exit "$FAIL"
fi
