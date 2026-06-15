#!/bin/bash
# Run falltracker with internal storage (no bind mount - test first)
# 用法: wsl -e bash scripts/wsl_docker_run.sh
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export DOCKER_BIN="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
export PATH="$(dirname "$DOCKER_BIN"):$PATH"

cd "$PROJECT_ROOT"

docker stop falltracker 2>/dev/null
docker rm falltracker 2>/dev/null

# JWT_SECRET 优先级:
#   1) 环境变量 JWT_SECRET（用户自己 export 的）
#   2) backend/.env 文件中的 SECRET_KEY
#   3) 默认占位（仅 dev 用途，启动会打印 security warning）
JWT_SECRET_VAL="${JWT_SECRET:-}"
if [ -z "$JWT_SECRET_VAL" ] && [ -f backend/.env ]; then
  JWT_SECRET_VAL=$(grep -E '^SECRET_KEY=' backend/.env | head -1 | cut -d'=' -f2- | tr -d '"' || true)
fi
if [ -z "$JWT_SECRET_VAL" ]; then
  JWT_SECRET_VAL="dev-secret-please-change"
  echo "WARNING: 未提供 JWT_SECRET，使用默认 dev 值（仅本地开发）。生产请设置 backend/.env 或 export JWT_SECRET=..."
fi

echo "=== Starting falltracker container ==="
docker run -d \
  --name falltracker \
  -p 8000:8000 \
  -p 5173:80 \
  -e JWT_SECRET="$JWT_SECRET_VAL" \
  falltracker:latest 2>&1

echo "=== Wait 10s for boot ==="
sleep 10

echo "=== Container status ==="
docker ps | grep falltracker
echo "=== Recent logs ==="
docker logs --tail 30 falltracker 2>&1
echo "=== Health check (backend) ==="
docker exec falltracker python -c "import urllib.request; r = urllib.request.urlopen('http://localhost:8000/health'); print('HEALTH:', r.read().decode())" 2>&1
