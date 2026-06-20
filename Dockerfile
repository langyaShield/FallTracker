# ============================================================
# Stage 1: Build frontend (Vue 3 + Vite)
# ============================================================
# Use daocloud mirror because default docker.io may be blocked in CN networks
FROM docker.m.daocloud.io/library/node:22-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable && corepack prepare pnpm@9 --activate && pnpm install

COPY frontend/ ./
RUN pnpm build

# ============================================================
# Stage 2: Backend runtime (Python + served frontend)
# ============================================================
FROM docker.m.daocloud.io/library/python:3.12-slim

WORKDIR /app

# Use Aliyun mirrors for faster and reliable package downloads
RUN (sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g; s|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list 2>/dev/null; \
     sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g; s|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null) && \
    apt-get update --allow-releaseinfo-change

# Install system deps: tesseract (OCR), fonts, and cleanup
# Retry up to 3 times in case of transient mirror errors
RUN for i in 1 2 3; do \
        apt-get install -y --no-install-recommends \
            tesseract-ocr \
            tesseract-ocr-eng \
            libglib2.0-0 \
            libsm6 \
            libxext6 \
            libxrender-dev \
            libgomp1 \
            poppler-utils \
        && break \
        || { echo "Attempt $i failed, retrying..."; sleep 2; }; \
    done && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy backend code (keeps the same directory structure as the repo)
COPY backend/requirements.txt ./backend/
RUN pip config set global.index-url https://mirrors.cloud.tencent.com/pypi/simple && \
    pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/

# Copy built frontend from stage 1
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# Create persistent data directories
RUN mkdir -p /app/backend/data /app/backend/uploads

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run with uvicorn — single worker for 2-core server (1 core for app, 1 for system)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--app-dir", "/app/backend"]
