#!/usr/bin/env bash
# 本地（宿主机）构建辅助：与 GitHub Actions 使用完全相同的容器内脚本。
# 用法: local-build.sh <el7|el8|centos7|all>
set -euo pipefail

EL="${1:?usage: local-build.sh <el7|el8|centos7|all>}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# shellcheck source=scripts/platforms.sh
source "$REPO_ROOT/scripts/platforms.sh"

build_one() {
	local el="$1" image
	image="$(image_for "$el")"
	sudo docker run --rm \
		-v "$REPO_ROOT":/src \
		-e SRC_DIR=/src \
		"$image" \
		bash /src/scripts/build-in-container.sh "$el"
}

case "$EL" in
all) build_one el7 && build_one el8 && build_one centos7 ;;
*) build_one "$EL" ;;
esac
