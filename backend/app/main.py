import sqlite3, os, threading, time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles
from app.config import settings
from app.database import engine, Base
from app.routers import auth, deliveries, events, resumes, reviews, radar, statistics, settings as settings_router


def _add_column_if_not_exists(table_name: str, column_name: str, column_type: str):
    """Add a column to an existing SQLite table if it doesn't exist yet."""
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing = [row[1] for row in cursor.fetchall()]
    if column_name not in existing:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        conn.commit()
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

app = FastAPI(title="FallTracker API", version="1.0.0")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def start_crawler_scheduler():
    """Start a background thread that periodically checks and runs due crawlers."""
    def _scheduler_loop():
        while True:
            try:
                from app.routers.radar import check_and_run_due_crawlers
                check_and_run_due_crawlers()
            except Exception:
                pass
            time.sleep(60)  # Check every 60 seconds

    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()


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
