"""
Tests for the /api/notifications endpoints (T1-2).

覆盖：
- 未登录用户访问 → 401
- 空列表 + unread_count=0
- 标记已读（id 列表 / 全部）
- 单条删除
- 跨用户隔离（用户 A 不能看到用户 B 的通知）
"""
def _create_notification_directly(db, user_id: int, **kwargs):
    """Bypass HTTP to create a notification row in the test DB."""
    from app.models import Notification
    n = Notification(user_id=user_id, **kwargs)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_list_notifications_requires_auth(client):
    r = client.get("/api/notifications")
    assert r.status_code == 401


def test_list_notifications_empty(client, auth_headers):
    r = client.get("/api/notifications", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["unread_count"] == 0
    assert data["total"] == 0
    assert data["items"] == []


def test_list_notifications_returns_user_data(client, auth_headers, db_session):
    user_id = client.get("/api/auth/me", headers=auth_headers).json()["id"]
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        for i in range(3):
            _create_notification_directly(
                db, user_id,
                type="radar_hit",
                title=f"通知 {i}",
                body=f"body {i}",
            )
    finally:
        db.close()

    r = client.get("/api/notifications", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["unread_count"] == 3
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_unread_count_endpoint(client, auth_headers, db_session):
    user_id = client.get("/api/auth/me", headers=auth_headers).json()["id"]
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        _create_notification_directly(db, user_id, type="radar_hit", title="t1")
        _create_notification_directly(db, user_id, type="radar_hit", title="t2", is_read=True)
    finally:
        db.close()

    r = client.get("/api/notifications/unread-count", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["unread_count"] == 1


def test_mark_all_read(client, auth_headers, db_session):
    user_id = client.get("/api/auth/me", headers=auth_headers).json()["id"]
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        for i in range(3):
            _create_notification_directly(db, user_id, type="radar_hit", title=f"t{i}")
    finally:
        db.close()

    r = client.post("/api/notifications/mark-read", json={}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["updated"] == 3

    r2 = client.get("/api/notifications/unread-count", headers=auth_headers)
    assert r2.json()["unread_count"] == 0


def test_mark_specific_ids(client, auth_headers, db_session):
    user_id = client.get("/api/auth/me", headers=auth_headers).json()["id"]
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        ids = []
        for i in range(2):
            n = _create_notification_directly(db, user_id, type="radar_hit", title=f"t{i}")
            ids.append(n.id)
    finally:
        db.close()

    r = client.post("/api/notifications/mark-read", json={"ids": ids}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["updated"] == 2

    r2 = client.get("/api/notifications/unread-count", headers=auth_headers)
    assert r2.json()["unread_count"] == 0


def test_delete_notification(client, auth_headers, db_session):
    user_id = client.get("/api/auth/me", headers=auth_headers).json()["id"]
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        n = _create_notification_directly(db, user_id, type="radar_hit", title="to-delete")
    finally:
        db.close()

    r = client.delete(f"/api/notifications/{n.id}", headers=auth_headers)
    assert r.status_code == 200

    r2 = client.get("/api/notifications", headers=auth_headers)
    assert r2.json()["total"] == 0


def test_user_isolation(client, auth_headers, db_session):
    """Notifications from another user should not be visible."""
    user_id = client.get("/api/auth/me", headers=auth_headers).json()["id"]
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        _create_notification_directly(db, user_id + 999, type="radar_hit", title="other-user")
        _create_notification_directly(db, user_id, type="radar_hit", title="my-notif")
    finally:
        db.close()

    r = client.get("/api/notifications", headers=auth_headers)
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "my-notif"
