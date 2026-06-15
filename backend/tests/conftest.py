"""
Shared test fixtures.

使用 SQLite in-memory DB + 临时 uploads 目录，避免污染开发数据。
"""
import os
import shutil
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. 在导入 app 前替换 settings 中依赖的环境变量
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_falltracker.db")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("LLM_API_BASE", "https://api.test.local/v1")

from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    """在所有测试结束后删除测试数据库。"""
    yield
    import time
    time.sleep(0.1)  # 让 SQLite 释放文件句柄
    test_db = "./test_falltracker.db"
    if os.path.exists(test_db):
        for _ in range(3):
            try:
                os.remove(test_db)
                break
            except PermissionError:
                time.sleep(0.5)


@pytest.fixture(scope="function")
def db_session():
    """Fresh DB for each test."""
    from app.database import engine
    # Drop & recreate
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with a fresh DB. Auth headers injected via fixtures."""
    # Override get_db to use the same engine
    from app.database import SessionLocal
    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user(client):
    """Register a test user, return user + auth token."""
    payload = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "password123",
    }
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 200, f"register failed: {r.text}"
    user_id = r.json()["id"]

    # 单独走 login 拿 token
    r2 = client.post(
        "/api/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    assert r2.status_code == 200, f"login failed: {r2.text}"
    token = r2.json()["access_token"]
    user = {"id": user_id, "username": payload["username"]}
    return user, {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def auth_headers(test_user):
    """Just the auth header dict."""
    _, headers = test_user
    return headers
