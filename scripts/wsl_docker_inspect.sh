#!/bin/bash
export DOCKER_BIN="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
export PATH="$(dirname "$DOCKER_BIN"):$PATH"
echo "=== Container frontend dist ==="
docker exec falltracker ls -la /app/frontend/dist/ 2>&1
echo "=== Container uvicorn process ==="
docker exec falltracker ps -ef 2>&1 | head -5
echo "=== OpenAPI (10 lines) ==="
curl -s http://localhost:8000/openapi.json 2>&1 | head -c 500
