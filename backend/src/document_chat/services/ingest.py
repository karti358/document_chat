from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from document_chat.logging import get_logger
from document_chat.services.index.chroma_store import chroma_store
from document_chat.services.index.table_store import table_store
from document_chat.services.parsers import parse_document

logger = get_logger("document_chat.ingest")

def index_document(record: dict) -> dict:
    path = Path(record["path"])
    logger.info(
        "index start id=%s file=%s",
        record.get("id"),
        record.get("filename"),
    )
    chroma_store.delete_document(record["id"])
    table_store.drop_document(record["id"])
    try:
        chunks = parse_document(path, record)
        if chunks:
            chroma_store.upsert(chunks)
    except Exception as exc:
        logger.exception("index failed id=%s file=%s", record.get("id"), record.get("filename"))
        raise exc
    logger.info(
        "index ready id=%s file=%s chunks=%s",
        record.get("id"),
        record.get("filename"),
        len(chunks),
    )
    return {
        **record,
        "parser_status": "ready",
        "parser_error": "",
        "chunk_count": len(chunks),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def unindex_document(document_id: str) -> None:
    logger.info("unindex id=%s", document_id)
    chroma_store.delete_document(document_id)
    table_store.drop_document(document_id)
