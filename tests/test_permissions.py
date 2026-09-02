from tests.conftest import create_admin, create_user


def login(client, username, password):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200


def test_user_cannot_access_admin_endpoints(client):
    username, password, _ = create_user(client)
    login(client, username, password)
    res = client.get("/api/admin/users")
    assert res.status_code == 403


def test_admin_can_access_admin_endpoints(client):
    username, password = create_admin(client)
    login(client, username, password)
    res = client.get("/api/admin/users")
    assert res.status_code == 200


def test_user_cannot_write_shared_files(client):
    username, password, _ = create_user(client)
    login(client, username, password)
    res = client.post("/api/shared/upload", files={"file": ("test.txt", b"hello")})
    assert res.status_code == 403


def test_user_cannot_delete_shared_files(client):
    username, password = create_admin(client)
    login(client, username, password)
    client.post("/api/shared/upload", files={"file": ("test.txt", b"hello")})

    username2, password2, _ = create_user(client, username="bob", password="bobpass123")
    login(client, username2, password2)
    res = client.delete("/api/shared", params={"path": "test.txt"})
    assert res.status_code == 403


def test_admin_can_write_shared_files(client):
    username, password = create_admin(client)
    login(client, username, password)
    res = client.post("/api/shared/upload", files={"file": ("test.txt", b"hello")})
    assert res.status_code == 200


def test_user_cannot_access_another_users_files(client):
    _, _, user1_id = create_user(client, username="alice", password="alicepass123")
    from app.config import USER_STORAGE_PATH
    (USER_STORAGE_PATH / str(user1_id) / "documents" / "secret.txt").write_text("private data")

    username2, password2, _ = create_user(client, username="bob", password="bobpass123")
    login(client, username2, password2)

    # Bob tries to read Alice's file by directly guessing her user id path.
    res = client.get("/api/files/download", params={"path": f"../{user1_id}/documents/secret.txt"})
    assert res.status_code in (400, 404)
