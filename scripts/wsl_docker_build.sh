#!/bin/bash
# WSL helper: build the Docker image
# 用法: wsl -e bash scripts/wsl_docker_build.sh
# 项目根 = 脚本父目录
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export DOCKER_BIN="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
export PATH="$(dirname "$DOCKER_BIN"):$PATH"

cd "$PROJECT_ROOT"

echo "=== Building Docker image (falltracker:latest) from $PROJECT_ROOT ==="
docker build -t falltracker:latest -f Dockerfile . 2>&1
EXIT=$?
echo "=== Build complete. Exit code: $EXIT ==="
docker images | grep falltracker
