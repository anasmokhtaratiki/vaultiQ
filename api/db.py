"""SQLite storage: users registry, loans and an append-only, hash-chained audit log."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  id_number TEXT NOT NULL UNIQUE,
  dob TEXT
);
CREATE TABLE IF NOT EXISTS loans (
  loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(user_id),
  amount REAL NOT NULL,
  months INTEGER NOT NULL,
  purpose TEXT,
  device_id TEXT,
  status TEXT NOT NULL,
  trust_score INTEGER,
  risk_tier TEXT,
  risk_narrative TEXT,
  signature_level TEXT,
  pdf_path TEXT,
  xades_path TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  event TEXT NOT NULL,
  actor TEXT NOT NULL,
  loan_id INTEGER,
  detail TEXT,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""

# Demo registry (fictional people). In production this is a national ID API.
SEED_USERS = [
    ("Amine Ben Salah", "12345678", "1995-04-12"),
    ("Sarra Trabelsi", "87654321", "1992-09-30"),
    ("Youssef Gharbi", "11223344", "1998-01-21"),
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR IGNORE INTO users (full_name, id_number, dob) VALUES (?, ?, ?)", SEED_USERS
        )


def audit(conn, event, actor, loan_id=None, detail=None):
    """Append an event; each row hashes the previous one so tampering is detectable."""
    last = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev_hash = last["hash"] if last else "0" * 64
    ts = now()
    detail_s = json.dumps(detail or {}, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(
        f"{prev_hash}|{ts}|{event}|{actor}|{loan_id}|{detail_s}".encode()
    ).hexdigest()
    conn.execute(
        "INSERT INTO audit_log (ts, event, actor, loan_id, detail, prev_hash, hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ts, event, actor, loan_id, detail_s, prev_hash, digest),
    )
