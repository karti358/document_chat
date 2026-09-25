import asyncio
import time
from collections.abc import AsyncIterator

from document_chat.logging import get_logger, preview
from document_chat.services.agents.orchestrator import (
    Document,
    _stream_events,
    _stream_queue,
    emit,
    prior_plans,
    run_turn,
)
from document_chat.services.conversations import LocalConversationsService
from document_chat.services.documents import LocalDocumentsService
from document_chat.services.parsers.kinds import kind_for_filename

logger = get_logger("document_chat.chat")


class ChatService:
    def __init__(
        self,
        documents_service: LocalDocumentsService,
        conversations_service: LocalConversationsService,
    ) -> None:
        self.documents_service = documents_service
        self.conversations_service = conversations_service

    async def stream(self, conversation_id: str, prompt: str) -> AsyncIterator[dict]:
        if not prompt.strip():
            raise ValueError("Please provide a prompt")
        conversation = self.conversations_service.get(conversation_id)
        stored_documents = list(conversation.get("documents") or [])
        if not stored_documents:
            stored_documents = self.documents_service.get_many(
                list(conversation.get("document_ids") or [])
            )
        documents = [
            Document(
                id=item["id"],
                filename=item["filename"],
                path=item["path"],
                kind=item.get("kind") or kind_for_filename(item["filename"]),
            )
            for item in stored_documents
        ]
        plans = prior_plans(conversation.get("messages") or [])

        queue: asyncio.Queue = asyncio.Queue()
        collected: list[dict] = []
        started = time.perf_counter()

        async def run() -> None:
            # Set inside the task: the generator may be closed from a different context.
            _stream_queue.set(queue)
            _stream_events.set(collected)
            try:
                await emit({"type": "agent_start", "agent": "orchestrator"})
                result = await run_turn(prompt.strip(), documents, plans)
                await emit(
                    {
                        "type": "agent_done",
                        "agent": "orchestrator",
                        "answer": result["content"],
                        "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    }
                )
                record = self.conversations_service.append_turn(
                    conversation_id,
                    prompt.strip(),
                    {
                        "content": result["content"],
                        "plan": result.get("plan"),
                        "trace": {"events": list(collected)},
                        "confidence": result.get("confidence"),
                        "unknown": result.get("unknown"),
                        "citations": result.get("citations"),
                    },
                    orchestrator_state={
                        "documents": [document.model_dump() for document in documents],
                        "messages": [],
                        "last_plan": result.get("plan"),
                    },
                )
                await queue.put({"type": "done", "record": record})
            except Exception as exc:
                logger.exception("orchestrator failed conversation=%s", conversation_id)
                await queue.put({"type": "error", "detail": str(exc)})
            finally:
                await queue.put(None)

        logger.info(
            "orchestrator stream start conversation=%s prompt=%s documents=%s prior_plans=%s",
            conversation_id,
            preview(prompt, 300),
            [(item.id, item.filename, item.kind) for item in documents],
            len(plans),
        )
        task = asyncio.create_task(run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            if not task.done():
                task.cancel()
