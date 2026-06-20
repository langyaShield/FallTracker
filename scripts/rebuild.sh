#!/usr/bin/env bash
# ============================================================
# FallTracker Docker Rebuild Script
# Limits build resources to avoid starving the server.
# Server spec: 2 CPU / 2GB RAM
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

echo "=== [1/4] Cleaning old build cache (keep last 2 builds) ==="
docker builder prune --filter "until=24h" --force 2>/dev/null || true

echo "=== [2/4] Pulling base images (cached if unchanged) ==="
docker compose pull 2>/dev/null || true

echo "=== [3/4] Building with resource limits (1GB RAM / 2 CPUs) ==="
# docker compose build doesn't support --memory/--cpus; use docker build directly.
# --cpuset-cpus=0-1 pins to the 2 available cores; --memory=1g caps RAM.
DOCKER_BUILDKIT=1 docker build \
  --memory=1g \
  --cpuset-cpus=0-1 \
  -t falltracker-main-app \
  --progress=plain \
  .

echo "=== [4/4] Restarting with zero-downtime (if already running) ==="
# Up --detach re-creates only if config/image changed; otherwise no-op.
docker compose up --detach --remove-orphans

echo ""
echo "=== Done. Cleaning up dangling images ==="
docker image prune --force 2>/dev/null || true

echo ""
echo "=== Current status ==="
docker compose ps
