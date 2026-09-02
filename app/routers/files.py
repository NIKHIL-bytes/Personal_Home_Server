"""
Personal file management for the logged-in user.
Every operation is scoped to data/users/<user_id>/ and validated with safe_join.
"""
import asyncio
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse

from app.audit import log_action
from app.config import MAX_UPLOAD_SIZE, USER_STORAGE_PATH
from app.database import db_session
from app.dependencies import CurrentUser, get_current_user
from app.utils import (
    PathSecurityError,
    TEXT_PREVIEW_MAX_BYTES,
    classify_extension,
    directory_size,
    guess_mime,
    human_size,
    preview_kind,
    range_streaming_response,
    safe_join,
    sanitize_filename,
)

router = APIRouter(prefix="/api/files", tags=["files"])

_upload_locks: dict[int, asyncio.Lock] = {}


def _upload_lock(user_id: int) -> asyncio.Lock:
    lock = _upload_locks.get(user_id)

    if lock is None:
        lock = asyncio.Lock()
        _upload_locks[user_id] = lock

    return lock


def user_root(user_id: int) -> Path:
    root = USER_STORAGE_PATH / str(user_id)
    for sub in ("documents", "photos", "videos", "audio", "other"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _entry_meta(path: Path, root: Path) -> dict:
    stat = path.stat()
    is_dir = path.is_dir()
    return {
        "name": path.name,
        "path": str(path.relative_to(root)),
        "is_dir": is_dir,
        "type": None if is_dir else classify_extension(path.name),
        "size": None if is_dir else stat.st_size,
        "size_display": None if is_dir else human_size(stat.st_size),
        "modified_at": int(stat.st_mtime),
    }


@router.get("")
def list_files(
    path: str = "",
    page: int = 1,
    page_size: int = 100,
    user: CurrentUser = Depends(get_current_user),
):
    root = user_root(user.id)
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
    total = len(entries)
    start = max(0, (page - 1) * page_size)
    page_entries = entries[start : start + page_size]

    return {
        "path": path,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_entry_meta(p, root) for p in page_entries],
    }


@router.post("/upload")
async def upload_file(
    path: str = "",
    file: UploadFile = None,
    request: Request = None,
    user: CurrentUser = Depends(get_current_user),
):
    root = user_root(user.id)

    try:
        target_dir = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Destination folder not found",
        )

    if file is None or not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file supplied",
        )

    async with _upload_lock(user.id):
        safe_name = sanitize_filename(file.filename)
        dest = target_dir / safe_name

        counter = 1
        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix

        while dest.exists():
            dest = target_dir / f"{stem} ({counter}){suffix}"
            counter += 1

        current_usage = directory_size(root)
        remaining_quota = max(
            0,
            user.storage_quota - current_usage,
        )

        allowed_size = min(
            MAX_UPLOAD_SIZE,
            remaining_quota,
        )

        if allowed_size <= 0:
            raise HTTPException(
                status_code=413,
                detail="Storage quota exceeded",
            )

        size_written = 0
        tmp_path = dest.with_suffix(
            dest.suffix + ".part"
        )

        try:
            with open(tmp_path, "wb") as out:
                while chunk := await file.read(1024 * 1024):
                    size_written += len(chunk)

                    if size_written > allowed_size:
                        raise HTTPException(
                            status_code=413,
                            detail="Storage quota or upload size limit exceeded",
                        )

                    out.write(chunk)

            tmp_path.rename(dest)

        except HTTPException:
            tmp_path.unlink(missing_ok=True)
            raise

        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=500,
                detail="Upload failed",
            )

    with db_session() as conn:
        log_action(
            conn,
            "FILE_UPLOAD",
            request=request,
            user_id=user.id,
            username=user.username,
            target_type="file",
            target_id=str(dest.relative_to(root)),
        )

    return {
        "status": "ok",
        "name": dest.name,
        "path": str(dest.relative_to(root)),
        "size": size_written,
    }


@router.get("/view")
def view_file(path: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    """
    Display a supported file inline in the browser (image/pdf/video/audio/text).
    Storage root is always derived from the authenticated user, exactly like
    every other personal-file endpoint here -- the client can never supply
    a user id. Unsupported types return 415 so the frontend falls back to
    the "preview unavailable" screen instead of guessing.
    """
    root = user_root(user.id)
    try:
        target = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    kind = preview_kind(target.name)
    mime = guess_mime(target.name)

    with db_session() as conn:
        log_action(conn, "FILE_VIEW", request=request, user_id=user.id, username=user.username,
                    target_type="file", target_id=path)

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
        # text/plain (not text/html) so the browser renders it as inert text,
        # never as executable markup, no matter what the file contains.
        return PlainTextResponse(text, media_type="text/plain; charset=utf-8")

    raise HTTPException(status_code=415, detail="Preview not available for this file type")


@router.get("/download")
def download_file(path: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    root = user_root(user.id)
    try:
        target = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    with db_session() as conn:
        log_action(conn, "FILE_DOWNLOAD", request=request, user_id=user.id, username=user.username,
                    target_type="file", target_id=path)

    return FileResponse(target, filename=target.name)


@router.delete("")
def delete_file(path: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    root = user_root(user.id)
    try:
        target = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target == root:
        raise HTTPException(status_code=400, detail="Cannot delete root folder")

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    with db_session() as conn:
        log_action(conn, "FILE_DELETE", request=request, user_id=user.id, username=user.username,
                    target_type="file", target_id=path)

    return {"status": "ok"}


@router.patch("/rename")
def rename_file(path: str, new_name: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    root = user_root(user.id)
    try:
        target = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")

    safe_name = sanitize_filename(new_name)
    dest = target.parent / safe_name
    if dest.exists():
        raise HTTPException(status_code=409, detail="A file with that name already exists")

    target.rename(dest)

    with db_session() as conn:
        log_action(conn, "FILE_RENAME", request=request, user_id=user.id, username=user.username,
                    target_type="file", target_id=path, details=f"renamed to {safe_name}")

    return {"status": "ok", "name": dest.name}


@router.post("/folder")
def create_folder(path: str, name: str, user: CurrentUser = Depends(get_current_user)):
    root = user_root(user.id)
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


@router.get("/storage")
def storage_summary(user: CurrentUser = Depends(get_current_user)):
    root = user_root(user.id)
    breakdown = {}
    total = 0
    for sub in ("documents", "photos", "videos", "audio", "other"):
        subdir = root / sub
        size = sum(f.stat().st_size for f in subdir.rglob("*") if f.is_file()) if subdir.exists() else 0
        breakdown[sub] = size
        total += size
    usage = shutil.disk_usage(root)
    return {
        "breakdown": {k: {"bytes": v, "display": human_size(v)} for k, v in breakdown.items()},
        "total_used": total,
        "total_used_display": human_size(total),
        "quota": user.storage_quota,
        "quota_display": human_size(user.storage_quota),
        "disk_total": usage.total,
        "disk_free": usage.free,
    }
