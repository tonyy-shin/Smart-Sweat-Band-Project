"""
SQLite session history backend.

Each session is stored as a JSON blob in ssb_history.db.
Keeps a sliding window of 5 most recent sessions per user.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import logging
logger = logging.getLogger(__name__)

# Config Constants ------------------------------------------------
MAX_SESSIONS = 5
DEFAULT_DB_PATH = Path(__file__).parent / "data" / "ssb_history.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    session_json TEXT NOT NULL
)
"""




def  init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the sessions table"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(_CREATE_TABLE_SQL)


def save_session(
        result: dict,
        db_path: str | Path = DEFAULT_DB_PATH,
        timestamp: str | None = None,
    ) -> None:
    """
    Insert one session result.
    Evict oldest row if at max capacity.
    """
    ts = timestamp or datetime.now().isoformat()
    payload = json.dumps(result)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(_CREATE_TABLE_SQL)
        count = conn.execute("SELECT COUNT(*) FROM  sessions").fetchone()[0]
        if count >= MAX_SESSIONS:
            evict = count - MAX_SESSIONS + 1
            conn.execute(
                "DELETE FROM sessions WHERE id IN "
                "(SELECT id FROM sessions ORDER BY id ASC LIMIT ?)",
                (evict,),
            )
            logger.info("Sessions window full; evicted %d oldest row", evict)
        conn.execute(
            "INSERT INTO sessions (timestamp, session_json) VALUES (?, ?)",
            (ts, payload),
        )
        logger.info("Saved session at %s", ts)


def get_recent_sessions(
        limit: int = MAX_SESSIONS,
        db_path: str | Path = DEFAULT_DB_PATH,
    ) -> list[dict]:
    """Return most recent sessions ordered oldest to newest"""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(_CREATE_TABLE_SQL)
        rows = conn.execute(
            "SELECT session_json FROM sessions ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [json.loads(row[0]) for row in reversed(rows)]


def get_session_count(db_path: str | Path = DEFAULT_DB_PATH) -> int:
    """Return current number of stored sessions"""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(_CREATE_TABLE_SQL)
        return conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    

def get_recent_sessions_with_timestamp(
        limit: int = MAX_SESSIONS,
        db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict]:
    """
    Return most recent sessions ordered oldeest to newest.
    Includes timestamp for front end dashboard.
    """
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(_CREATE_TABLE_SQL)
        rows = conn.execute(
            "SELECT timestamp, session_json FROM sessions ORDER by id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"timestamp": ts, **json.loads(session_json)}
        for ts, session_json in reversed(rows)
    ]