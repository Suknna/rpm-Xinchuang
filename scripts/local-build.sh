#!/usr/bin/env bash
# 本地构建辅助：统一转发到 scripts/package.sh（包缺省 openssh，可指定版本）。
# 用法: local-build.sh <platform|all> [package] [version]
# all 按 platforms/<id>/platform.yaml 动态筛选启用该包的平台，不硬编码平台清单。
set -euo pipefail

PLATFORM="${1:?usage: local-build.sh <el7|el8|centos7|ubuntu2204|all> [package] [version]}"
shift
PACKAGE="${1:-openssh}"
if [ "$#" -gt 0 ]; then shift; fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# 宿主解释器统一入口（与 package.sh 一致，见其注释）。
PYTHON="${PYTHON:-/usr/bin/python3}"
command -v "$PYTHON" >/dev/null 2>&1 || {
	echo "local-build.sh: PYTHON interpreter not found: '$PYTHON' (set PYTHON=/usr/bin/python3)" >&2
	exit 2
}

# 启用 <package> 的平台列表（含宿主侧 YAML 解析与 enabled 过滤，含暂停包排除）。
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

case "$PLATFORM" in
all)
	mapfile -t platforms < <(enabled_platforms)
	[ "${#platforms[@]}" -gt 0 ] || {
		echo "local-build.sh: no enabled platform builds '$PACKAGE'" >&2
		exit 2
	}
	for p in "${platforms[@]}"; do
		bash "$ROOT/scripts/package.sh" build "$p" "$PACKAGE" "$@"
	done
	;;
*)
	bash "$ROOT/scripts/package.sh" build "$PLATFORM" "$PACKAGE" "$@"
	;;
esac
