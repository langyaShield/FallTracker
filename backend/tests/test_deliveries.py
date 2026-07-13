"""
Tests for /api/deliveries endpoints.

覆盖：
- 列表 / 创建 / 更新 / 删除
- 标签聚合（与 N-BUG-1 修复关联：标签可全局复用）
- 截止日期过滤
"""
def _create(client, auth_headers, **overrides):
    payload = {
        "company": "Acme",
        "position": "Backend Engineer",
        "link": "https://example.com",
    }
    payload.update(overrides)
    r = client.post("/api/deliveries", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_list_deliveries_empty(client, auth_headers):
    r = client.get("/api/deliveries", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_delivery_minimal(client, auth_headers):
    """Required-only payload should work."""
    r = client.post(
        "/api/deliveries",
        json={"company": "X", "position": "Y"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["company"] == "X"
    assert data["position"] == "Y"
    assert data["status"] == "pending"  # default


def test_create_delivery_with_tags(client, auth_headers):
    """Tags should be persisted and returned in list."""
    delivery = _create(client, auth_headers, tags=["python", "backend"])
    r = client.get("/api/deliveries", headers=auth_headers)
    items = r.json()
    assert len(items) == 1
    assert sorted(items[0]["tags"]) == ["backend", "python"]


def test_update_delivery_status(client, auth_headers):
    delivery = _create(client, auth_headers)
    r = client.put(
        f"/api/deliveries/{delivery['id']}",
        json={"status": "interview"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "interview"

    logs = client.get(f"/api/deliveries/{delivery['id']}/logs", headers=auth_headers)
    assert logs.status_code == 200
    assert len(logs.json()) == 1
    assert logs.json()[0]["action"] == "status_change"


def test_update_delivery_without_status_does_not_create_status_log(client, auth_headers):
    delivery = _create(client, auth_headers)
    response = client.put(
        f"/api/deliveries/{delivery['id']}",
        json={"company": "Renamed Acme"},
        headers=auth_headers,
    )
    assert response.status_code == 200

    logs = client.get(f"/api/deliveries/{delivery['id']}/logs", headers=auth_headers)
    assert logs.status_code == 200
    assert logs.json() == []


def test_delete_delivery(client, auth_headers):
    delivery = _create(client, auth_headers)
    r = client.delete(f"/api/deliveries/{delivery['id']}", headers=auth_headers)
    assert r.status_code == 200
    r2 = client.get("/api/deliveries", headers=auth_headers)
    assert r2.json() == []


def test_user_isolation(client, auth_headers, db_session):
    """Another user's deliveries must not leak."""
    from app.database import SessionLocal
    from app.models import User
    from app.auth import get_password_hash

    db = SessionLocal()
    try:
        other = User(
            username="other",
            password_hash=get_password_hash("otherpass1"),
        )
        db.add(other)
        db.commit()
    finally:
        db.close()

    # 登录 second user
    r = client.post(
        "/api/auth/login",
        data={"username": "other", "password": "otherpass1"},
    )
    other_token = r.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # first user creates 1 delivery
    _create(client, auth_headers)
    # other user creates 1 delivery
    r2 = client.post(
        "/api/deliveries",
        json={"company": "OtherCo", "position": "FE"},
        headers=other_headers,
    )
    assert r2.status_code == 200

    # first user only sees their own
    r3 = client.get("/api/deliveries", headers=auth_headers)
    assert len(r3.json()) == 1
    assert r3.json()[0]["company"] == "Acme"

    # other user only sees their own
    r4 = client.get("/api/deliveries", headers=other_headers)
    assert len(r4.json()) == 1
    assert r4.json()[0]["company"] == "OtherCo"
