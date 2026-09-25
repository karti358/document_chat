from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

from document_chat.config import config
from document_chat.db.sqlite_store import get_sqlite_store
from document_chat.logging import get_logger
from document_chat.services.conversations import conversations_service
from document_chat.services.parsers.kinds import kind_for_filename

ALLOWED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".pptx",
    ".csv",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".html",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
logger = get_logger("document_chat.documents")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = _SAFE_NAME.sub("_", base).strip("._")
    return cleaned or "upload"


class DocumentNotFoundError(LookupError):
    pass


class UnsupportedDocumentError(ValueError):
    pass


class LocalDocumentsService:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(config.data_dir) / "documents"
        self._root.mkdir(parents=True, exist_ok=True)
        self._store = get_sqlite_store()
        self._lock = threading.RLock()

    def create(
        self,
        files: list[UploadFile],
        conversation_id: str | None = None,
    ) -> list[dict]:
        created: list[dict] = []
        for upload in files:
            created.append(self._store_new(upload, conversation_id))
        return created

    def list(self, conversation_id: str | None = None) -> list[dict]:
        records = self._store.list_records("documents")
        seen = {item["id"] for item in records}
        for conversation in conversations_service.list():
            if conversation_id is not None and conversation["id"] != conversation_id:
                continue
            for document in conversation.get("documents") or []:
                if document["id"] not in seen:
                    records.append(document)
                    seen.add(document["id"])
        if conversation_id is not None:
            records = [
                item
                for item in records
                if item.get("conversation_id") == conversation_id
            ]
        records.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return records

    def get(self, document_id: str) -> dict:
        record = self._store.get("documents", document_id)
        if record is None:
            record = conversations_service.find_document(document_id)
        if record is None:
            raise DocumentNotFoundError(document_id)
        return record

    def get_many(self, document_ids: list[str]) -> list[dict]:
        return [self.get(document_id) for document_id in document_ids]

    def path_for(self, document_id: str) -> Path:
        record = self.get(document_id)
        path = Path(record["path"])
        if not path.is_file():
            raise DocumentNotFoundError(document_id)
        return path

    def update(self, document_id: str, upload: UploadFile) -> dict:
        existing = self.get(document_id)
        suffix = Path(upload.filename or existing["filename"]).suffix.lower()
        self._assert_suffix(suffix)
        filename = _safe_filename(upload.filename or existing["filename"])
        dest = Path(existing["path"])
        data = upload.file.read()
        dest.write_bytes(data)
        updated = {
            **existing,
            "filename": filename,
            "content_type": upload.content_type,
            "size": len(data),
            "kind": kind_for_filename(filename),
            "updated_at": _utc_now(),
        }
        logger.info("document update id=%s file=%s", document_id, filename)
        indexed = self._index(updated)
        self._persist(indexed)
        return indexed

    def delete(self, document_id: str) -> None:
        record = self.get(document_id)
        logger.info(
            "document delete id=%s file=%s conversation=%s",
            document_id,
            record.get("filename"),
            record.get("conversation_id"),
        )
        path = Path(record["path"])
        if path.exists():
            path.unlink()
        parent = path.parent
        if parent != self._root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
        self._unindex(document_id)
        with self._lock:
            self._store.delete("documents", document_id)

    def _store_new(
        self,
        upload: UploadFile,
        conversation_id: str | None = None,
    ) -> dict:
        filename = _safe_filename(upload.filename or "upload")
        suffix = Path(filename).suffix.lower()
        self._assert_suffix(suffix)
        document_id = str(uuid.uuid4())
        dest_dir = self._root / document_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        data = upload.file.read()
        dest.write_bytes(data)
        logger.info(
            "document stored id=%s file=%s bytes=%s conversation=%s path=%s",
            document_id,
            filename,
            len(data),
            conversation_id,
            dest,
        )
        now = _utc_now()
        record = {
            "id": document_id,
            "filename": filename,
            "content_type": upload.content_type,
            "size": len(data),
            "path": str(dest),
            "kind": kind_for_filename(filename),
            "conversation_id": conversation_id,
            "created_at": now,
            "updated_at": now,
        }
        return self._index(record)

    def _persist(self, record: dict) -> None:
        conversation_id = record.get("conversation_id")
        if conversation_id:
            conversations_service.replace_document(conversation_id, record)
            return
        with self._lock:
            self._store.put("documents", record)

    def _index(self, record: dict) -> dict:
        from document_chat.services.ingest import index_document

        return index_document(record)

    def _unindex(self, document_id: str) -> None:
        from document_chat.services.ingest import unindex_document

        unindex_document(document_id)

    def _assert_suffix(self, suffix: str) -> None:
        if suffix not in ALLOWED_SUFFIXES:
            allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
            raise UnsupportedDocumentError(
                f"Unsupported file type {suffix or '(none)'}. Allowed: {allowed}"
            )
