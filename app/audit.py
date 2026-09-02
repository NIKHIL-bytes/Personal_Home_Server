"""
Audit logging for security-sensitive actions.
"""
import sqlite3
from typing import Optional

from fastapi import Request


def log_action(
    conn: sqlite3.Connection,
    action: str,
    request: Optional[Request] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    ip = request.client.host if request and request.client else None
    conn.execute(
        """INSERT INTO audit_logs (user_id, username, action, target_type, target_id, ip_address, details)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, username, action, target_type, target_id, ip, details),
    )
    conn.commit()
