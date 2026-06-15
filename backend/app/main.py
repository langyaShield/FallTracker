import sqlite3, os, logging, warnings
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import SQLAlchemyError
from starlette.staticfiles import StaticFiles
from app.config import settings
from app.database import engine, Base
from app.routers import auth, deliveries, events, resumes, reviews, radar, statistics, settings as settings_router, notifications

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


Base.metadata.create_all(bind=engine)

# Patch new columns into existing tables (safe to run multiple times)
_add_column_if_not_exists("deliveries", "deadline", "DATETIME")
_add_column_if_not_exists("resumes", "ocr_text", "TEXT")
_add_column_if_not_exists("resumes", "ocr_status", "VARCHAR(20) DEFAULT 'pending'")
_add_column_if_not_exists("resumes", "ocr_progress", "INTEGER DEFAULT 0")
# Patch new columns into existing user_settings table
_add_column_if_not_exists("user_settings", "smtp_server", "VARCHAR(200)")
_add_column_if_not_exists("user_settings", "smtp_port", "INTEGER")
_add_column_if_not_exists("user_settings", "smtp_username", "VARCHAR(200)")
_add_column_if_not_exists("user_settings", "smtp_password", "VARCHAR(500)")
_add_column_if_not_exists("user_settings", "email_from", "VARCHAR(200)")

# Security warning for default SECRET_KEY
if settings.SECRET_KEY == "change-me-to-a-random-secret-key":
    warnings.warn(
        "SECURITY WARNING: Using default SECRET_KEY. "
        "Please set a strong random SECRET_KEY in .env for production!",
        stacklevel=1,
    )
    logger.warning("Using default SECRET_KEY — not safe for production!")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start crawler scheduler
    import threading, time

    # 在测试环境下不启动后台调度器（避免测试 DB 表不存在导致启动失败）
    if os.environ.get("PYTEST_CURRENT_TEST"):
        yield
        return

    def _scheduler_loop():
        tick_count = 0
        while True:
            try:
                from app.routers.radar import check_and_run_due_crawlers
                check_and_run_due_crawlers()
            except Exception as e:
                # 记录到日志便于排查，但不影响后续轮询
                logger.warning(f"Crawler scheduler tick failed: {e}", exc_info=True)
            # T1-2: 面试提醒 tick 频率可低于爬虫调度（每 10 分钟一次）
            tick_count += 1
            if tick_count % 10 == 0:
                try:
                    from app.services.radar.scheduler import notify_upcoming_interviews
                    notify_upcoming_interviews()
                except Exception as e:
                    logger.warning(f"Interview reminder tick failed: {e}", exc_info=True)
            time.sleep(60)

    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()
    yield
    # Shutdown: cleanup if needed


app = FastAPI(title="FallTracker API", version="1.0.0", lifespan=lifespan)


# ─────────────────────────────────────────────
#  Global Exception Handlers (B-11)
# ─────────────────────────────────────────────
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


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.get("/health")
def health():
    return {"status": "ok"}


# --- Serve frontend static files ---
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve the SPA - return index.html for all non-API, non-static routes."""
        if full_path and os.path.isfile(os.path.join(FRONTEND_DIST, full_path)):
            return FileResponse(os.path.join(FRONTEND_DIST, full_path))
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
