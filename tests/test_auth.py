from tests.conftest import create_admin, create_user


def test_valid_login(client):
    username, password = create_admin(client)
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    assert "hs_session" in res.cookies


def test_invalid_password(client):
    username, _ = create_admin(client)
    res = client.post("/api/auth/login", json={"username": username, "password": "wrongpass"})
    assert res.status_code == 401


def test_unknown_username_same_error_as_wrong_password(client):
    res1 = client.post("/api/auth/login", json={"username": "nobody", "password": "whatever123"})
    username, _ = create_admin(client)
    res2 = client.post("/api/auth/login", json={"username": username, "password": "wrongpass"})
    assert res1.status_code == res2.status_code == 401
    assert res1.json()["detail"] == res2.json()["detail"]


def test_logout_invalidates_session(client):
    username, password = create_admin(client)
    client.post("/api/auth/login", json={"username": username, "password": password})
    client.post("/api/auth/logout")
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_disabled_user_cannot_login(client):
    username, password, user_id = create_user(client)
    from app.database import db_session
    with db_session() as conn:
        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 403


def test_me_requires_authentication(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401
