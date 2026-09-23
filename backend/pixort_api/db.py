"""SQLite access layer.

The schema is a backward compatible superset of the one shipped with the
desktop application (``illustration_manager.db``), so an existing library keeps
working after the front-end/back-end split.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from . import settings

SCHEMA_VERSION = 3

_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS artists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS illustrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        artist_id INTEGER REFERENCES artists(id) ON DELETE SET NULL,
        character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
        title TEXT,
        file_path TEXT NOT NULL,
        tags TEXT,
        rating INTEGER DEFAULT 0,
        remark TEXT,
        created_at TEXT,
        updated_at TEXT,
        file_size INTEGER,
        width INTEGER,
        height INTEGER,
        checksum TEXT,
        sort_order INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_illustrations_artist ON illustrations(artist_id)",
    "CREATE INDEX IF NOT EXISTS idx_illustrations_character ON illustrations(character_id)",
    "CREATE INDEX IF NOT EXISTS idx_illustrations_created ON illustrations(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_illustrations_order ON illustrations(artist_id, sort_order)",
    "CREATE INDEX IF NOT EXISTS idx_illustrations_checksum ON illustrations(checksum)",
)

# table -> {column: DDL fragment}; applied when an older database is opened
_COLUMN_MIGRATIONS: dict[str, dict[str, str]] = {
    "artists": {"created_at": "TEXT"},
    "characters": {"created_at": "TEXT"},
    "illustrations": {
        "updated_at": "TEXT",
        "file_size": "INTEGER",
        "width": "INTEGER",
        "height": "INTEGER",
        "checksum": "TEXT",
        "sort_order": "INTEGER DEFAULT 0",
        "remark": "TEXT",
        "tags": "TEXT",
        "rating": "INTEGER DEFAULT 0",
        "created_at": "TEXT",
    },
}


def now_iso() -> str:
    """Timestamp stored in ``created_at``/``updated_at`` (ISO-8601, seconds)."""
    return datetime.now().isoformat(timespec="seconds")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a tuned connection; one per request keeps threads isolated."""
    target = Path(path or settings.DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class Database:
    """Owns the schema lifecycle; hands out short-lived connections."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or settings.DB_PATH)

    def initialize(self) -> None:
        with self.transaction() as conn:
            for statement in _TABLE_STATEMENTS:
                conn.execute(statement)
            self._migrate(conn)
            for statement in _INDEX_STATEMENTS:
                conn.execute(statement)
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        for table, columns in _COLUMN_MIGRATIONS.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, ddl in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = connect(self.path)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Connection that commits on success and rolls back on failure."""
        conn = connect(self.path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()
