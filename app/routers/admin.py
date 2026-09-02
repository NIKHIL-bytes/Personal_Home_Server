"""
Administrator-only endpoints: user management, per-user storage browsing,
audit log viewing, system stats. Every route in this file requires require_admin.
"""
import shutil
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from app.audit import log_action
from app.config import DEFAULT_USER_QUOTA_BYTES, SHARED_STORAGE_PATH, USER_STORAGE_PATH
from app.database import db_session
from app.dependencies import CurrentUser, require_admin
from app.security import hash_password
from app.routers.files import user_root, _entry_meta
from app.utils import (
    PathSecurityError,
    TEXT_PREVIEW_MAX_BYTES,
    directory_size,
    guess_mime,
    human_size,
    preview_kind,
    range_streaming_response,
    safe_join,
    sanitize_filename,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_START_TIME = time.time()


def _active_admin_count(conn, exclude_id: int | None = None) -> int:
    """Count currently-active administrators, optionally excluding one user
    id (used to ask 'how many active admins would remain WITHOUT this one').
    """
    query = "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND is_active = 1"
    params: list = []
    if exclude_id is not None:
        query += " AND id != ?"
        params.append(exclude_id)
    return conn.execute(query, params).fetchone()["c"]


class CreateUserPayload(BaseModel):
    username: str
    display_name: str
    password: str
    role: str = "user"
    storage_quota: int = DEFAULT_USER_QUOTA_BYTES


class UpdateUserPayload(BaseModel):
    username: str | None = None
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    storage_quota: int | None = None


class ResetPasswordPayload(BaseModel):
    new_password: str


class ConfirmPayload(BaseModel):
    confirm: bool = False


@router.get("/users")
def list_users(admin: CurrentUser = Depends(require_admin)):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, username, display_name, role, is_active, created_at, last_login, storage_quota "
            "FROM users ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/users/{user_id}")
def get_user_detail(user_id: int, admin: CurrentUser = Depends(require_admin)):
    """Full detail for one user, including on-demand storage usage and file
    count. Deliberately NOT computed for every row in list_users() above --
    that stays a cheap query so the user table loads instantly; this walks
    that one user's directory tree only when their detail view is opened."""
    with db_session() as conn:
        row = conn.execute(
            "SELECT id, username, display_name, role, is_active, created_at, last_login, storage_quota "
            "FROM users WHERE id = ?", (user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    root = user_root(user_id)
    used = directory_size(root)
    file_count = sum(1 for p in root.rglob("*") if p.is_file() and not p.name.endswith(".part"))

    return {
        **dict(row),
        "storage_used": used,
        "storage_used_display": human_size(used),
        "storage_quota_display": human_size(row["storage_quota"]),
        "file_count": file_count,
    }


@router.post("/users", status_code=201)
def create_user(payload: CreateUserPayload, request: Request, admin: CurrentUser = Depends(require_admin)):
    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    username = payload.username.strip().lower()
    with db_session() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="Username already exists")

        cur = conn.execute(
            """INSERT INTO users (username, password_hash, display_name, role, storage_quota)
               VALUES (?, ?, ?, ?, ?)""",
            (username, hash_password(payload.password), payload.display_name, payload.role, payload.storage_quota),
        )
        new_id = cur.lastrowid
        (USER_STORAGE_PATH / str(new_id)).mkdir(parents=True, exist_ok=True)
        for sub in ("documents", "photos", "videos", "audio", "other"):
            (USER_STORAGE_PATH / str(new_id) / sub).mkdir(exist_ok=True)

        log_action(conn, "USER_CREATED", request=request, user_id=admin.id, username=admin.username,
                    target_type="user", target_id=str(new_id), details=f"created {username}")

    return {"id": new_id, "username": username}


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UpdateUserPayload, request: Request,
                 admin: CurrentUser = Depends(require_admin)):
    if user_id == admin.id:
        if payload.role == "user":
            raise HTTPException(
                status_code=400,
                detail="Cannot remove administrator role from your own account",
            )

        if payload.is_active is False:
            raise HTTPException(
                status_code=400,
                detail="Cannot disable your own account",
            )

    fields, values = [], []
    if payload.username is not None:
        new_username = payload.username.strip().lower()
        if not new_username:
            raise HTTPException(status_code=400, detail="Username cannot be empty")
        fields.append("username = ?")
        values.append(new_username)
    if payload.display_name is not None:
        fields.append("display_name = ?")
        values.append(payload.display_name)
    if payload.role is not None:
        if payload.role not in ("admin", "user"):
            raise HTTPException(status_code=400, detail="Invalid role")
        fields.append("role = ?")
        values.append(payload.role)
    if payload.is_active is not None:
        fields.append("is_active = ?")
        values.append(int(payload.is_active))
    if payload.storage_quota is not None:
        if payload.storage_quota < 0:
            raise HTTPException(
                status_code=400,
                detail="Storage quota cannot be negative",
            )

        fields.append("storage_quota = ?")
        values.append(payload.storage_quota)

    if not fields:
        raise HTTPException(status_code=400, detail="No changes provided")

    with db_session() as conn:
        existing = conn.execute(
            "SELECT id, role, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if not existing:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        # Would this change take an active admin's role/status away? If so,
        # make sure at least one OTHER active admin would still remain --
        # this protects against demoting/disabling the last admin no matter
        # who performs the action (the earlier check above only covers an
        # admin acting on their own account).
        target_is_active_admin = existing["role"] == "admin" and existing["is_active"] == 1
        would_lose_admin = payload.role == "user"
        would_be_disabled = payload.is_active is False
        if target_is_active_admin and (would_lose_admin or would_be_disabled):
            if _active_admin_count(conn, exclude_id=user_id) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot remove or disable the last active administrator",
                )

        if payload.username is not None:
            clash = conn.execute(
                "SELECT id FROM users WHERE username = ? AND id != ?",
                (values[0], user_id),  # username is always the first field appended, if present
            ).fetchone()
            if clash:
                raise HTTPException(status_code=409, detail="Username already exists")

        values.append(user_id)

        conn.execute(
            f"UPDATE users SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        action = "USER_DISABLED" if payload.is_active is False else "USER_UPDATED"
        log_action(conn, action, request=request, user_id=admin.id, username=admin.username,
                    target_type="user", target_id=str(user_id))

    return {"status": "ok"}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, payload: ResetPasswordPayload, request: Request,
                    admin: CurrentUser = Depends(require_admin)):
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    with db_session() as conn:
        existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                      (hash_password(payload.new_password), user_id))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))  # force re-login
        log_action(conn, "PASSWORD_CHANGED", request=request, user_id=admin.id, username=admin.username,
                    target_type="user", target_id=str(user_id), details="admin reset")

    return {"status": "ok"}


@router.post("/users/{user_id}/force-logout")
def force_logout(user_id: int, request: Request, admin: CurrentUser = Depends(require_admin)):
    """Invalidate a user's active sessions without touching their password --
    useful when you just want to kick a stale/compromised session."""
    with db_session() as conn:
        existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        log_action(conn, "USER_FORCE_LOGOUT", request=request, user_id=admin.id, username=admin.username,
                    target_type="user", target_id=str(user_id))
    return {"status": "ok"}


@router.post("/users/{user_id}/delete-data")
def delete_user_data(user_id: int, payload: ConfirmPayload, request: Request,
                      admin: CurrentUser = Depends(require_admin)):
    """Wipe a user's storage while keeping their account. Requires an
    explicit confirm=true body so this can never be triggered by accident."""
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required to delete user data")

    with db_session() as conn:
        row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

    root = user_root(user_id)  # deterministic path (data/users/<id>/) -- never user-controlled
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    # Recreate the standard subfolders so the user's next login/upload works normally.
    user_root(user_id)

    with db_session() as conn:
        log_action(conn, "USER_DATA_DELETED", request=request, user_id=admin.id, username=admin.username,
                    target_type="user", target_id=str(user_id), details=f"wiped storage for {row['username']}")

    return {"status": "ok"}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request, delete_data: bool = False,
                 admin: CurrentUser = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    with db_session() as conn:
        row = conn.execute("SELECT username, role, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        if row["role"] == "admin" and row["is_active"] == 1:
            if _active_admin_count(conn, exclude_id=user_id) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot delete the last active administrator",
                )

        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        details = f"deleted {row['username']}" + (" (storage wiped)" if delete_data else " (storage preserved)")
        log_action(conn, "USER_DELETED", request=request, user_id=admin.id, username=admin.username,
                    target_type="user", target_id=str(user_id), details=details)

    if delete_data:
        root = USER_STORAGE_PATH / str(user_id)  # same deterministic, non-user-controlled path
        if root.exists() and root.is_dir():
            shutil.rmtree(root)

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Admin storage browser -- browse/manage a SELECTED user's files.
# Every endpoint below takes user_id from the URL (admin's choice, never
# trusted from a generic "whose files" field) and scopes all filesystem
# access to that user's root via the same user_root() + safe_join() used by
# the personal /api/files endpoints -- no separate path-validation logic.
# ---------------------------------------------------------------------------

def _require_user_exists(user_id: int) -> None:
    with db_session() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")


@router.get("/users/{user_id}/files")
def browse_user_files(user_id: int, path: str = "", admin: CurrentUser = Depends(require_admin)):
    _require_user_exists(user_id)
    root = user_root(user_id)
    try:
        target = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    entries = sorted(
        (p for p in target.iterdir() if not p.name.startswith(".") and not p.name.endswith(".part")),
        key=lambda p: (p.is_file(), p.name.lower()),
    )
    return {"path": path, "items": [_entry_meta(p, root) for p in entries]}


@router.get("/users/{user_id}/files/view")
def view_user_file(user_id: int, path: str, request: Request, admin: CurrentUser = Depends(require_admin)):
    """Admin preview of a file inside a selected user's storage. Same
    inline/streamed rendering as the personal /api/files/view endpoint."""
    _require_user_exists(user_id)
    root = user_root(user_id)
    try:
        target = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    kind = preview_kind(target.name)
    mime = guess_mime(target.name)

    with db_session() as conn:
        log_action(conn, "FILE_VIEW", request=request, user_id=admin.id, username=admin.username,
                    target_type="user_file", target_id=f"{user_id}:{path}")

    if kind in ("image", "pdf"):
        return FileResponse(
            target, media_type=mime,
            headers={"Content-Disposition": f'inline; filename="{target.name}"'},
        )
    if kind in ("video", "audio"):
        return range_streaming_response(target, request, mime)
    if kind == "text":
        with open(target, "rb") as f:
            raw = f.read(TEXT_PREVIEW_MAX_BYTES + 1)
        truncated = len(raw) > TEXT_PREVIEW_MAX_BYTES
        text = raw[:TEXT_PREVIEW_MAX_BYTES].decode("utf-8", errors="replace")
        if truncated:
            text += "\n\n[... file truncated for preview — download to see the full contents ...]"
        return PlainTextResponse(text, media_type="text/plain; charset=utf-8")

    raise HTTPException(status_code=415, detail="Preview not available for this file type")


@router.get("/users/{user_id}/files/download")
def download_user_file(user_id: int, path: str, request: Request, admin: CurrentUser = Depends(require_admin)):
    _require_user_exists(user_id)
    root = user_root(user_id)
    try:
        target = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    with db_session() as conn:
        log_action(conn, "FILE_DOWNLOAD", request=request, user_id=admin.id, username=admin.username,
                    target_type="user_file", target_id=f"{user_id}:{path}")

    return FileResponse(target, filename=target.name)


@router.delete("/users/{user_id}/files")
def delete_user_file(user_id: int, path: str, request: Request, admin: CurrentUser = Depends(require_admin)):
    _require_user_exists(user_id)
    root = user_root(user_id)
    try:
        target = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target == root:
        raise HTTPException(status_code=400, detail="Cannot delete the user's root folder")

    is_dir = target.is_dir()
    if is_dir:
        shutil.rmtree(target)
    else:
        target.unlink()

    with db_session() as conn:
        log_action(conn, "FOLDER_DELETE" if is_dir else "FILE_DELETE", request=request,
                    user_id=admin.id, username=admin.username,
                    target_type="user_file", target_id=f"{user_id}:{path}")

    return {"status": "ok"}


@router.patch("/users/{user_id}/files/rename")
def rename_user_file(user_id: int, path: str, new_name: str, request: Request,
                      admin: CurrentUser = Depends(require_admin)):
    _require_user_exists(user_id)
    root = user_root(user_id)
    try:
        target = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target == root:
        raise HTTPException(status_code=400, detail="Cannot rename the user's root folder")

    safe_name = sanitize_filename(new_name)
    dest = target.parent / safe_name
    if dest.exists():
        raise HTTPException(status_code=409, detail="A file with that name already exists")
    is_dir = target.is_dir()
    target.rename(dest)

    with db_session() as conn:
        log_action(conn, "FOLDER_RENAME" if is_dir else "FILE_RENAME", request=request,
                    user_id=admin.id, username=admin.username,
                    target_type="user_file", target_id=f"{user_id}:{path}", details=f"renamed to {safe_name}")

    return {"status": "ok", "name": dest.name}


@router.post("/users/{user_id}/files/folder")
def create_user_folder(user_id: int, path: str, name: str, admin: CurrentUser = Depends(require_admin)):
    _require_user_exists(user_id)
    root = user_root(user_id)
    try:
        parent = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    safe_name = sanitize_filename(name)
    new_dir = parent / safe_name
    if new_dir.exists():
        raise HTTPException(status_code=409, detail="Folder already exists")
    new_dir.mkdir(parents=True)
    return {"status": "ok", "name": safe_name}


@router.get("/logs")
def get_logs(
    page: int = 1,
    page_size: int = 50,
    user_id: int | None = None,
    action: str | None = None,
    since: str | None = None,  # e.g. "2026-08-01" -- matched as a date prefix
    admin: CurrentUser = Depends(require_admin),
):
    page_size = min(page_size, 200)  # keep this cheap on SQLite/HDD regardless of what's requested
    clauses, params = [], []
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    offset = max(0, (page - 1) * page_size)
    with db_session() as conn:
        rows = conn.execute(
            f"SELECT * FROM audit_logs {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        total = conn.execute(f"SELECT COUNT(*) AS c FROM audit_logs {where}", params).fetchone()["c"]
    return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}


@router.get("/stats")
def system_stats(admin: CurrentUser = Depends(require_admin)):
    disk = shutil.disk_usage(USER_STORAGE_PATH)
    cpu_percent = None
    ram_percent = None
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.2)
        ram_percent = psutil.virtual_memory().percent
    except ImportError:
        pass

    with db_session() as conn:
        user_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        active_sessions = conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"]

    return {
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_free": disk.free,
        "disk_percent": round(disk.used / disk.total * 100, 1) if disk.total else 0,
        "disk_total_display": human_size(disk.total),
        "disk_used_display": human_size(disk.used),
        "disk_free_display": human_size(disk.free),
        "user_count": user_count,
        "active_sessions": active_sessions,
        "uptime_seconds": int(time.time() - _START_TIME),
    }
