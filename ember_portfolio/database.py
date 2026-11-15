"""SQLite access for the portfolio contact form.

Only the standard-library sqlite3 module is used. Every query is parameterised
(the ? placeholders), so user text is never pasted into SQL.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "portfolio.db"))

# Columns the app needs. If your existing `messages` table lacks any of them,
# init_db() adds them, so your old rows are kept.
_REQUIRED_COLUMNS = {
    "name": "TEXT NOT NULL DEFAULT ''",
    "email": "TEXT NOT NULL DEFAULT ''",
    "message": "TEXT NOT NULL DEFAULT ''",
    "created_at": "TEXT NOT NULL DEFAULT ''",
    "email_status": "TEXT NOT NULL DEFAULT 'pending'",
    "email_error": "TEXT",
}


@contextmanager
def get_connection():
    """Open a connection, commit on success, roll back on error, always close."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create the messages table if needed and add any missing columns."""
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT)"
        )
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(messages)")}
        for column, definition in _REQUIRED_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {column} {definition}")


def save_message(name: str, email: str, message: str, created_at: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO messages (name, email, message, created_at, email_status) "
            "VALUES (?, ?, ?, ?, 'pending')",
            (name, email, message, created_at),
        )
        return cur.lastrowid


def set_email_status(message_id: int, status: str, error: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE messages SET email_status = ?, email_error = ? WHERE id = ?",
            (status, (error or "")[:300] or None, message_id),
        )


def list_messages(limit: int = 100) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, email, message, created_at, email_status, email_error "
            "FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def ping() -> bool:
    """Used by the health check."""
    with get_connection() as conn:
        conn.execute("SELECT 1")
    return True
