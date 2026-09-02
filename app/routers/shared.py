"""
Shared file storage. All authenticated users may browse/download.
Only administrators may upload, rename, move, or delete.
"""
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from app.audit import log_action
from app.config import MAX_UPLOAD_SIZE, SHARED_STORAGE_PATH
from app.database import db_session
from app.dependencies import CurrentUser, get_current_user, require_admin
from app.utils import (
    PathSecurityError,
    TEXT_PREVIEW_MAX_BYTES,
    classify_extension,
    guess_mime,
    human_size,
    preview_kind,
    range_streaming_response,
    safe_join,
    sanitize_filename,
)

router = APIRouter(prefix="/api/shared", tags=["shared"])

SHARED_STORAGE_PATH.mkdir(parents=True, exist_ok=True)


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
def list_shared(path: str = "", user: CurrentUser = Depends(get_current_user)):
    try:
        target = safe_join(SHARED_STORAGE_PATH, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    entries = sorted(
        (p for p in target.iterdir() if not p.name.startswith(".") and not p.name.endswith(".part")),
        key=lambda p: (p.is_file(), p.name.lower()),
    )
    return {"path": path, "items": [_entry_meta(p, SHARED_STORAGE_PATH) for p in entries]}


@router.get("/view")
def view_shared(path: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    """Display a supported shared file inline. Any authenticated user may
    preview shared files (same as the existing download rule) -- only
    upload/rename/delete stay admin-only, unchanged."""
    try:
        target = safe_join(SHARED_STORAGE_PATH, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    kind = preview_kind(target.name)
    mime = guess_mime(target.name)

    with db_session() as conn:
        log_action(conn, "FILE_VIEW", request=request, user_id=user.id, username=user.username,
                    target_type="shared_file", target_id=path)

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


@router.get("/download")
def download_shared(path: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    try:
        target = safe_join(SHARED_STORAGE_PATH, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    with db_session() as conn:
        log_action(conn, "FILE_DOWNLOAD", request=request, user_id=user.id, username=user.username,
                    target_type="shared_file", target_id=path)

    return FileResponse(target, filename=target.name)


@router.post("/upload")
async def upload_shared(
    path: str = "",
    file: UploadFile = None,
    request: Request = None,
    admin: CurrentUser = Depends(require_admin),
):
    try:
        target_dir = safe_join(SHARED_STORAGE_PATH, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="Destination folder not found")

    safe_name = sanitize_filename(file.filename)
    dest = target_dir / safe_name
    counter = 1
    stem, suffix = Path(safe_name).stem, Path(safe_name).suffix
    while dest.exists():
        dest = target_dir / f"{stem} ({counter}){suffix}"
        counter += 1

    tmp_path = dest.with_suffix(dest.suffix + ".part")
    size_written = 0
    try:
        with open(tmp_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size_written += len(chunk)
                if size_written > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="File too large")
                out.write(chunk)
        tmp_path.rename(dest)
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Upload failed")

    with db_session() as conn:
        log_action(conn, "SHARED_FILE_UPLOAD", request=request, user_id=admin.id, username=admin.username,
                    target_type="shared_file", target_id=str(dest.relative_to(SHARED_STORAGE_PATH)))

    return {"status": "ok", "name": dest.name}


@router.delete("")
def delete_shared(path: str, request: Request, admin: CurrentUser = Depends(require_admin)):
    try:
        target = safe_join(SHARED_STORAGE_PATH, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target == SHARED_STORAGE_PATH:
        raise HTTPException(status_code=400, detail="Cannot delete root folder")

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    with db_session() as conn:
        log_action(conn, "SHARED_FILE_DELETE", request=request, user_id=admin.id, username=admin.username,
                    target_type="shared_file", target_id=path)

    return {"status": "ok"}


@router.patch("/rename")
def rename_shared(path: str, new_name: str, request: Request, admin: CurrentUser = Depends(require_admin)):
    try:
        target = safe_join(SHARED_STORAGE_PATH, path)
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
        log_action(conn, "FILE_RENAME", request=request, user_id=admin.id, username=admin.username,
                    target_type="shared_file", target_id=path, details=f"renamed to {safe_name}")

    return {"status": "ok", "name": dest.name}


@router.post("/folder")
def create_shared_folder(path: str, name: str, admin: CurrentUser = Depends(require_admin)):
    try:
        parent = safe_join(SHARED_STORAGE_PATH, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    safe_name = sanitize_filename(name)
    new_dir = parent / safe_name
    if new_dir.exists():
        raise HTTPException(status_code=409, detail="Folder already exists")
    new_dir.mkdir(parents=True)
    return {"status": "ok", "name": safe_name}
