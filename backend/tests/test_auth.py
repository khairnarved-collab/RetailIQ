"""Authentication, password security and role-based access control."""
import pytest

from app.core.security import create_access_token, hash_password, verify_password


def test_password_is_hashed_not_plain(db):
    from sqlalchemy import select

    from app.models import User
    u = db.scalar(select(User).where(User.email == "admin@retailiq.dev"))
    assert u.hashed_password != "Admin@12345"
    assert u.hashed_password.startswith("$2")  # bcrypt
    assert verify_password("Admin@12345", u.hashed_password)
    assert not verify_password("wrong", u.hashed_password)


def test_hash_uses_random_salt():
    assert hash_password("Secret123") != hash_password("Secret123")


def test_register_login_and_me(client):
    r = client.post("/api/auth/register", json={"email": "New.User@Example.com", "full_name": "New User",
                                                "password": "Passw0rd!"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["role"] == "analyst"           # self-registration never grants admin
    assert body["user"]["email"] == "new.user@example.com"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["full_name"] == "New User"


def test_register_duplicate_email(client):
    r = client.post("/api/auth/register", json={"email": "admin@retailiq.dev", "full_name": "X Y", "password": "Passw0rd!"})
    assert r.status_code == 409


@pytest.mark.parametrize("pw", ["short1", "allletters", "12345678"])
def test_register_weak_password(client, pw):
    r = client.post("/api/auth/register", json={"email": f"weak{len(pw)}{pw[:2]}@x.com", "full_name": "Weak", "password": pw})
    assert r.status_code == 422


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "admin@retailiq.dev", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password"


def test_protected_routes_require_token(client):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_expired_token_rejected(client):
    token = create_access_token(1, "admin", expires_minutes=-1)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_analyst_cannot_manage_users(client, analyst_headers, admin_headers):
    assert client.get("/api/admin/users", headers=analyst_headers).status_code == 403
    assert client.get("/api/admin/users", headers=admin_headers).status_code == 200
    assert client.put("/api/admin/settings/inventory", json={"values": {"overstock_days_of_cover": 50}},
                      headers=analyst_headers).status_code == 403


def test_admin_can_create_and_update_user(client, admin_headers):
    r = client.post("/api/admin/users", headers=admin_headers,
                    json={"email": "second.admin@x.com", "full_name": "Second Admin", "password": "Adm1nPass!", "role": "admin"})
    assert r.status_code == 201
    uid = r.json()["id"]
    r = client.patch(f"/api/admin/users/{uid}", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    # deactivated users cannot log in
    assert client.post("/api/auth/login", json={"email": "second.admin@x.com", "password": "Adm1nPass!"}).status_code == 403


def test_profile_update_and_change_password(client):
    r = client.post("/api/auth/register", json={"email": "pw@x.com", "full_name": "Pw User", "password": "FirstPass1"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.patch("/api/auth/me", headers=h, json={"full_name": "Renamed User", "job_title": "Data Analyst"})
    assert r.json()["full_name"] == "Renamed User" and r.json()["job_title"] == "Data Analyst"
    assert client.post("/api/auth/change-password", headers=h,
                       json={"current_password": "wrong", "new_password": "SecondPass2"}).status_code == 400
    assert client.post("/api/auth/change-password", headers=h,
                       json={"current_password": "FirstPass1", "new_password": "SecondPass2"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "pw@x.com", "password": "SecondPass2"}).status_code == 200


def test_forgot_and_reset_password(client):
    client.post("/api/auth/register", json={"email": "reset@x.com", "full_name": "Reset Me", "password": "OldPass123"})
    r = client.post("/api/auth/forgot-password", json={"email": "reset@x.com"})
    token = r.json()["dev_reset_token"]
    # unknown emails get the same generic answer (no account enumeration)
    r2 = client.post("/api/auth/forgot-password", json={"email": "nobody@x.com"})
    assert r2.json()["message"] == r.json()["message"] and "dev_reset_token" not in r2.json()
    assert client.post("/api/auth/reset-password", json={"token": "x" * 20, "new_password": "NewPass123"}).status_code == 400
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "NewPass123"}).status_code == 200
    # token is single-use
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "NewPass456"}).status_code == 400
    assert client.post("/api/auth/login", json={"email": "reset@x.com", "password": "NewPass123"}).status_code == 200


def test_rate_limiter_blocks_after_limit():
    from fastapi import HTTPException
    from starlette.requests import Request

    from app.core.rate_limit import RateLimiter
    lim = RateLimiter(3, 60, scope="t")
    req = Request({"type": "http", "client": ("1.2.3.4", 1), "headers": []})
    for _ in range(3):
        lim(req)
    with pytest.raises(HTTPException) as e:
        lim(req)
    assert e.value.status_code == 429


def test_demo_accounts_protected_when_enabled(client, admin_headers, analyst_headers, db):
    from sqlalchemy import select

    from app.core.config import settings
    from app.models import User
    settings.PROTECT_DEMO_ACCOUNTS = True
    try:
        analyst = db.scalar(select(User).where(User.email == "analyst@retailiq.dev"))
        assert client.patch(f"/api/admin/users/{analyst.id}", headers=admin_headers, json={"is_active": False}).status_code == 403
        assert client.delete(f"/api/admin/users/{analyst.id}", headers=admin_headers).status_code == 403
        assert client.post("/api/auth/change-password", headers=analyst_headers,
                           json={"current_password": "Analyst@12345", "new_password": "Hacked123"}).status_code == 403
        assert "dev_reset_token" not in client.post("/api/auth/forgot-password", json={"email": "analyst@retailiq.dev"}).json()
    finally:
        settings.PROTECT_DEMO_ACCOUNTS = False
