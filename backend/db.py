import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS intake (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT UNIQUE NOT NULL,
    received_at TEXT,
    processed_at TEXT NOT NULL,
    sender_name TEXT,
    sender_email TEXT,
    subject TEXT,
    request_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    property_address TEXT,
    summary TEXT,
    extraction_json TEXT NOT NULL,
    action_type TEXT NOT NULL,
    action_subject TEXT,
    action_body TEXT,
    flags_json TEXT NOT NULL,
    raw_email_text TEXT NOT NULL
)
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(SCHEMA)


def source_already_processed(source_file: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM intake WHERE source_file = ?", (source_file,)
        ).fetchone()
        return row is not None


def insert_intake(record: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO intake (
                source_file, received_at, processed_at, sender_name, sender_email,
                subject, request_type, confidence, property_address, summary,
                extraction_json, action_type, action_subject, action_body,
                flags_json, raw_email_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["source_file"],
                record.get("received_at"),
                datetime.now(timezone.utc).isoformat(),
                record.get("sender_name"),
                record.get("sender_email"),
                record.get("subject"),
                record["request_type"],
                record["confidence"],
                record.get("property_address"),
                record.get("summary"),
                record["extraction_json"],
                record["action_type"],
                record.get("action_subject"),
                record.get("action_body"),
                json.dumps(record.get("flags", [])),
                record["raw_email_text"],
            ),
        )
        return cur.lastrowid


def list_intake():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM intake ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_intake(intake_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM intake WHERE id = ?", (intake_id,)
        ).fetchone()
        return dict(row) if row else None


def clear_all():
    with get_conn() as conn:
        conn.execute("DELETE FROM intake")
