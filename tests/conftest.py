"""
Shared pytest fixtures. Each test run gets a fully isolated tmp environment
(separate SQLite DB and storage directories) so tests never touch real data.
"""
import os
import shutil
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    tmp_dir = tempfile.mkdtemp(prefix="hs_test_")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DATABASE_PATH", os.path.join(tmp_dir, "server.db"))
    monkeypatch.setenv("USER_STORAGE_PATH", os.path.join(tmp_dir, "users"))
    monkeypatch.setenv("SHARED_STORAGE_PATH", os.path.join(tmp_dir, "shared"))
    monkeypatch.setenv("MEDIA_STORAGE_PATH", os.path.join(tmp_dir, "media"))
    monkeypatch.setenv("THUMBNAIL_PATH", os.path.join(tmp_dir, "thumbnails"))

    # Every app.* module (config, database, and every router) binds storage
    # paths as module-level constants at import time for simplicity/speed in
    # production (paths never change while the process is running). That
    # means Python's module cache must be fully cleared between tests, or
    # later tests would silently reuse a previous test's now-deleted tmp
    # directories. Production is unaffected since it only imports once.
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]

    from app.main import app as fastapi_app
    with TestClient(fastapi_app) as test_client:
        yield test_client

    shutil.rmtree(tmp_dir, ignore_errors=True)


def create_admin(client, username="admin", password="adminpass123"):
    from app.database import db_session
    from app.security import hash_password
    with db_session() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, 'admin')",
            (username, hash_password(password), "Admin"),
        )
    return username, password


def create_user(client, username="alice", password="alicepass123", role="user"):
    from app.database import db_session
    from app.security import hash_password
    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), username.title(), role),
        )
        user_id = cur.lastrowid
    from app.config import USER_STORAGE_PATH
    for sub in ("documents", "photos", "videos", "audio", "other"):
        (USER_STORAGE_PATH / str(user_id) / sub).mkdir(parents=True, exist_ok=True)
    return username, password, user_id
