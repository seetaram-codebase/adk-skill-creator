import sqlite3, json, os
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "./skill_builder.db")


def init_db():
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS drafts (
                draft_id    TEXT PRIMARY KEY,
                skill_name  TEXT NOT NULL,
                skill_dir   TEXT NOT NULL,
                files       TEXT NOT NULL,   -- JSON: {relative_path: content}
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                conversation_id  TEXT PRIMARY KEY,
                adk_session_id   TEXT NOT NULL,
                created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- Drafts ---

def save_draft(draft_id: str, skill_name: str, skill_dir: str, files: dict[str, str]):
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO drafts (draft_id, skill_name, skill_dir, files) VALUES (?,?,?,?)",
            (draft_id, skill_name, skill_dir, json.dumps(files)),
        )


def get_draft(draft_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
    if not row:
        return None
    return {
        "draft_id": row["draft_id"],
        "skill_name": row["skill_name"],
        "skill_dir": row["skill_dir"],
        "files": json.loads(row["files"]),
        "created_at": row["created_at"],
    }


def list_drafts() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT draft_id, skill_name, skill_dir, created_at FROM drafts ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# --- Sessions ---

def save_session(conversation_id: str, adk_session_id: str):
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions (conversation_id, adk_session_id) VALUES (?,?)",
            (conversation_id, adk_session_id),
        )


def get_adk_session_id(conversation_id: str) -> str | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT adk_session_id FROM sessions WHERE conversation_id=?", (conversation_id,)
        ).fetchone()
    return row["adk_session_id"] if row else None
