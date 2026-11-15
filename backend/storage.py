import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def data_dir():
    return Path(os.getenv("DATA_DIR", "data").strip() or "data")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def execute(sql, params=()):
    conn = sqlite3.connect(data_dir() / "chat.db", timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def init_db():
    data_dir().mkdir(parents=True, exist_ok=True)
    execute(
        """CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'chat',
            lead_offered INTEGER NOT NULL DEFAULT 0,
            lead_name TEXT,
            lead_phone TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            kind TEXT NOT NULL,
            debug TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            company TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id)")


def create_session():
    session_id = uuid.uuid4().hex
    execute(
        "INSERT INTO sessions (id, created_at) VALUES (?, ?)",
        (session_id, now()),
    )
    return session_id


def get_session(session_id):
    rows = execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    return rows[0] if rows else None


def update_session(session_id, **fields):
    columns = ", ".join(f"{name} = ?" for name in fields)
    execute(
        f"UPDATE sessions SET {columns} WHERE id = ?",
        (*fields.values(), session_id),
    )


def add_message(session_id, role, content, kind, debug=None):
    debug_text = json.dumps(debug, ensure_ascii=False) if debug is not None else None
    execute(
        "INSERT INTO messages (session_id, role, content, kind, debug, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, role, content, kind, debug_text, now()),
    )


def get_messages(session_id, kind=None):
    sql = "SELECT role, content, kind, debug, created_at FROM messages WHERE session_id = ?"
    params = [session_id]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    rows = execute(sql + " ORDER BY id", params)
    for row in rows:
        row["debug"] = json.loads(row["debug"]) if row["debug"] else None
    return rows


def list_sessions():
    return execute(
        """SELECT s.id, s.created_at,
            (SELECT content FROM messages m
                WHERE m.session_id = s.id AND m.role = 'user' AND m.kind = 'chat'
                ORDER BY m.id LIMIT 1) AS first_message,
            (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count,
            (SELECT COUNT(*) FROM leads l WHERE l.session_id = s.id) AS lead_count
        FROM sessions s
        ORDER BY s.rowid DESC"""
    )


def save_lead(session_id, name, phone, company, summary):
    execute(
        "INSERT INTO leads (session_id, name, phone, company, summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, name, phone, company, summary, now()),
    )


def list_leads():
    return execute(
        "SELECT id, session_id, name, phone, company, summary, created_at FROM leads ORDER BY id DESC"
    )
