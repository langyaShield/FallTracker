#!/bin/bash
# WSL helper: check Windows Docker Desktop availability from WSL
# 用法: wsl -e bash scripts/wsl_docker_check.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export DOCKER_BIN="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
export PATH="$(dirname "$DOCKER_BIN"):$PATH"

echo "=== Docker info ==="
docker --version
docker ps 2>&1 | head -10
echo ""
echo "Script location: $SCRIPT_DIR"
