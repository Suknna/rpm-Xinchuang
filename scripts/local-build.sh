#!/usr/bin/env bash
# 本地（宿主机）构建辅助：与 GitHub Actions 使用完全相同的容器内脚本。
# 用法: local-build.sh <el7|el8> [也支持 all]
set -euo pipefail

EL="${1:?usage: local-build.sh <el7|el8|all>}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 官方 UBI 基础镜像，固定 digest（升级 digest 属受控变更，需同步更新此处与 workflow）
UBI7="registry.access.redhat.com/ubi7/ubi@sha256:046e525722f14702c360dc6092324af7c21656e76b0c254b067871f1d4d3df68"
UBI8="registry.access.redhat.com/ubi8/ubi@sha256:ed721ca811f29fa0fd8a4666aec2fb6771f3defbecc708a973d0b711d6f09293"

image_for() {
	case "$1" in
	el7) echo "$UBI7" ;;
	el8) echo "$UBI8" ;;
	esac
}

build_one() {
	local el="$1"
	sudo docker run --rm \
		-v "$REPO_ROOT":/src \
		-e SRC_DIR=/src \
		"$(image_for "$el")" \
		bash /src/scripts/build-in-container.sh "$el"
}

case "$EL" in
all) build_one el7 && build_one el8 ;;
*) build_one "$EL" ;;
esac
