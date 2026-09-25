from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from document_chat.db.sqlite_store import get_sqlite_store
from document_chat.logging import get_logger

logger = get_logger("document_chat.conversations")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationNotFoundError(LookupError):
    pass


class LocalConversationsService:
    def __init__(self) -> None:
        self._store = get_sqlite_store()
        self._lock = threading.RLock()

    def create(self, title: str = "New chat") -> dict:
        now = _utc_now()
        record = {
            "id": str(uuid.uuid4()),
            "title": title,
            "document_ids": [],
            "documents": [],
            "messages": [],
            "orchestrator_state": {"documents": [], "messages": []},
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._store.put("conversations", record)
        logger.info("conversation created id=%s", record["id"])
        return record

    def list(self) -> list[dict]:
        records = self._store.list_records("conversations")
        records.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return records

    def get(self, conversation_id: str) -> dict:
        record = self._store.get("conversations", conversation_id)
        if record is None:
            raise ConversationNotFoundError(conversation_id)
        messages = list(record.get("messages") or [])
        changed = False
        for index, message in enumerate(messages):
            if not message.get("id"):
                messages[index] = {**message, "id": str(uuid.uuid4())}
                changed = True
        if not changed:
            return record
        updated = {**record, "messages": messages}
        with self._lock:
            self._store.put("conversations", updated)
        return updated

    def add_documents(self, conversation_id: str, documents: list[dict]) -> dict:
        with self._lock:
            record = self.get(conversation_id)
            stored = list(record.get("documents") or [])
            ids = list(record.get("document_ids") or [])
            known = {item["id"] for item in stored}
            for document in documents:
                if document["id"] not in known:
                    stored.append(document)
                    known.add(document["id"])
                if document["id"] not in ids:
                    ids.append(document["id"])
            logger.info(
                "conversation documents added id=%s files=%s",
                conversation_id,
                [item.get("filename") for item in documents],
            )
            return self._update(
                conversation_id,
                {
                    "documents": stored,
                    "document_ids": ids,
                    "updated_at": _utc_now(),
                },
            )

    def replace_document(self, conversation_id: str, document: dict) -> dict:
        with self._lock:
            record = self.get(conversation_id)
            stored = [
                document if item.get("id") == document["id"] else item
                for item in (record.get("documents") or [])
            ]
            if not any(item.get("id") == document["id"] for item in stored):
                stored.append(document)
            ids = list(record.get("document_ids") or [])
            if document["id"] not in ids:
                ids.append(document["id"])
            return self._update(
                conversation_id,
                {
                    "documents": stored,
                    "document_ids": ids,
                    "updated_at": _utc_now(),
                },
            )

    def find_document(self, document_id: str) -> dict | None:
        for record in self.list():
            for document in record.get("documents") or []:
                if document.get("id") == document_id:
                    return document
        return None

    def remove_document_id(self, conversation_id: str, document_id: str) -> dict:
        record = self.get(conversation_id)
        ids = [
            item
            for item in (record.get("document_ids") or [])
            if item != document_id
        ]
        documents = [
            item
            for item in (record.get("documents") or [])
            if item.get("id") != document_id
        ]
        logger.info(
            "conversation document removed id=%s document=%s",
            conversation_id,
            document_id,
        )
        return self._update(
            conversation_id,
            {
                "document_ids": ids,
                "documents": documents,
                "updated_at": _utc_now(),
            },
        )

    def append_turn(
        self,
        conversation_id: str,
        prompt: str,
        assistant: dict,
        orchestrator_state: dict | None = None,
    ) -> dict:
        record = self.get(conversation_id)
        now = _utc_now()
        messages = list(record.get("messages") or [])
        messages.append(
            {
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": prompt,
                "created_at": now,
            }
        )
        messages.append(
            {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": assistant.get("content") or "",
                "created_at": now,
                "plan": assistant.get("plan"),
                "trace": assistant.get("trace"),
                "confidence": assistant.get("confidence"),
                "unknown": assistant.get("unknown"),
            }
        )
        updates: dict = {
            "messages": messages,
            "updated_at": now,
        }
        if orchestrator_state is not None:
            updates["orchestrator_state"] = orchestrator_state
        if record.get("title") in (None, "", "New chat"):
            updates["title"] = prompt.strip()[:60] or "New chat"
        state = orchestrator_state or {}
        logger.info(
            "conversation turn stored id=%s messages=%s orchestrator_messages=%s documents=%s",
            conversation_id,
            len(messages),
            len(state.get("messages") or []),
            len(state.get("documents") or []),
        )
        return self._update(conversation_id, updates)

    def delete_message(self, conversation_id: str, message_id: str) -> dict:
        record = self.get(conversation_id)
        messages = list(record.get("messages") or [])
        index = next(
            (i for i, item in enumerate(messages) if item.get("id") == message_id),
            None,
        )
        if index is None:
            raise LookupError(message_id)
        remove = {index}
        current = messages[index]
        if current.get("role") == "user" and index + 1 < len(messages):
            following = messages[index + 1]
            if following.get("role") == "assistant":
                remove.add(index + 1)
        elif current.get("role") == "assistant" and index > 0:
            previous = messages[index - 1]
            if previous.get("role") == "user":
                remove.add(index - 1)
        kept = [item for i, item in enumerate(messages) if i not in remove]
        state = dict(record.get("orchestrator_state") or {})
        state["messages"] = []
        logger.info(
            "conversation message deleted id=%s message=%s remaining=%s",
            conversation_id,
            message_id,
            len(kept),
        )
        return self._update(
            conversation_id,
            {
                "messages": kept,
                "orchestrator_state": state,
                "updated_at": _utc_now(),
            },
        )

    def delete(self, conversation_id: str) -> dict:
        record = self.get(conversation_id)
        with self._lock:
            self._store.delete("conversations", conversation_id)
        logger.info(
            "conversation deleted id=%s documents=%s",
            conversation_id,
            record.get("document_ids") or [],
        )
        return record

    def _update(self, conversation_id: str, updates: dict) -> dict:
        record = self.get(conversation_id)
        updated = {**record, **updates}
        with self._lock:
            self._store.put("conversations", updated)
        return updated
