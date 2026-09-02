"""
Lightweight system endpoints used for monitoring and the dashboard's status widget.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.database import db_session
from app.dependencies import CurrentUser, get_current_user

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health():
    db_ok = True
    try:
        with db_session() as conn:
            conn.execute("SELECT 1")
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "storage": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/me/activity")
def my_activity(limit: int = 10, user: CurrentUser = Depends(get_current_user)):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT action, target_type, target_id, timestamp FROM audit_logs "
            "WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user.id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/api/system/status")
def status(user: CurrentUser = Depends(get_current_user)):
    """Simple online/healthy indicators for the dashboard status widget."""
    health_data = health()
    return {
        "server": "online",
        "storage": "healthy" if health_data["storage"] == "ok" else "degraded",
        "database": "online" if health_data["database"] == "ok" else "offline",
        "network": "online",
    }
