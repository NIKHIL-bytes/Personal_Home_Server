"""
Reusable FastAPI dependencies for authentication and permission checks.
Authentication (who are you) and authorization (what can you do) are kept separate.
"""
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status

from app.config import COOKIE_NAME
from app.database import db_session
from app.security import hash_token, now_str


class CurrentUser:
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.display_name = row["display_name"]
        self.role = row["role"]
        self.is_active = bool(row["is_active"])
        self.storage_quota = row["storage_quota"]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "is_admin": self.is_admin,
        }


def get_current_user(hs_session: Optional[str] = Cookie(default=None)) -> CurrentUser:
    """Resolve the active session cookie into a user. Raises 401 if invalid/expired."""
    if not hs_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token_hash = hash_token(hs_session)
    with db_session() as conn:
        row = conn.execute(
            """SELECT s.expires_at, u.* FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ?""",
            (token_hash,),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalid")

        if row["expires_at"] < now_str():
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

        if not row["is_active"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

        return CurrentUser(row)


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user


def get_optional_user(hs_session: Optional[str] = Cookie(default=None)) -> Optional[CurrentUser]:
    """Like get_current_user but returns None instead of raising (used for page rendering)."""
    if not hs_session:
        return None
    try:
        return get_current_user(hs_session)
    except HTTPException:
        return None
