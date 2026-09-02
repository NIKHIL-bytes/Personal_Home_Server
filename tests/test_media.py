from tests.conftest import create_user


def login(client, username, password):
    client.post("/api/auth/login", json={"username": username, "password": password})


def _write_media_file(name=b"tiny.mp4", content=b"0" * 1000):
    from app.config import MEDIA_STORAGE_PATH
    (MEDIA_STORAGE_PATH / "videos").mkdir(parents=True, exist_ok=True)
    path = MEDIA_STORAGE_PATH / "videos" / name.decode()
    path.write_bytes(content)
    return path


def test_list_media_empty(client):
    username, password, _ = create_user(client)
    login(client, username, password)
    res = client.get("/api/media", params={"category": "videos"})
    assert res.status_code == 200
    assert res.json()["items"] == []


def test_stream_full_file(client):
    username, password, _ = create_user(client)
    login(client, username, password)
    _write_media_file()

    res = client.get("/api/media", params={"category": "videos"})
    media_id = res.json()["items"][0]["id"]

    res = client.get(f"/api/media/{media_id}/stream")
    assert res.status_code == 200
    assert len(res.content) == 1000


def test_range_request_returns_partial_content(client):
    username, password, _ = create_user(client)
    login(client, username, password)
    _write_media_file(content=b"A" * 500 + b"B" * 500)

    res = client.get("/api/media", params={"category": "videos"})
    media_id = res.json()["items"][0]["id"]

    res = client.get(f"/api/media/{media_id}/stream", headers={"Range": "bytes=500-599"})
    assert res.status_code == 206
    assert res.content == b"B" * 100
    assert res.headers["Content-Range"] == "bytes 500-599/1000"


def test_invalid_media_id_returns_404(client):
    username, password, _ = create_user(client)
    login(client, username, password)
    res = client.get("/api/media/doesnotexist/stream")
    assert res.status_code == 404
