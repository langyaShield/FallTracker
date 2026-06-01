# ============================================================
# Stage 1: Build frontend (Vue 3 + Vite)
# ============================================================
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable && corepack prepare pnpm@9 --activate && pnpm install

COPY frontend/ ./
RUN pnpm build

# ============================================================
# Stage 2: Backend runtime (Python + served frontend)
# ============================================================
FROM python:3.12-slim

WORKDIR /app

# Use Tencent Cloud apt mirror for faster package downloads
RUN (sed -i 's|http://deb.debian.org|http://mirrors.tencentyun.com|g' /etc/apt/sources.list 2>/dev/null; \
     sed -i 's|http://security.debian.org|http://mirrors.tencentyun.com/debian-security|g' /etc/apt/sources.list 2>/dev/null; \
     sed -i 's|http://deb.debian.org|http://mirrors.tencentyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
     sed -i 's|http://security.debian.org|http://mirrors.tencentyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null) && \
    apt-get update

# Install system deps: tesseract (OCR), fonts, and cleanup
RUN apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender-dev \
        libgomp1 \
        poppler-utils \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy backend code (keeps the same directory structure as the repo)
COPY backend/requirements.txt ./backend/
RUN pip config set global.index-url https://mirrors.tencentyun.com/pypi/simple && \
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

# Run with uvicorn — use chdir to make backend/ the working directory
# so that internal imports (e.g. "from app.config import settings") resolve correctly
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--app-dir", "/app/backend"]
