"""Agent REST proxy and MCP smoke tests.

Run with:
    pytest backend/tests/test_agent.py -v
"""
from __future__ import annotations

import json
import os

# Use an in-memory SQLite DB and disable the scheduler for tests.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTEST_CURRENT_TEST"] = "1"

import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token, get_password_hash
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import User


@pytest.fixture(scope="module")
def client():
    """Yield a TestClient with app lifespan entered."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def token(client):
    """Create a test user and return a valid JWT."""
    db = SessionLocal()
    try:
        user = User(
            username="agent_smoke_user",
            password_hash=get_password_hash("password123"),
            is_disabled=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return create_access_token(data={"sub": str(user.id)})
    finally:
        db.close()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# REST proxy smoke tests
# ---------------------------------------------------------------------------
def test_agent_deliveries_unauthorized(client):
    r = client.get("/api/agent/deliveries")
    assert r.status_code == 401


def test_agent_deliveries_empty(client, token):
    r = client.get("/api/agent/deliveries", headers=_auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_agent_create_and_list_delivery(client, token):
    payload = {
        "company": "Tencent",
        "position": "Backend Engineer",
        "status": "pending",
        "tags": ["agent-test"],
    }
    r = client.post("/api/agent/deliveries", json=payload, headers=_auth(token))
    assert r.status_code == 201
    created = r.json()
    assert created["id"] > 0
    assert created["company"] == "Tencent"

    r = client.get("/api/agent/deliveries", headers=_auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["company"] == "Tencent"


def test_agent_statistics(client, token):
    r = client.get("/api/agent/statistics", headers=_auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert "counts" in data


def test_agent_profile(client, token):
    r = client.get("/api/agent/profile", headers=_auth(token))
    assert r.status_code == 200
    data = r.json()
    for cat in ("basic", "education", "work"):
        assert cat in data
        assert isinstance(data[cat], list)


# ---------------------------------------------------------------------------
# MCP endpoint smoke tests
# ---------------------------------------------------------------------------
def test_mcp_tools_list(client, token):
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
        headers={**_auth(token), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("id") == 1
    tools = data.get("result", {}).get("tools", [])
    tool_names = {t["name"] for t in tools}
    assert "list_deliveries" in tool_names
    assert "get_profile" in tool_names


def test_mcp_call_list_deliveries(client, token):
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "list_deliveries", "arguments": {"limit": 10}},
            "id": 2,
        },
        headers={**_auth(token), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("id") == 2
    result = data.get("result", {})
    # FastMCP wraps the tool return value as JSON text in the content list.
    assert "content" in result
    parsed = json.loads(result["content"][0]["text"])
    assert "items" in parsed
    assert parsed["total"] >= 1


def test_mcp_unauthorized(client):
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 3},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401
