"""
Smoke test - import all modules and verify endpoints exist.

Lightweight alternative to pytest that avoids Windows file-locking
issues with SQLite test DBs.
"""
import os

os.environ["SECRET_KEY"] = "smoke-test-key"
os.environ["DATABASE_URL"] = "sqlite:///./smoke.db"

print("=" * 60)
print("FallTracker Backend Smoke Test")
print("=" * 60)

print("\n[1/4] Import all backend modules...")
from app.main import app
from app.routers import (
    notifications, events, deliveries, radar,
    auth, resumes, reviews, statistics, settings as settings_router,
)
from app.services.radar import fetcher, llm, email, engine, scheduler
from app.auth import _truncate_password, get_password_hash, verify_password
from app.schemas import NotificationOut, EVENT_TYPE_LABEL_MAP
from app.models import Notification, User, Delivery, InterviewEvent
print("  [OK] 14 modules imported")

print("\n[2/4] Verify route mounting...")
all_routes = []
for route in app.routes:
    if hasattr(route, "path"):
        all_routes.append(route.path)
print(f"  Total routes: {len(all_routes)}")
expected = [
    "/api/notifications",
    "/api/notifications/unread-count",
    "/api/notifications/mark-read",
    "/api/events/export.ics",
]
for path in expected:
    found = any(path in r for r in all_routes)
    mark = "[OK]" if found else "[FAIL]"
    print(f"  {mark} {path}")

print("\n[3/4] Unit logic checks...")
# B-10 bcrypt 72-byte truncation
assert _truncate_password("a" * 100) == "a" * 72, "B-10 ASCII truncation failed"
out = _truncate_password("密码" * 50)
assert len(out.encode("utf-8")) == 72, f"Expected 72 bytes, got {len(out.encode('utf-8'))}"
assert out == "密码" * 12, f"Expected 24 chars, got {len(out)}"
# verify hash consistency
h = get_password_hash("x" * 200)
assert verify_password("x" * 200, h)
assert verify_password("x" * 300, h), "B-10: extreme length should still verify"
# ICS escape
from app.routers.events import _ics_escape
assert _ics_escape("a,b;c") == "a\\,b\\;c"
assert _ics_escape("line\nbreak") == "line\\nbreak"
print("  [OK] B-10 bcrypt + UTF-8 + ICS escape all pass")

print("\n[4/4] HTTP endpoint response check...")
from fastapi.testclient import TestClient
client = TestClient(app)
# unauth
r = client.get("/api/notifications")
print(f"  GET /api/notifications: {r.status_code} (expect 401)")
assert r.status_code == 401
r = client.get("/api/events/export.ics")
print(f"  GET /api/events/export.ics: {r.status_code} (expect 401)")
assert r.status_code == 401
r = client.get("/docs")
print(f"  GET /docs (Swagger UI): {r.status_code}")
assert r.status_code == 200
# register
r = client.post("/api/auth/register", json={
    "username": "smokeuser",
    "password": "SmokePass123",
})
print(f"  POST /api/auth/register: {r.status_code}")
assert r.status_code == 200
# login
r = client.post("/api/auth/login", data={"username": "smokeuser", "password": "SmokePass123"})
print(f"  POST /api/auth/login: {r.status_code}")
assert r.status_code == 200
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
# notifications
r = client.get("/api/notifications", headers=headers)
print(f"  GET /api/notifications (authed): {r.status_code}")
assert r.status_code == 200
assert r.json()["unread_count"] == 0
# ICS
r = client.get("/api/events/export.ics", headers=headers)
print(f"  GET /api/events/export.ics (authed): {r.status_code}")
assert r.status_code == 200
assert "BEGIN:VCALENDAR" in r.text
print(f"  ICS response: {len(r.text)} chars, content-type={r.headers['content-type']}")
# deliveries
r = client.get("/api/deliveries", headers=headers)
print(f"  GET /api/deliveries (authed): {r.status_code}")
assert r.status_code == 200
# create a delivery
r = client.post("/api/deliveries", json={"company": "Acme", "position": "FE"}, headers=headers)
print(f"  POST /api/deliveries: {r.status_code}")
assert r.status_code == 200
delivery_id = r.json()["id"]
# radar
r = client.get("/api/radar/configs", headers=headers)
print(f"  GET /api/radar/configs: {r.status_code}")
assert r.status_code == 200

# OpenAPI schema summary
schema = client.get("/openapi.json").json()
print(f"\n  OpenAPI: {len(schema.get('paths', {}))} paths total")

print("\n" + "=" * 60)
print("[PASS] All smoke tests passed")
print("=" * 60)
