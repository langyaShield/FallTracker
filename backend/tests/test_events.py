"""
Tests for /api/events endpoints, especially the iCal export (T1-3).

覆盖：
- 列出事件
- 未来事件筛选
- ICS 导出格式正确（RFC 5545）
- 空用户导出返回 valid ics (BEGIN/END/VEVENT/CALENDAR 块齐全)
"""
def _create_delivery(client, auth_headers, **overrides):
    payload = {
        "company": "Acme",
        "position": "Backend Engineer",
        "link": "https://example.com/jobs/1",
        "status": "applied",
    }
    payload.update(overrides)
    r = client.post("/api/deliveries", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_list_events_empty(client, auth_headers):
    r = client.get("/api/events", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_event(client, auth_headers):
    delivery = _create_delivery(client, auth_headers)
    payload = {
        "delivery_id": delivery["id"],
        "event_type": "interview",
        "scheduled_at": "2026-12-01T10:00:00Z",
        "location": "线上",
        "notes": "技术一面",
    }
    r = client.post("/api/events", json=payload, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["event_type"] == "interview"
    assert data["delivery_id"] == delivery["id"]


def test_upcoming_filter(client, auth_headers):
    """The upcoming=true flag should filter to future events only."""
    from datetime import datetime, timedelta, timezone
    delivery = _create_delivery(client, auth_headers)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    client.post("/api/events", json={"delivery_id": delivery["id"], "event_type": "interview", "scheduled_at": past}, headers=auth_headers)
    client.post("/api/events", json={"delivery_id": delivery["id"], "event_type": "interview", "scheduled_at": future}, headers=auth_headers)

    r = client.get("/api/events", params={"upcoming": True, "limit": 10}, headers=auth_headers)
    items = r.json()
    assert len(items) == 1
    assert items[0]["scheduled_at"].startswith(future[:10])


def test_ics_export_requires_auth(client):
    r = client.get("/api/events/export.ics")
    assert r.status_code == 401


def test_ics_export_empty(client, auth_headers):
    """A user with no events should still get a valid (empty) iCal feed."""
    r = client.get("/api/events/export.ics", headers=auth_headers)
    assert r.status_code == 200
    assert "text/calendar" in r.headers["content-type"]
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR")
    assert "END:VCALENDAR" in body


def test_ics_export_with_event(client, auth_headers):
    """An event should appear as a VEVENT block in the exported iCal."""
    from datetime import datetime, timedelta, timezone
    delivery = _create_delivery(client, auth_headers, company="Google", position="SWE")
    future = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    client.post("/api/events", json={
        "delivery_id": delivery["id"],
        "event_type": "interview",
        "scheduled_at": future.isoformat(),
        "location": "在线会议",
        "notes": "一面",
    }, headers=auth_headers)

    r = client.get("/api/events/export.ics", headers=auth_headers)
    assert r.status_code == 200
    body = r.text
    # 验证 RFC 5545 关键字段
    assert "BEGIN:VCALENDAR" in body
    assert "END:VCALENDAR" in body
    assert "BEGIN:VEVENT" in body
    assert "END:VEVENT" in body
    assert "Google - SWE" in body
    assert "DTSTART:" in body
    assert "DTEND:" in body
    assert "在线会议" in body
    # 没有则不能出现空 DTSTART
    assert body.count("DTSTART:") == 1
    assert body.count("DTEND:") == 1


def test_ics_export_escapes_special_chars(client, auth_headers):
    """iCal escapes commas, semicolons, and backslashes per RFC 5545."""
    from datetime import datetime, timedelta, timezone
    delivery = _create_delivery(client, auth_headers, company="Acme; Co", position="Eng, Jr")
    future = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
    client.post("/api/events", json={
        "delivery_id": delivery["id"],
        "event_type": "interview",
        "scheduled_at": future.isoformat(),
    }, headers=auth_headers)

    r = client.get("/api/events/export.ics", headers=auth_headers)
    body = r.text
    # 逗号/分号应被转义（使用原始字符串避免 SyntaxWarning）
    assert r"Acme\; Co" in body
    assert r"Eng\, Jr" in body
