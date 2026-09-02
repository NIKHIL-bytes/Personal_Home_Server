"""
Interactive CLI to create an administrator account.
Usage (from /opt/home-server, with the venv active):
    python -m app.create_admin
"""
import getpass
import sys

from app.config import USER_STORAGE_PATH
from app.database import db_session, init_db
from app.security import hash_password


def main():
    init_db()

    print("=== Create Administrator Account ===")
    username = input("Username: ").strip().lower()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)

    display_name = input("Display name: ").strip() or username

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)

    with db_session() as conn:
        existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            print(f"A user named '{username}' already exists.")
            sys.exit(1)

        cur = conn.execute(
            """INSERT INTO users (username, password_hash, display_name, role)
               VALUES (?, ?, ?, 'admin')""",
            (username, hash_password(password), display_name),
        )
        new_id = cur.lastrowid

    root = USER_STORAGE_PATH / str(new_id)
    for sub in ("documents", "photos", "videos", "audio", "other"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    print(f"\nAdministrator '{username}' created successfully (id={new_id}).")
    print("You can now log in from the web UI.")


if __name__ == "__main__":
    main()
