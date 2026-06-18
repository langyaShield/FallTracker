"""
Integration tests for /api/auth endpoints.

覆盖：
- 注册 → 登录 → 用 token 访问受保护端点
- 重复注册 → 409
- 错误密码 → 401
"""
def test_register_login_flow(client):
    """User can register, log in, and access a protected endpoint."""
    payload = {
        "username": "alice",
        "password": "AlicePass123",
    }
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 200

    r2 = client.post(
        "/api/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert "access_token" in data
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # /api/auth/me is protected
    r3 = client.get("/api/auth/me", headers=headers)
    assert r3.status_code == 200
    assert r3.json()["username"] == "alice"


def test_register_duplicate_username(client):
    """Registering the same username twice should fail with 4xx."""
    payload = {
        "username": "bob",
        "password": "BobPass123",
    }
    r1 = client.post("/api/auth/register", json=payload)
    assert r1.status_code == 200

    # Try with same username again
    r2 = client.post("/api/auth/register", json=payload)
    assert r2.status_code in (400, 409, 422)


def test_login_wrong_password(client):
    """Login with wrong password returns 401."""
    payload = {
        "username": "carol",
        "password": "CarolPass123",
    }
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 200

    r2 = client.post(
        "/api/auth/login",
        data={"username": payload["username"], "password": "wrong"},
    )
    assert r2.status_code == 401


def test_protected_endpoint_without_token(client):
    """Accessing a protected endpoint without a token should return 401."""
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_protected_endpoint_invalid_token(client):
    """An invalid token should return 401."""
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
