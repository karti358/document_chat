from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Literal

from document_chat.config import config
from document_chat.logging import get_logger

logger = get_logger("document_chat.sqlite")

TableName = Literal["documents", "conversations"]

_store: "SqliteStore | None" = None
_store_lock = threading.Lock()


class SqliteStore:
    """Key–value style storage: each row is (id, data) where data is a JSON string."""

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is not None:
            self._db_path = db_path
        elif config.sqlite_path:
            self._db_path = Path(config.sqlite_path)
        else:
            self._db_path = Path(config.data_dir) / "document_chat.sqlite"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._create_tables()

    @property
    def path(self) -> Path:
        return self._db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, table: TableName, row_id: str) -> dict | None:
        conn = self.connect()
        try:
            row = conn.execute(
                f"SELECT data FROM {table} WHERE id = ?",
                (row_id,),
            ).fetchone()
            return _loads(row["data"]) if row else None
        finally:
            conn.close()

    def put(self, table: TableName, record: dict) -> None:
        row_id = record["id"]
        payload = _dumps(record)
        with self._lock:
            conn = self.connect()
            try:
                conn.execute(
                    f"""
                    INSERT INTO {table} (id, data) VALUES (?, ?)
                    ON CONFLICT(id) DO UPDATE SET data = excluded.data
                    """,
                    (row_id, payload),
                )
                conn.commit()
            finally:
                conn.close()
        logger.info("sqlite put table=%s id=%s bytes=%s", table, row_id, len(payload))

    def delete(self, table: TableName, row_id: str) -> None:
        with self._lock:
            conn = self.connect()
            try:
                conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
                conn.commit()
            finally:
                conn.close()
        logger.info("sqlite delete table=%s id=%s", table, row_id)

    def list_records(self, table: TableName) -> list[dict]:
        conn = self.connect()
        try:
            rows = conn.execute(f"SELECT data FROM {table}").fetchall()
            return [_loads(row["data"]) for row in rows]
        finally:
            conn.close()

    def _create_tables(self) -> None:
        with self._lock:
            conn = self.connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        id TEXT PRIMARY KEY,
                        data TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id TEXT PRIMARY KEY,
                        data TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()


def get_sqlite_store() -> SqliteStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = SqliteStore()
        return _store


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _loads(raw: str) -> dict:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Stored record must be a JSON object")
    return parsed
