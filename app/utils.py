"""
Shared utilities: safe path resolution (path-traversal protection),
file-type classification, and human-readable formatting.
"""
import mimetypes
import re
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg", ".heic"}
VIDEO_EXT = {".mp4", ".webm", ".mkv", ".mov", ".avi"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
DOCUMENT_EXT = {".pdf", ".txt", ".md", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz"}

# Narrower sets used specifically to decide in-browser viewer behavior.
# (DOCUMENT_EXT above stays broad — it's used for file-icon classification
# elsewhere and intentionally includes formats we do NOT preview, like docx.)
PDF_EXT = {".pdf"}
TEXT_PREVIEW_EXT = {".txt", ".md", ".csv", ".log"}
VIEWABLE_VIDEO_EXT = {".mp4", ".webm", ".ogg"}  # browser-playable subset of VIDEO_EXT
VIEWABLE_AUDIO_EXT = {".mp3", ".wav", ".ogg"}

# Cap how much of a text file we ever read into memory for preview.
TEXT_PREVIEW_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


def preview_kind(filename: str) -> str:
    """Classify a file for the in-browser viewer. Returns one of:
    'image', 'pdf', 'video', 'audio', 'text', or 'unsupported'."""
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in PDF_EXT:
        return "pdf"
    if ext in VIEWABLE_VIDEO_EXT:
        return "video"
    if ext in VIEWABLE_AUDIO_EXT:
        return "audio"
    if ext in TEXT_PREVIEW_EXT:
        return "text"
    return "unsupported"


class PathSecurityError(Exception):
    """Raised when a requested path would escape its permitted root."""


def safe_join(root: Path, relative_path: str) -> Path:
    """
    Resolve `relative_path` against `root` and guarantee the result stays
    inside `root`. Raises PathSecurityError on any attempted traversal.
    """
    root = root.resolve()
    relative_path = (relative_path or "").strip().lstrip("/\\")
    # Reject null bytes and obviously malicious sequences up front.
    if "\x00" in relative_path:
        raise PathSecurityError("Invalid path")

    candidate = (root / relative_path).resolve()

    try:
        candidate.relative_to(root)
    except ValueError:
        raise PathSecurityError("Path escapes permitted root")

    return candidate


def classify_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in DOCUMENT_EXT:
        return "document"
    if ext in ARCHIVE_EXT:
        return "archive"
    return "other"


def guess_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def directory_size(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(
        path.stat().st_size
        for path in root.rglob("*")
        if path.is_file()
    )


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\- ]+")


def sanitize_filename(filename: str) -> str:
    """Strip directory components and disallowed characters from an uploaded filename."""
    name = Path(filename).name  # drop any path components
    name = _SAFE_NAME_RE.sub("_", name).strip()
    if not name or name in (".", ".."):
        name = "file"
    return name[:255]


_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
_STREAM_CHUNK_SIZE = 1024 * 1024  # 1 MB


def range_streaming_response(path: Path, request: Request, mime: str) -> Response:
    """
    Serve `path` with HTTP Range support so <video>/<audio> can seek without
    the browser (or this server) ever loading the whole file into memory.
    Mirrors the streaming approach already used by the media library
    (app/routers/media.py) so personal/shared file previews behave the same
    way video/audio already does elsewhere in the app.
    """
    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type=mime)

    match = _RANGE_RE.match(range_header)
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
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(_STREAM_CHUNK_SIZE, remaining))
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
