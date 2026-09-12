#!/usr/bin/env bash
# 本地（宿主机）行为测试辅助：在干净的 UBI 容器中逐场景执行 test-install.sh。
# 用法: local-test.sh <el7|el8|all> [场景...]（缺省跑全部4场景）
set -uo pipefail

EL="${1:?usage: local-test.sh <el7|el8|all> [scenario...]}"
shift || true
SCENARIOS=("$@")
[ ${#SCENARIOS[@]} -eq 0 ] && SCENARIOS=(fresh upgrade reinstall uninstall symlink-guard)

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# 与 local-build.sh / workflow 保持一致的固定 digest
UBI7="registry.access.redhat.com/ubi7/ubi@sha256:046e525722f14702c360dc6092324af7c21656e76b0c254b067871f1d4d3df68"
UBI8="registry.access.redhat.com/ubi8/ubi@sha256:ed721ca811f29fa0fd8a4666aec2fb6771f3defbecc708a973d0b711d6f09293"
OVERALL=0

image_for() {
	case "$1" in
	el7) echo "$UBI7" ;;
	el8) echo "$UBI8" ;;
	esac
}

run_el() {
	local el="$1" scenario img
	img="$(image_for "$el")"
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
all) run_el el7 && run_el el8 ;;
*) run_el "$EL" ;;
esac

exit $OVERALL
