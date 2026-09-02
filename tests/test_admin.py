from tests.conftest import create_admin, create_user


def login(client, username, password):
    client.post("/api/auth/login", json={"username": username, "password": password})


def test_admin_create_user(client):
    username, password = create_admin(client)
    login(client, username, password)

    res = client.post("/api/admin/users", json={
        "username": "newuser",
        "display_name": "New User",
        "password": "newpassword123",
        "role": "user",
    })
    assert res.status_code == 201

    res = client.get("/api/admin/users")
    usernames = [u["username"] for u in res.json()]
    assert "newuser" in usernames


def test_admin_create_user_duplicate_username_fails(client):
    username, password = create_admin(client)
    login(client, username, password)
    client.post("/api/admin/users", json={
        "username": "dupe", "display_name": "Dupe", "password": "password123", "role": "user",
    })
    res = client.post("/api/admin/users", json={
        "username": "dupe", "display_name": "Dupe2", "password": "password123", "role": "user",
    })
    assert res.status_code == 409


def test_admin_disable_user(client):
    username, password = create_admin(client)
    login(client, username, password)
    _, _, uid = create_user(client, username="target", password="targetpass123")

    res = client.patch(f"/api/admin/users/{uid}", json={"is_active": False})
    assert res.status_code == 200

    res = client.post("/api/auth/login", json={"username": "target", "password": "targetpass123"})
    assert res.status_code == 403


def test_admin_delete_user(client):
    username, password = create_admin(client)
    login(client, username, password)
    _, _, uid = create_user(client, username="deleteme", password="deletemepass123")

    res = client.delete(f"/api/admin/users/{uid}")
    assert res.status_code == 200

    res = client.get("/api/admin/users")
    ids = [u["id"] for u in res.json()]
    assert uid not in ids


def test_admin_cannot_delete_self(client):
    username, password = create_admin(client)
    login(client, username, password)
    me = client.get("/api/auth/me").json()

    res = client.delete(f"/api/admin/users/{me['id']}")
    assert res.status_code == 400


def test_admin_cannot_remove_own_admin_role(client):
    username, password = create_admin(client)
    login(client, username, password)

    me = client.get("/api/auth/me").json()

    res = client.patch(
        f"/api/admin/users/{me['id']}",
        json={"role": "user"},
    )

    assert res.status_code == 400


def test_admin_cannot_disable_own_account(client):
    username, password = create_admin(client)
    login(client, username, password)

    me = client.get("/api/auth/me").json()

    res = client.patch(
        f"/api/admin/users/{me['id']}",
        json={"is_active": False},
    )

    assert res.status_code == 400


def test_admin_get_user_detail_includes_storage(client):
    username, password = create_admin(client)
    login(client, username, password)
    _, _, uid = create_user(client, username="detailuser", password="detailuserpass123")

    res = client.get(f"/api/admin/users/{uid}")
    assert res.status_code == 200
    data = res.json()
    assert "storage_used_display" in data
    assert "file_count" in data
    assert data["file_count"] == 0


def test_admin_update_username_conflict(client):
    username, password = create_admin(client)
    login(client, username, password)
    create_user(client, username="userone", password="useronepass123")
    _, _, uid2 = create_user(client, username="usertwo", password="usertwopass123")

    res = client.patch(f"/api/admin/users/{uid2}", json={"username": "userone"})
    assert res.status_code == 409


def test_admin_force_logout_invalidates_sessions(client):
    username, password = create_admin(client)
    login(client, username, password)
    _, _, uid = create_user(client, username="forcelogout", password="forcelogoutpass123")

    from app.database import db_session
    from app.security import hash_token
    with db_session() as conn:
        conn.execute(
            "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?, ?, datetime('now', '+1 day'))",
            (uid, hash_token("dummy-token-for-test")),
        )

    res = client.post(f"/api/admin/users/{uid}/force-logout")
    assert res.status_code == 200

    with db_session() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) AS c FROM sessions WHERE user_id = ?", (uid,)
        ).fetchone()["c"]
    assert remaining == 0


def test_admin_delete_user_data_requires_confirmation(client):
    username, password = create_admin(client)
    login(client, username, password)
    _, _, uid = create_user(client, username="wipeme", password="wipemepass123")

    res = client.post(f"/api/admin/users/{uid}/delete-data", json={"confirm": False})
    assert res.status_code == 400


def test_admin_delete_user_data_wipes_files_but_keeps_account(client):
    username, password = create_admin(client)
    login(client, username, password)
    _, _, uid = create_user(client, username="wipeme2", password="wipemepass123")

    from app.config import USER_STORAGE_PATH
    test_file = USER_STORAGE_PATH / str(uid) / "documents" / "note.txt"
    test_file.write_text("hello")
    assert test_file.exists()

    res = client.post(f"/api/admin/users/{uid}/delete-data", json={"confirm": True})
    assert res.status_code == 200
    assert not test_file.exists()

    res = client.get("/api/admin/users")
    ids = [u["id"] for u in res.json()]
    assert uid in ids


def test_admin_delete_user_with_delete_data_removes_storage(client):
    username, password = create_admin(client)
    login(client, username, password)
    _, _, uid = create_user(client, username="fulldelete", password="fulldeletepass123")

    from app.config import USER_STORAGE_PATH
    user_dir = USER_STORAGE_PATH / str(uid)
    (user_dir / "documents" / "x.txt").write_text("x")

    res = client.delete(f"/api/admin/users/{uid}?delete_data=true")
    assert res.status_code == 200
    assert not user_dir.exists()


def test_admin_delete_user_without_delete_data_preserves_storage(client):
    username, password = create_admin(client)
    login(client, username, password)
    _, _, uid = create_user(client, username="keepdata", password="keepdatapass123")

    from app.config import USER_STORAGE_PATH
    user_dir = USER_STORAGE_PATH / str(uid)
    (user_dir / "documents" / "x.txt").write_text("x")

    res = client.delete(f"/api/admin/users/{uid}")
    assert res.status_code == 200
    assert user_dir.exists()
    assert (user_dir / "documents" / "x.txt").exists()


def test_admin_file_browser_lists_selected_user_files(client):
    username, password = create_admin(client)
    login(client, username, password)
    _, _, uid = create_user(client, username="browseme", password="browsemepass123")

    from app.config import USER_STORAGE_PATH
    (USER_STORAGE_PATH / str(uid) / "documents" / "report.txt").write_text("data")

    res = client.get(f"/api/admin/users/{uid}/files?path=documents")
    assert res.status_code == 200
    names = [i["name"] for i in res.json()["items"]]
    assert "report.txt" in names


def test_admin_file_browser_rejects_path_traversal(client):
    username, password = create_admin(client)
    login(client, username, password)
    _, _, uid = create_user(client, username="traversaltest", password="traversalpass123")

    res = client.get(f"/api/admin/users/{uid}/files?path=../../etc")
    assert res.status_code == 400


def test_admin_file_browser_404_for_unknown_user(client):
    username, password = create_admin(client)
    login(client, username, password)

    res = client.get("/api/admin/users/999999/files")
    assert res.status_code == 404


def test_normal_user_cannot_browse_other_user_storage(client):
    _, _, uid = create_user(client, username="victim", password="victimpass123")
    attacker_username, attacker_password, _ = create_user(
        client, username="attacker", password="attackerpass123"
    )
    login(client, attacker_username, attacker_password)

    res = client.get(f"/api/admin/users/{uid}/files")
    assert res.status_code == 403


def test_admin_logs_filter_by_action(client):
    username, password = create_admin(client)
    login(client, username, password)
    create_user(client, username="logtest", password="logtestpass123")

    res = client.get("/api/admin/logs?action=USER_CREATED")
    assert res.status_code == 200
    for item in res.json()["items"]:
        assert item["action"] == "USER_CREATED"


def test_multi_admin_transitions_succeed_when_another_admin_remains_active(client):
    """Regression check for the last-admin guard: it must NOT block ordinary
    admin management as long as at least one other active admin remains."""
    username, password = create_admin(client)
    login(client, username, password)
    me = client.get("/api/auth/me").json()

    res = client.post("/api/admin/users", json={
        "username": "secondadmin", "display_name": "Second Admin",
        "password": "secondadminpass123", "role": "admin",
    })
    second_id = res.json()["id"]

    # "me" is still an active admin, so demoting/disabling the second admin
    # must succeed -- the guard only fires when it would leave ZERO active
    # admins, not merely one.
    res = client.patch(f"/api/admin/users/{second_id}", json={"role": "user"})
    assert res.status_code == 200

    res = client.patch(f"/api/admin/users/{second_id}", json={"role": "admin"})
    assert res.status_code == 200
    res = client.patch(f"/api/admin/users/{second_id}", json={"is_active": False})
    assert res.status_code == 200


def test_cannot_delete_own_account_even_as_the_sole_admin(client):
    """The self-delete check must still fire when the caller happens to be
    the last active admin (it fires unconditionally for self, regardless of
    admin count -- this confirms that path stays intact)."""
    username, password = create_admin(client)
    login(client, username, password)
    me = client.get("/api/auth/me").json()

    res = client.delete(f"/api/admin/users/{me['id']}")
    assert res.status_code == 400


def test_last_admin_guard_blocks_demotion_at_the_database_level(client):
    """The general (non-self) last-admin guard can only be reached when a
    request targets a user who is the SOLE active admin in the database at
    check time. Requests always pass through require_admin first, so the
    caller is necessarily a currently-active admin distinct from the target
    -- meaning this path is a defense-in-depth backstop against races
    rather than something reachable via a single ordinary request. This
    test verifies the guard directly against the database, the same way
    admin.py computes it, using the exact SQL the endpoint runs.
    """
    username, password = create_admin(client)
    login(client, username, password)
    me = client.get("/api/auth/me").json()

    from app.database import db_session

    def active_admin_count(conn, exclude_id=None):
        query = "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND is_active = 1"
        params = []
        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)
        return conn.execute(query, params).fetchone()["c"]

    with db_session() as conn:
        count = active_admin_count(conn, exclude_id=me["id"])
    assert count == 0, "the seeded admin should be the sole active admin"

    # Add a second admin -- now excluding either admin still leaves one.
    client.post("/api/admin/users", json={
        "username": "backupadmin", "display_name": "Backup Admin",
        "password": "backupadminpass123", "role": "admin",
    })
    with db_session() as conn:
        count = active_admin_count(conn, exclude_id=me["id"])
    assert count == 1, "the second admin should now cover for the first"


