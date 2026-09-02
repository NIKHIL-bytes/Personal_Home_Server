"""
SQLite database access layer.
Uses raw sqlite3 (no ORM) to keep the app lightweight on low-resource hardware.

Schema changes are handled two ways:
  1. CREATE TABLE/INDEX IF NOT EXISTS in SCHEMA -- creates everything from
     scratch on a brand-new install. A no-op on any table that already exists.
  2. migrate_schema() -- an additive-only migration step that runs on every
     startup (fresh or existing install alike). It inspects each table with
     PRAGMA table_info(), adds any columns the current app code expects but
     an older install is missing, backfills sensible defaults for the rows
     that just gained a column, and (re)creates indexes once their columns
     are confirmed present. It never drops, renames, or recreates a table,
     and never touches existing data beyond filling in genuinely missing
     columns -- existing users, password hashes, sessions, and audit logs
     are left exactly as they are.
"""
import sqlite3
from contextlib import contextmanager

from app.config import DATABASE_PATH, DEFAULT_USER_QUOTA_BYTES

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin', 'user')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_login      TEXT,
    storage_quota   INTEGER NOT NULL DEFAULT 21474836480
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT UNIQUE NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL,
    ip_address  TEXT,
    user_agent  TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username    TEXT,
    action      TEXT NOT NULL,
    target_type TEXT,
    target_id   TEXT,
    ip_address  TEXT,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    details     TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db_session():
    """Context manager that yields a connection and commits/rollbacks automatically."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _existing_columns(conn: sqlite3.Connection, table: str) -> set:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, coltype_sql: str) -> bool:
    """Adds `column` to `table` if it isn't already there. Returns True if it
    actually added the column (so callers know whether a backfill is needed),
    False if the column already existed (existing data untouched)."""
    if column in _existing_columns(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype_sql}")
    return True


def _create_index_if_columns_exist(conn: sqlite3.Connection, index_name: str, table: str, columns: list) -> None:
    """Only creates the index once every column it references is confirmed
    present -- CREATE INDEX on a column that doesn't exist yet would raise
    an OperationalError and break startup on a genuinely old schema."""
    existing = _existing_columns(conn, table)
    if all(c in existing for c in columns):
        cols_sql = ", ".join(columns)
        conn.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({cols_sql})")


def migrate_schema(conn: sqlite3.Connection) -> None:
    """
    Idempotent, additive-only migration for pre-existing databases.

    Safe to run on every startup:
      - On a brand-new database, `users`/`sessions`/`audit_logs` don't exist
        yet at the point this runs relative to SCHEMA having just created
        them with every current column already in place, so every check
        below is a harmless no-op.
      - On an existing database from an older version of this project, it
        adds exactly the columns this version of the app needs and nothing
        else -- it never drops or recreates a table, never deletes a row,
        and never touches a password_hash, session, or audit log entry.
    """
    if not _table_exists(conn, "users"):
        return  # nothing to migrate -- SCHEMA already built the current shape

    # --- users: add any columns this version relies on -------------------
    added = set()
    for column, coltype in (
        ("display_name", "TEXT"),
        ("role", "TEXT NOT NULL DEFAULT 'user'"),
        ("is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("created_at", "TEXT"),
        ("last_login", "TEXT"),
        ("storage_quota", f"INTEGER NOT NULL DEFAULT {DEFAULT_USER_QUOTA_BYTES}"),
    ):
        # display_name/created_at can't carry a per-row DEFAULT in ALTER TABLE
        # (SQLite only allows a constant there), so they're added nullable
        # and backfilled below with a real per-row value instead.
        if _add_column_if_missing(conn, "users", column, coltype):
            added.add(column)

    if "display_name" in added:
        # Sensible default for pre-existing accounts: reuse their username.
        conn.execute(
            "UPDATE users SET display_name = username WHERE display_name IS NULL OR TRIM(display_name) = ''"
        )

    if "created_at" in added:
        conn.execute("UPDATE users SET created_at = datetime('now') WHERE created_at IS NULL")

    if "role" in added:
        # `role` didn't exist before this migration, meaning every existing
        # row just got 'user' as its DEFAULT. Before accepting that, check
        # whether an older version of this project tracked admin status
        # under a different column name and migrate it forward instead of
        # silently demoting every existing administrator.
        existing_cols = _existing_columns(conn, "users")
        for legacy_col in ("is_admin", "is_superuser", "admin"):
            if legacy_col in existing_cols:
                try:
                    conn.execute(f"UPDATE users SET role = 'admin' WHERE {legacy_col} = 1")
                except sqlite3.OperationalError:
                    # Unexpected type/shape for that legacy column -- skip
                    # rather than fail the whole migration over it.
                    pass

    # Note: SQLite's ALTER TABLE ADD COLUMN cannot attach a CHECK constraint,
    # so a migrated `role` column doesn't get the CHECK(role IN ('admin',
    # 'user')) that a fresh install's CREATE TABLE has. This is enforced at
    # the application layer instead (every endpoint that writes `role`
    # validates it's 'admin' or 'user' before the UPDATE/INSERT).

    # --- sessions: add any columns this version relies on -----------------
    if _table_exists(conn, "sessions"):
        _add_column_if_missing(conn, "sessions", "ip_address", "TEXT")
        _add_column_if_missing(conn, "sessions", "user_agent", "TEXT")
        _create_index_if_columns_exist(conn, "idx_sessions_token_hash", "sessions", ["token_hash"])
        _create_index_if_columns_exist(conn, "idx_sessions_expires_at", "sessions", ["expires_at"])

    # --- audit_logs: add any columns this version relies on ---------------
    if _table_exists(conn, "audit_logs"):
        _add_column_if_missing(conn, "audit_logs", "username", "TEXT")
        _add_column_if_missing(conn, "audit_logs", "details", "TEXT")
        _create_index_if_columns_exist(conn, "idx_audit_logs_timestamp", "audit_logs", ["timestamp"])
        _create_index_if_columns_exist(conn, "idx_audit_logs_user_id", "audit_logs", ["user_id"])

    _create_index_if_columns_exist(conn, "idx_users_username", "users", ["username"])


def init_db() -> None:
    with db_session() as conn:
        conn.executescript(SCHEMA)  # creates anything missing entirely (fresh installs)
        migrate_schema(conn)        # adds anything missing from existing tables (upgrades)
