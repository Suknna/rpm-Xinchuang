#!/usr/bin/env bash
# 本地行为测试辅助：统一转发到 scripts/package.sh。
# 兼容旧签名: local-test.sh <platform|all> [场景...]（包固定 openssh，5 场景缺省全跑）
# 新签名:     local-test.sh <platform|all> [package] [场景...]
# all 按 platforms/<id>/platform.yaml 动态筛选启用该包的平台，不硬编码平台清单。
set -uo pipefail

PLATFORM="${1:?usage: local-test.sh <el7|el8|centos7|ubuntu2204|all> [package] [scenario...]}"
shift
case "${1:-}" in
"" | fresh | upgrade | reinstall | uninstall | symlink-guard)
	# 旧签名：场景直接跟在平台后，包固定 openssh。
	PACKAGE="openssh"
	;;
*)
	PACKAGE="$1"
	shift
	;;
esac
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# 宿主解释器统一入口（与 package.sh 一致，见其注释）。
PYTHON="${PYTHON:-/usr/bin/python3}"
command -v "$PYTHON" >/dev/null 2>&1 || {
	echo "local-test.sh: PYTHON interpreter not found: '$PYTHON' (set PYTHON=/usr/bin/python3)" >&2
	exit 2
}

# 启用 <package> 的平台列表（宿主侧 YAML 解析与 enabled 过滤，含暂停包排除）。
enabled_platforms() {
	(cd "$ROOT" && "$PYTHON" - "$PACKAGE" <<'PY'
import sys

sys.path.insert(0, "scripts")
import project_config

package = sys.argv[1]
for target in project_config.iter_targets(project_config.load_config()):
    if target["package"] == package:
        print(target["platform"])
PY
)
}

OVERALL=0
run_one() {
	local p="$1"
	shift
	bash "$ROOT/scripts/package.sh" test "$p" "$PACKAGE" "$@" || OVERALL=1
}

case "$PLATFORM" in
all)
	mapfile -t platforms < <(enabled_platforms)
	if [ "${#platforms[@]}" -eq 0 ]; then
		echo "local-test.sh: no enabled platform builds '$PACKAGE'" >&2
		exit 2
	fi
	for p in "${platforms[@]}"; do
		run_one "$p" "$@"
	done
	;;
*)
	run_one "$PLATFORM" "$@"
	;;
esac

exit "$OVERALL"
