"""
Media library: browsing, lightweight thumbnails, and streamed playback
with HTTP Range support so the browser can seek without loading whole files.
"""
import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.config import MAX_UPLOAD_SIZE, MEDIA_STORAGE_PATH, THUMBNAIL_PATH
from app.dependencies import CurrentUser, get_current_user, require_admin
from app.utils import PathSecurityError, guess_mime, human_size, safe_join, sanitize_filename

router = APIRouter(prefix="/api/media", tags=["media"])

CATEGORY_DIRS = {"photos": "image", "videos": "video", "audio": "audio", "other": "other"}
CHUNK_SIZE = 1024 * 1024  # 1 MB
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _media_id(rel_path: str) -> str:
    return hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:16]


def _resolve_by_id(media_id: str) -> Path:
    """We don't keep a DB table of media (kept lightweight); instead we
    walk the small, bounded media root to find the file whose id matches.
    For a typical home library this is fast; a future version could cache
    an id->path index in SQLite if the library grows very large."""
    for category in CATEGORY_DIRS:
        base = MEDIA_STORAGE_PATH / category
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if f.is_file() and not f.name.startswith(".") and not f.name.endswith(".part"):
                rel = str(f.relative_to(MEDIA_STORAGE_PATH))
                if _media_id(rel) == media_id:
                    return f
    raise HTTPException(status_code=404, detail="Media not found")


@router.get("")
def list_media(category: str = "photos", path: str = "", page: int = 1, page_size: int = 60,
               user: CurrentUser = Depends(get_current_user)):
    if category not in CATEGORY_DIRS:
        raise HTTPException(status_code=400, detail="Invalid category")

    root = MEDIA_STORAGE_PATH / category
    root.mkdir(parents=True, exist_ok=True)
    try:
        target = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")

    files = sorted(
        [f for f in target.iterdir() if f.is_file() and not f.name.startswith(".") and not f.name.endswith(".part")],
        key=lambda p: p.name.lower(),
    )
    folders = sorted(
        [f for f in target.iterdir() if f.is_dir() and not f.name.startswith(".")],
        key=lambda p: p.name.lower(),
    )

    total = len(files)
    start = max(0, (page - 1) * page_size)
    page_files = files[start : start + page_size]

    items = []
    for f in page_files:
        rel = str(f.relative_to(MEDIA_STORAGE_PATH))
        items.append({
            "id": _media_id(rel),
            "name": f.name,
            "size_display": human_size(f.stat().st_size),
            "category": category,
        })

    return {
        "category": category,
        "path": path,
        "folders": [f.name for f in folders],
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.get("/{media_id}/thumbnail")
def get_thumbnail(media_id: str, user: CurrentUser = Depends(get_current_user)):
    source = _resolve_by_id(media_id)
    ext = source.suffix.lower()

    # Only photos get real generated thumbnails; video/audio get a static placeholder.
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        placeholder = Path(__file__).resolve().parent.parent / "static/images/media-placeholder.svg"
        return FileResponse(placeholder, media_type="image/svg+xml")

    THUMBNAIL_PATH.mkdir(parents=True, exist_ok=True)
    thumb_path = THUMBNAIL_PATH / f"{media_id}.jpg"

    if not thumb_path.exists():
        try:
            from PIL import Image
            with Image.open(source) as img:
                img = img.convert("RGB")
                img.thumbnail((320, 320))
                img.save(thumb_path, "JPEG", quality=80)
        except Exception:
            # If thumbnailing fails for any reason, fall back to the original.
            return FileResponse(source)

    return FileResponse(thumb_path, media_type="image/jpeg")


@router.get("/{media_id}/stream")
def stream_media(media_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    source = _resolve_by_id(media_id)
    file_size = source.stat().st_size
    mime = guess_mime(source.name)

    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(source, media_type=mime)

    match = RANGE_RE.match(range_header)
    if not match:
        raise HTTPException(status_code=416, detail="Invalid Range header")

    start_str, end_str = match.groups()
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1
    end = min(end, file_size - 1)

    if start > end or start >= file_size:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    length = end - start + 1

    def iter_chunk():
        with open(source, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }
    return StreamingResponse(iter_chunk(), status_code=206, media_type=mime, headers=headers)


@router.post("/upload")
async def upload_media(category: str = "photos", path: str = "", file: UploadFile = None,
                        admin: CurrentUser = Depends(require_admin)):
    if category not in CATEGORY_DIRS:
        raise HTTPException(status_code=400, detail="Invalid category")

    root = MEDIA_STORAGE_PATH / category
    root.mkdir(parents=True, exist_ok=True)
    try:
        target_dir = safe_join(root, path)
    except PathSecurityError:
        raise HTTPException(status_code=400, detail="Invalid path")
    target_dir.mkdir(parents=True, exist_ok=True)

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

    return {"status": "ok", "name": dest.name}


@router.delete("/{media_id}")
def delete_media(media_id: str, admin: CurrentUser = Depends(require_admin)):
    source = _resolve_by_id(media_id)
    source.unlink()
    thumb = THUMBNAIL_PATH / f"{media_id}.jpg"
    thumb.unlink(missing_ok=True)
    return {"status": "ok"}
