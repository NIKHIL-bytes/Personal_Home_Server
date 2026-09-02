from tests.conftest import create_user


def login(client, username, password):
    client.post("/api/auth/login", json={"username": username, "password": password})


def test_upload_and_list_file(client):
    username, password, _ = create_user(client)
    login(client, username, password)

    res = client.post("/api/files/upload", files={"file": ("report.pdf", b"%PDF-1.4 fake")})
    assert res.status_code == 200

    res = client.get("/api/files")
    names = [item["name"] for item in res.json()["items"]]
    assert "report.pdf" in names


def test_download_file(client):
    username, password, _ = create_user(client)
    login(client, username, password)
    client.post("/api/files/upload", files={"file": ("note.txt", b"hello world")})

    res = client.get("/api/files/download", params={"path": "note.txt"})
    assert res.status_code == 200
    assert res.content == b"hello world"


def test_rename_file(client):
    username, password, _ = create_user(client)
    login(client, username, password)
    client.post("/api/files/upload", files={"file": ("old.txt", b"data")})

    res = client.patch("/api/files/rename", params={"path": "old.txt", "new_name": "new.txt"})
    assert res.status_code == 200

    res = client.get("/api/files")
    names = [item["name"] for item in res.json()["items"]]
    assert "new.txt" in names and "old.txt" not in names


def test_delete_file(client):
    username, password, _ = create_user(client)
    login(client, username, password)
    client.post("/api/files/upload", files={"file": ("temp.txt", b"data")})

    res = client.delete("/api/files", params={"path": "temp.txt"})
    assert res.status_code == 200

    res = client.get("/api/files")
    names = [item["name"] for item in res.json()["items"]]
    assert "temp.txt" not in names


def test_path_traversal_blocked_on_list(client):
    username, password, _ = create_user(client)
    login(client, username, password)

    res = client.get("/api/files", params={"path": "../../../../etc"})
    assert res.status_code == 400


def test_path_traversal_blocked_on_download(client):
    username, password, _ = create_user(client)
    login(client, username, password)

    res = client.get("/api/files/download", params={"path": "../../../../etc/passwd"})
    assert res.status_code == 400


def test_uploaded_filename_is_sanitized(client):
    username, password, _ = create_user(client)
    login(client, username, password)

    res = client.post("/api/files/upload", files={"file": ("../../evil.txt", b"data")})
    assert res.status_code == 200
    # The sanitizer should strip directory components, so it lands as a plain file
    # inside the user's own root rather than escaping it.
    res = client.get("/api/files")
    for item in res.json()["items"]:
        assert ".." not in item["path"]


def test_upload_cannot_exceed_user_quota(client):
    username, password, user_id = create_user(client)

    from app.database import db_session

    with db_session() as conn:
        conn.execute(
            "UPDATE users SET storage_quota = 4 WHERE id = ?",
            (user_id,),
        )

    client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": password,
        },
    )

    res = client.post(
        "/api/files/upload",
        files={
            "file": (
                "too-big.txt",
                b"12345",
                "text/plain",
            )
        },
    )

    assert res.status_code == 413
