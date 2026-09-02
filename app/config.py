"""
Centralized configuration for the Home Server application.
All values are read from environment variables (see .env.example).
Never hard-code secrets here.
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

APP_NAME = os.getenv("APP_NAME", "Home Server")
APP_ENV = os.getenv("APP_ENV", "development")

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if APP_ENV == "production":
        raise RuntimeError(
            "SECRET_KEY environment variable must be set in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    # Dev-only fallback so the app can boot locally without a .env file.
    SECRET_KEY = secrets.token_hex(32)

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "data/database/server.db")))
USER_STORAGE_PATH = Path(os.getenv("USER_STORAGE_PATH", str(BASE_DIR / "data/users")))
SHARED_STORAGE_PATH = Path(os.getenv("SHARED_STORAGE_PATH", str(BASE_DIR / "data/shared")))
MEDIA_STORAGE_PATH = Path(os.getenv("MEDIA_STORAGE_PATH", str(BASE_DIR / "data/media")))
THUMBNAIL_PATH = Path(os.getenv("THUMBNAIL_PATH", str(BASE_DIR / "data/thumbnails")))

# 5 GB default max upload size
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(5 * 1024 * 1024 * 1024)))

SESSION_TIMEOUT_HOURS = int(os.getenv("SESSION_TIMEOUT_HOURS", "168"))  # 7 days

COOKIE_NAME = "hs_session"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true" if APP_ENV == "production" else "false").strip().lower() in {"1", "true", "yes", "on"}

DEFAULT_USER_QUOTA_BYTES = int(os.getenv("DEFAULT_USER_QUOTA_BYTES", str(20 * 1024 * 1024 * 1024)))

# Ensure required directories exist at import time (cheap, idempotent).
for path in (
    DATABASE_PATH.parent,
    USER_STORAGE_PATH,
    SHARED_STORAGE_PATH,
    MEDIA_STORAGE_PATH / "photos",
    MEDIA_STORAGE_PATH / "videos",
    MEDIA_STORAGE_PATH / "audio",
    MEDIA_STORAGE_PATH / "other",
    THUMBNAIL_PATH,
    BASE_DIR / "logs",
):
    path.mkdir(parents=True, exist_ok=True)
