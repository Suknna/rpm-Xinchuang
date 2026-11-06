#!/usr/bin/env bash
# Shared platform mapping and pinned official images for CI and local builds.
# centos7 reuses EL7 packaging, but keeps its own build tree, RPM suffix and releases.
platform_el() {
	case "$1" in
	el7 | centos7) echo el7 ;;
	el8) echo el8 ;;
	*) echo "unsupported platform: $1 (expect el7|el8|centos7)" >&2; return 2 ;;
	esac
}

image_for() {
	case "$1" in
	el7) echo 'registry.access.redhat.com/ubi7/ubi@sha256:046e525722f14702c360dc6092324af7c21656e76b0c254b067871f1d4d3df68' ;;
	el8) echo 'registry.access.redhat.com/ubi8/ubi@sha256:ed721ca811f29fa0fd8a4666aec2fb6771f3defbecc708a973d0b711d6f09293' ;;
	# Docker Official Image centos:7.9.2009, linux/amd64 manifest.
	centos7) echo 'docker.io/library/centos@sha256:dead07b4d8ed7e29e98de0f4504d87e8880d4347859d839686a31da35a3b532f' ;;
	# Docker Official Image ubuntu:22.04; callers explicitly select linux/amd64.
	ubuntu2204) echo 'docker.io/library/ubuntu@sha256:076e7bf82319619f28dd0aa9c02ab34b055ad37100395b4f49a2ffba04fb5e11' ;;
	*) echo "unsupported platform: $1 (expect el7|el8|centos7|ubuntu2204)" >&2; return 2 ;;
	esac
}
