from __future__ import annotations

import re
import threading
from pathlib import Path

import duckdb
import pandas as pd

from document_chat.config import config
from document_chat.logging import get_logger, preview

logger = get_logger("document_chat.tables")

_NAME = re.compile(r"[^A-Za-z0-9_]+")


def sanitize_name(document_id: str, sheet: str) -> str:
    raw = f"t_{document_id}_{sheet}".lower().replace("-", "_")
    cleaned = _NAME.sub("_", raw).strip("_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned

class TableStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path(config.data_dir) / "tables.duckdb"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def load_frame(self, document_id: str, sheet: str, frame: pd.DataFrame) -> str:
        name = sanitize_name(document_id, sheet)
        with self._lock:
            connection = duckdb.connect(str(self._path))
            try:
                connection.register("incoming", frame)
                connection.execute(
                    f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM incoming'
                )
            finally:
                connection.close()
        logger.info(
            "duckdb load document_id=%s sheet=%s table=%s rows=%s cols=%s",
            document_id,
            sheet,
            name,
            len(frame),
            list(frame.columns),
        )
        return name

    def drop_document(self, document_id: str) -> None:
        prefix = sanitize_name(document_id, "")
        with self._lock:
            connection = duckdb.connect(str(self._path))
            try:
                try:
                    rows = connection.execute("SHOW TABLES").fetchall()
                except Exception:
                    logger.exception("duckdb drop failed document_id=%s", document_id)
                    return
                dropped = []
                for row in rows:
                    name = str(row[0])
                    if name.startswith(prefix):
                        connection.execute(f'DROP TABLE IF EXISTS "{name}"')
                        dropped.append(name)
                logger.info("duckdb drop document_id=%s tables=%s", document_id, dropped)
            finally:
                connection.close()

    def tables_for(self, document_ids: list[str]) -> list[str]:
        prefixes = [sanitize_name(document_id, "") for document_id in document_ids]
        with self._lock:
            connection = duckdb.connect(str(self._path), read_only=True)
            try:
                rows = connection.execute("SHOW TABLES").fetchall()
            except Exception:
                logger.exception("duckdb list tables failed document_ids=%s", document_ids)
                return []
            finally:
                connection.close()
        names = []
        for row in rows:
            name = str(row[0])
            if any(name.startswith(prefix) for prefix in prefixes):
                names.append(name)
        return names

    def describe(self, table_names: list[str]) -> str:
        if not table_names:
            return "No spreadsheet tables are registered for this conversation."
        parts = []
        with self._lock:
            connection = duckdb.connect(str(self._path), read_only=True)
            try:
                for name in table_names:
                    columns = connection.execute(f'DESCRIBE "{name}"').fetchall()
                    column_text = ", ".join(
                        f"{column[0]} {column[1]}" for column in columns
                    )
                    sample = connection.execute(
                        f'SELECT * FROM "{name}" LIMIT 3'
                    ).fetchdf()
                    parts.append(
                        f"Table {name}\nColumns: {column_text}\nSample:\n{sample.to_csv(index=False)}"
                    )
            finally:
                connection.close()
        return "\n\n".join(parts)

    def query_select(self, sql: str, allowed_tables: list[str]) -> str:
        logger.info("duckdb query tables=%s sql=%s", allowed_tables, preview(sql, 400))
        statement = _validated_select(sql, set(allowed_tables))
        with self._lock:
            connection = duckdb.connect(str(self._path), read_only=True)
            try:
                frame = connection.execute(statement).fetchdf()
            finally:
                connection.close()
        logger.info("duckdb query done rows=%s", len(frame))
        if len(frame) > 50:
            frame = frame.head(50)
            note = "\n(showing first 50 rows)"
        else:
            note = ""
        return f"rows: {len(frame)}{note}\n{frame.to_csv(index=False)}"


table_store = TableStore()


_BANNED = re.compile(
    r"\b(insert|update|delete|drop|attach|copy|pragma|create|alter|install|load|export|call)\b",
    re.IGNORECASE,
)
_FILE_FUNCTIONS = re.compile(
    r"\b(read_\w+|\w+_scan|glob|getenv|query|query_table|sniff_csv)\s*\(",
    re.IGNORECASE,
)
_TABLE = re.compile(r"\bt_[a-z0-9_]+\b", re.IGNORECASE)

def _validated_select(sql: str, allowed: set[str]) -> str:
    statement = sql.strip().rstrip(";").strip()
    if not statement:
        raise ValueError("SQL is empty")
    if ";" in statement:
        raise ValueError("Only one SELECT statement is allowed")
    lowered = statement.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("Only SELECT statements are allowed")
    if _BANNED.search(statement):
        raise ValueError("Only read-only SELECT statements are allowed")
    if _FILE_FUNCTIONS.search(statement) or re.search(r"'[^']*[/\\.][^']*\.\w{2,5}'", statement):
        raise ValueError("Reading files or external sources is not allowed")
    mentioned = {name.lower() for name in _TABLE.findall(statement)}
    allowed_lower = {name.lower() for name in allowed}
    if not mentioned or not mentioned <= allowed_lower:
        known = ", ".join(sorted(allowed_lower)) or "(none)"
        raise ValueError(f"SQL must use only these tables: {known}")
    return statement
