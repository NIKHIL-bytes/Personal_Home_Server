"""
Authentication endpoints: login, logout, session introspection.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.audit import log_action
from app.config import COOKIE_NAME, COOKIE_SECURE
from app.database import db_session
from app.rate_limit import check_login_allowed, record_login_failure, record_login_success
from app.dependencies import CurrentUser, get_current_user
from app.security import (
    generate_session_token,
    hash_password,
    hash_token,
    now_str,
    session_expiry,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-real-ip")
    if forwarded:
        return forwarded.strip()
    return request.client.host if request.client else "unknown"


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response):
    generic_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    username = payload.username.strip().lower()
    ip_address = client_ip(request)

    allowed, retry_after = check_login_allowed(ip_address, username)
    if not allowed:
        response.headers["Retry-After"] = str(retry_after)
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later."
        )

    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        # Always run verify_password (even on a dummy hash) to avoid leaking
        # via response-time whether the username exists.
        dummy_hash = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$c29tZWhhc2g"
        password_hash = row["password_hash"] if row else dummy_hash
        password_ok = verify_password(payload.password, password_hash)

        if not row or not password_ok:
            record_login_failure(ip_address, username)
            log_action(conn, "LOGIN_FAILED", request=request, username=username)
            raise generic_error

        if not row["is_active"]:
            log_action(conn, "LOGIN_FAILED", request=request, user_id=row["id"], username=row["username"],
                        details="account disabled")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

        record_login_success(ip_address, username)
        token = generate_session_token()
        conn.execute(
            """INSERT INTO sessions (user_id, token_hash, expires_at, ip_address, user_agent)
               VALUES (?, ?, ?, ?, ?)""",
            (
                row["id"],
                hash_token(token),
                session_expiry(),
                ip_address,
                request.headers.get("user-agent"),
            ),
        )
        conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_str(), row["id"]))
        log_action(conn, "LOGIN", request=request, user_id=row["id"], username=row["username"])

        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            secure=COOKIE_SECURE,
            max_age=60 * 60 * 24 * 7,
            path="/",
        )
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
        }


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with db_session() as conn:
            row = conn.execute(
                "SELECT user_id FROM sessions WHERE token_hash = ?", (hash_token(token),)
            ).fetchone()
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
            if row:
                log_action(conn, "LOGOUT", request=request, user_id=row["user_id"])
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return user.to_dict()


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, request: Request, user: CurrentUser = Depends(get_current_user)):
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    with db_session() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user.id,)).fetchone()
        if not verify_password(payload.current_password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Current password is incorrect")

        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                      (hash_password(payload.new_password), user.id))
        log_action(conn, "PASSWORD_CHANGED", request=request, user_id=user.id, username=user.username)

    return {"status": "ok"}
