#!/usr/bin/env bash
# 本地行为测试辅助：在干净的对应平台容器中逐场景执行 test-install.sh。
# 用法: local-test.sh <el7|el8|centos7|all> [场景...]（缺省跑全部5场景）
set -uo pipefail

EL="${1:?usage: local-test.sh <el7|el8|centos7|all> [scenario...]}"
shift || true
SCENARIOS=("$@")
[ ${#SCENARIOS[@]} -eq 0 ] && SCENARIOS=(fresh upgrade reinstall uninstall symlink-guard)

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/platforms.sh
source "$REPO_ROOT/scripts/platforms.sh"
OVERALL=0

run_el() {
	local el="$1" scenario img
	img="$(image_for "$el")" || exit 2
	for scenario in "${SCENARIOS[@]}"; do
		echo ""
		echo "########## $el / $scenario ##########"
		if ! sudo docker run --rm \
			-v "$REPO_ROOT":/src:ro \
			-e SRC_DIR=/src \
			"$img" \
			bash /src/scripts/test-install.sh "$el" "$scenario"; then
			echo "!!!!! $el/$scenario FAILED"
			OVERALL=1
		fi
	done
}

case "$EL" in
all) run_el el7 && run_el el8 && run_el centos7 ;;
*) run_el "$EL" ;;
esac

exit $OVERALL
