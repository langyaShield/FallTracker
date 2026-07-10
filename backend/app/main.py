import re
import sqlite3, os, logging
from contextlib import AsyncExitStack, asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import SQLAlchemyError
from starlette.staticfiles import StaticFiles
from app.config import settings
from app.database import engine, Base
from app.mcp_server import mcp, mcp_lifespan
from app.ratelimit import limiter
from app.routers import agent as agent_router
from app.routers import auth, deliveries, events, resumes, reviews, radar, statistics, settings as settings_router, notifications, backup, admin, profile, bookmarks

logger = logging.getLogger("falltracker")

# ─────────────────────────────────────────────
#  Logging Configuration (B-9)
# ─────────────────────────────────────────────
# 在应用启动时配置 logging.basicConfig，让 logger.warning/error 默认输出到控制台
# 已被 Uvicorn 接管时会被覆盖（Uvicorn 会用自家 handler），但兜底安全
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _add_column_if_not_exists(table_name: str, column_name: str, column_type: str):
    """Add a column to an existing table if it doesn't exist yet.

    B-5: use SQLAlchemy `inspect()` API instead of raw `PRAGMA table_info`.
    - Avoids duplicating table-name-to-connection-state knowledge
    - Works across MySQL/PostgreSQL/SQLite uniformly (PRAGMA is SQLite-only)
    - Falls back to raw sqlite3 ALTER for non-SQLAlchemy-tracked columns
      (e.g. tables whose ORM model was removed)
    """
    # Validate identifiers to prevent SQL injection
    if not all(c.isalnum() or c == '_' for c in table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    if not all(c.isalnum() or c == '_' for c in column_name):
        raise ValueError(f"Invalid column name: {column_name}")
    # Validate column_type: only allow known safe SQL type tokens
    _SAFE_TYPE_RE = re.compile(r"^[A-Za-z0-9() ,_']+$")
    if not _SAFE_TYPE_RE.match(column_type):
        raise ValueError(f"Invalid column type: {column_type}")

    try:
        inspector = sa_inspect(engine)
        if inspector.has_table(table_name):
            existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
            if column_name in existing_columns:
                return
    except SQLAlchemyError as e:
        # Fall back to raw SQLite PRAGMA when the engine dialect can't introspect
        logger.warning("SQLAlchemy inspect() failed for %s, falling back to PRAGMA: %s", table_name, e)

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing = [row[1] for row in cursor.fetchall()]
        if column_name not in existing:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            conn.commit()
            logger.info("Added column %s.%s (%s)", table_name, column_name, column_type)
    finally:
        conn.close()


def _create_index_if_not_exists(table_name: str, column_name: str):
    """Create an index on a column if it doesn't exist yet (SQLite-safe, idempotent)."""
    if not all(c.isalnum() or c == '_' for c in table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    if not all(c.isalnum() or c == '_' for c in column_name):
        raise ValueError(f"Invalid column name: {column_name}")
    index_name = f"ix_{table_name}_{column_name}"
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA index_list({table_name})")
        existing = {row[1] for row in cursor.fetchall()}
        if index_name not in existing:
            cursor.execute(f"CREATE INDEX {index_name} ON {table_name} ({column_name})")
            conn.commit()
            logger.info("Created index %s on %s(%s)", index_name, table_name, column_name)
    finally:
        conn.close()


def _cleanup_work_profile_fields():
    """移除已下线的「工作经历」分类历史数据（profile_fields 表中 category='work' 的行）。

    一次性数据清理，安全幂等：表不存在或无 work 行时直接返回。
    """
    table_name = "profile_fields"
    try:
        inspector = sa_inspect(engine)
        if not inspector.has_table(table_name):
            return
    except SQLAlchemyError as e:
        logger.warning("inspect() failed for %s, skip work cleanup: %s", table_name, e)
        return
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM profile_fields WHERE category = ?", ("work",))
        deleted = cursor.rowcount
        conn.commit()
        if deleted:
            logger.info("Cleaned up %d legacy 'work' profile_fields rows", deleted)
    except SQLAlchemyError as e:
        logger.warning("Failed to cleanup work profile_fields: %s", e)
    finally:
        conn.close()


Base.metadata.create_all(bind=engine)

# Patch new columns into existing tables (safe to run multiple times)
_add_column_if_not_exists("deliveries", "deadline", "DATETIME")
_add_column_if_not_exists("resumes", "ocr_text", "TEXT")
_add_column_if_not_exists("resumes", "ocr_status", "VARCHAR(20) DEFAULT 'pending'")
_add_column_if_not_exists("resumes", "ocr_progress", "INTEGER DEFAULT 0")
_add_column_if_not_exists("resumes", "file_size", "INTEGER DEFAULT 0")
_add_column_if_not_exists("resumes", "file_type", "VARCHAR(20) DEFAULT ''")
# Patch new columns into existing user_settings table
_add_column_if_not_exists("user_settings", "smtp_server", "VARCHAR(200)")
_add_column_if_not_exists("user_settings", "smtp_port", "INTEGER")
_add_column_if_not_exists("user_settings", "smtp_username", "VARCHAR(200)")
_add_column_if_not_exists("user_settings", "smtp_password", "VARCHAR(500)")
_add_column_if_not_exists("user_settings", "email_from", "VARCHAR(200)")
_add_column_if_not_exists("user_settings", "cos_secret_id", "VARCHAR(500)")
_add_column_if_not_exists("user_settings", "cos_secret_key", "VARCHAR(500)")
_add_column_if_not_exists("user_settings", "cos_bucket", "VARCHAR(200)")
_add_column_if_not_exists("user_settings", "cos_region", "VARCHAR(100)")
_add_column_if_not_exists("user_settings", "cos_path", "VARCHAR(500)")
_add_column_if_not_exists("user_settings", "cos_auto_backup_hours", "INTEGER")
_add_column_if_not_exists("users", "is_admin", "BOOLEAN DEFAULT 0")
_add_column_if_not_exists("users", "is_disabled", "BOOLEAN DEFAULT 0")
_add_column_if_not_exists("users", "token_version", "INTEGER DEFAULT 0")  # P2-8: JWT token 版本
_add_column_if_not_exists("crawler_configs", "extra_headers", "TEXT")
_add_column_if_not_exists("crawler_configs", "last_error", "VARCHAR(500)")
_add_column_if_not_exists("crawler_configs", "consecutive_failures", "INTEGER")
_add_column_if_not_exists("crawler_results", "matched_items", "TEXT")
_add_column_if_not_exists("user_settings", "email_template", "TEXT")

# 移除已下线的「工作经历」分类历史数据
_cleanup_work_profile_fields()

# Ensure indexes exist on high-frequency filter columns (idempotent)
_create_index_if_not_exists("deliveries", "user_id")
_create_index_if_not_exists("deliveries", "status")
_create_index_if_not_exists("deliveries", "deadline")
_create_index_if_not_exists("interview_events", "delivery_id")
_create_index_if_not_exists("resumes", "user_id")
_create_index_if_not_exists("reviews", "user_id")
_create_index_if_not_exists("crawler_configs", "user_id")

# Security: block startup with default/weak SECRET_KEY
_BLOCKED_SECRETS = {
    "change-me-to-a-random-secret-key",
    "falltracker-secret-key-change-me",
}
if settings.SECRET_KEY in _BLOCKED_SECRETS:
    raise RuntimeError(
        "SECURITY ERROR: Using default SECRET_KEY is not allowed. "
        "Please set a strong random SECRET_KEY in .env before starting the application."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在测试环境下不启动后台调度器（避免测试 DB 表不存在导致启动失败），但仍启动 MCP lifespan
    if os.environ.get("PYTEST_CURRENT_TEST"):
        async with mcp_lifespan(app):
            yield
        return

    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp_lifespan(app))

        from apscheduler.schedulers.background import BackgroundScheduler
        from app.services.radar.scheduler import (
            check_and_run_due_crawlers,
            notify_upcoming_interviews,
            notify_upcoming_deadlines,
        )
        from app.routers.backup import auto_backup_all_users
        from app.routers.admin import cleanup_expired_invite_codes

        scheduler = BackgroundScheduler(daemon=True)
        # 爬虫调度：每 60 秒检查一次到期的爬虫配置
        scheduler.add_job(check_and_run_due_crawlers, "interval", seconds=60, id="crawler_tick")
        # 面试提醒：每 10 分钟检查一次即将开始的面试
        scheduler.add_job(notify_upcoming_interviews, "interval", minutes=10, id="interview_reminder")
        # 截止日期预警：每小时检查一次 48h 内到期的投递
        scheduler.add_job(notify_upcoming_deadlines, "interval", hours=1, id="deadline_warning")
        # COS 自动备份：每 30 分钟检查一次是否需要自动备份
        scheduler.add_job(auto_backup_all_users, "interval", minutes=30, id="auto_backup")
        # 过期邀请码清理：每小时检查一次并删除过期邀请码
        scheduler.add_job(cleanup_expired_invite_codes, "interval", hours=1, id="invite_cleanup")
        scheduler.start()

        yield

        scheduler.shutdown(wait=False)


# P0-2.1: 生产环境关闭 API 文档，防止端点结构泄露
_debug = settings.DEBUG
app = FastAPI(
    title="FallTracker API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _debug else None,
    redoc_url="/redoc" if _debug else None,
    openapi_url="/openapi.json" if _debug else None,
)
app.state.limiter = limiter


# ─────────────────────────────────────────────
#  Global Exception Handlers (B-11)
# ─────────────────────────────────────────────
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 校验错误：保留 422 + 原始错误结构（前端 extractErrorMessage 需要 detail 数组）"""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """捕获所有未处理异常：完整堆栈写入日志，响应体只返回通用消息，避免泄露代码细节"""
    logger.exception("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )


# CORS: disable credentials when origins is wildcard (browser spec requirement)
_cors_origins = settings.cors_origins_list
_allow_credentials = _cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ─────────────────────────────────────────────
#  Security Headers Middleware (P1-2.4 / P1-2.5)
# ─────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """添加安全响应头并隐藏服务器信息。"""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # P1-2.4: 安全响应头
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self';"
        )
        # P1-2.5: 隐藏服务器信息，覆盖 uvicorn 默认的 Server header
        response.headers["Server"] = "FallTracker"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# API routers
app.include_router(auth.router, prefix="/api")
app.include_router(deliveries.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(resumes.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(radar.router, prefix="/api")
app.include_router(statistics.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(backup.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(bookmarks.router, prefix="/api")
app.include_router(agent_router.router, prefix="/api")

@app.get("/health")
def health(request: Request):
    # P2-2.8: 限制健康检查仅允许内网/localhost 访问，防止外部探测服务状态
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"status": "ok"}


# --- Serve frontend static files ---
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist")

assets_dir = os.path.join(FRONTEND_DIST, "assets")
if os.path.isdir(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# Mount MCP server for Hermes Agent (stateless HTTP transport).
# Starlette's app.mount() only matches /mcp/... (with trailing slash) when
# other routes like the SPA catch-all exist. To support /mcp (without slash),
# we use an ASGI middleware that intercepts /mcp* paths and delegates to the
# MCP sub-application directly, before Starlette's routing takes over.
mcp_app = mcp.streamable_http_app()

from starlette.types import Scope, Receive, Send

class MCPMiddleware:
    """ASGI middleware: routes /mcp and /mcp/* to the MCP sub-application.

    P0-2: 强制要求 MCP 端点认证。支持两种方式：
    1. 固定 API KEY（MCP_API_KEY 环境变量）
    2. JWT Bearer token（与 Web API 共用）
    """
    def __init__(self, app, mcp_app):
        self.app = app
        self.mcp_app = mcp_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/mcp"):
            # P0-2: 验证 MCP 请求的认证头
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
            if not auth_header.lower().startswith("bearer "):
                from starlette.responses import JSONResponse
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "MCP 端点需要认证，请在 Authorization 头中提供 Bearer token"},
                )
                await response(scope, receive, send)
                return

            token = auth_header[7:].strip()
            # 优先检查固定 API KEY
            if settings.MCP_API_KEY and token == settings.MCP_API_KEY:
                pass  # 固定 API KEY 有效
            else:
                # 否则走 JWT 认证
                try:
                    from jose import JWTError, jwt
                    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                    if not payload.get("sub"):
                        raise JWTError("missing sub")
                except (JWTError, Exception):
                    from starlette.responses import JSONResponse
                    response = JSONResponse(
                        status_code=401,
                        content={"detail": "无效的认证凭据"},
                    )
                    await response(scope, receive, send)
                    return

            scope = dict(scope)
            path = scope["path"]
            scope["path"] = path[4:] if len(path) > 4 else "/"
            await self.mcp_app(scope, receive, send)
        else:
            await self.app(scope, receive, send)

app.add_middleware(MCPMiddleware, mcp_app=mcp_app)

if os.path.isdir(FRONTEND_DIST):
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve the SPA - return index.html for all non-API, non-static routes."""
        if full_path:
            # Security: prevent path traversal by resolving and checking the real path
            resolved = os.path.realpath(os.path.join(FRONTEND_DIST, full_path))
            dist_real = os.path.realpath(FRONTEND_DIST)
            if resolved.startswith(dist_real + os.sep) and os.path.isfile(resolved):
                return FileResponse(resolved)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
