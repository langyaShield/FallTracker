#!/usr/bin/env bash
#
# FallTracker Docker Deployment Script
# Server: 2GB RAM, 2 CPU cores
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "============================================"
echo " FallTracker Docker Deployment"
echo "============================================"
echo ""

# Step 1: Check prerequisites
echo "[1/4] Checking prerequisites..."

if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker is not installed."
    echo "Please install Docker first: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! command -v docker compose &>/dev/null; then
    echo "ERROR: docker compose plugin is not installed."
    exit 1
fi

MEM_TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_TOTAL_MB=$((MEM_TOTAL_KB / 1024))
echo "  Server memory: ${MEM_TOTAL_MB}MB"
echo "  CPU cores: $(nproc)"
echo ""

if [ "$MEM_TOTAL_MB" -lt 1500 ]; then
    echo "WARNING: Server has less than 1.5GB RAM."
    echo "  Consider reducing mem_limit in docker-compose.yml."
    echo ""
fi

# Step 2: Create data directories
echo "[2/4] Creating persistent data directories..."
mkdir -p data/db data/uploads
echo "  ✓ data/db/"
echo "  ✓ data/uploads/"
echo ""

# Step 3: Copy .env if not exists
echo "[3/4] Checking .env configuration..."
if [ ! -f backend/.env ]; then
    # Generate a random SECRET_KEY (64 hex chars = 256 bits)
    GENERATED_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || head -c 64 /dev/urandom | od -An -tx1 | tr -d ' \n')
    cat > backend/.env << ENVEOF
DATABASE_URL=sqlite:///./falltracker.db
SECRET_KEY=${GENERATED_SECRET}
ACCESS_TOKEN_EXPIRE_MINUTES=10080
LLM_API_KEY=
LLM_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
ENVEOF
    echo "  ✓ Created backend/.env with randomly generated SECRET_KEY"
    echo "  ⚠ Please review backend/.env and configure LLM_API_KEY if needed"
else
    echo "  ✓ backend/.env already exists"
fi
echo ""

# Step 4: Build and start
echo "[4/4] Building and starting containers..."
echo "  This may take a few minutes on first run..."
echo ""

docker compose build --pull
echo ""
docker compose up -d
echo ""

# Wait for health check
echo "  Waiting for service to be healthy..."
RETRIES=0
MAX_RETRIES=30
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
    RETRIES=$((RETRIES + 1))
    if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
        echo "  ✗ Service failed to start within $MAX_RETRIES seconds."
        echo "    Check logs: docker compose logs"
        exit 1
    fi
    sleep 2
done

echo ""
echo "============================================"
echo " Deployment Complete!"
echo "============================================"
echo ""
echo "  App:     http://YOUR_SERVER_IP"
echo "  Health:  http://YOUR_SERVER_IP/health"
echo ""
echo "  Useful commands:"
echo "    docker compose logs -f    # View logs"
echo "    docker compose ps         # Check status"
echo "    docker compose down       # Stop services"
echo "    docker compose restart    # Restart"
echo ""

# Show resource usage
docker compose ps
