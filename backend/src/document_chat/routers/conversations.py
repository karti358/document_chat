from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
import json

from document_chat.logging import get_logger, preview
from document_chat.models import (
    ChatRequest,
    ConversationListOut,
    ConversationOut,
    ConversationSummaryOut,
    DocumentListOut,
    DocumentOut,
    MessageOut,
)
from document_chat.services.chat import ChatService
from document_chat.services.conversations import (
    ConversationNotFoundError,
    conversations_service,
)
from document_chat.services.documents import (
    DocumentNotFoundError,
    UnsupportedDocumentError,
    documents_service,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])
chat_service = ChatService(documents_service, conversations_service)
logger = get_logger("document_chat.api")


def _document_out(record: dict) -> DocumentOut:
    return DocumentOut(
        id=record["id"],
        filename=record["filename"],
        content_type=record.get("content_type"),
        size=record["size"],
        conversation_id=record.get("conversation_id"),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


def _conversation_out(record: dict) -> ConversationOut:
    embedded = record.get("documents") or []
    if embedded:
        documents = [_document_out(item) for item in embedded]
    else:
        documents = []
        for document_id in record.get("document_ids") or []:
            try:
                documents.append(_document_out(documents_service.get(document_id)))
            except DocumentNotFoundError:
                continue
    return ConversationOut(
        id=record["id"],
        title=record["title"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        document_ids=record.get("document_ids") or [],
        documents=documents,
        messages=[
            MessageOut(
                id=item.get("id"),
                role=item["role"],
                content=item.get("content") or "",
                created_at=item["created_at"],
                plan=item.get("plan"),
                trace=item.get("trace"),
                confidence=item.get("confidence"),
                unknown=item.get("unknown"),
            )
            for item in record.get("messages") or []
        ],
    )


def _summary_out(record: dict) -> ConversationSummaryOut:
    return ConversationSummaryOut(
        id=record["id"],
        title=record["title"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        document_ids=record.get("document_ids") or [],
    )


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation() -> ConversationOut:
    return _conversation_out(conversations_service.create())


@router.get("", response_model=ConversationListOut)
def list_conversations() -> ConversationListOut:
    return ConversationListOut(
        conversations=[_summary_out(item) for item in conversations_service.list()]
    )


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: str) -> ConversationOut:
    try:
        return _conversation_out(conversations_service.get(conversation_id))
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from exc


@router.delete(
    "/{conversation_id}/messages/{message_id}",
    response_model=ConversationOut,
)
def delete_conversation_message(
    conversation_id: str,
    message_id: str,
) -> ConversationOut:
    try:
        record = conversations_service.delete_message(conversation_id, message_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        ) from exc
    return _conversation_out(record)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str) -> None:
    try:
        record = conversations_service.get(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from exc
    for document_id in record.get("document_ids") or []:
        try:
            documents_service.delete(document_id)
        except DocumentNotFoundError:
            continue
    conversations_service.delete(conversation_id)


@router.post(
    "/{conversation_id}/documents",
    response_model=DocumentListOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_conversation_documents(
    conversation_id: str,
    documents: list[UploadFile] = File(...),
) -> DocumentListOut:
    try:
        conversations_service.get(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from exc
    
    logger.info(
        "upload start conversation=%s files=%s",
        conversation_id,
        [item.filename for item in documents],
    )
    try:
        created = documents_service.create(documents, conversation_id)
    except UnsupportedDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    
    conversations_service.add_documents(conversation_id, created)
    logger.info(
        "upload done conversation=%s documents=%s",
        conversation_id,
        [(item["id"], item["filename"]) for item in created],
    )
    return DocumentListOut(documents=[_document_out(item) for item in created])


@router.delete(
    "/{conversation_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation_document(conversation_id: str, document_id: str) -> None:
    try:
        record = documents_service.get(document_id)
        conversations_service.get(conversation_id)
    except (DocumentNotFoundError, ConversationNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    if record.get("conversation_id") != conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    documents_service.delete(document_id)
    conversations_service.remove_document_id(conversation_id, document_id)


@router.get("/{conversation_id}/documents/{document_id}/file")
async def download_conversation_document(
    conversation_id: str,
    document_id: str,
) -> FileResponse:
    try:
        record = documents_service.get(document_id)
        path = documents_service.path_for(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    if record.get("conversation_id") != conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return FileResponse(
        path,
        filename=record["filename"],
        media_type=record.get("content_type") or "application/octet-stream",
    )


@router.post("/{conversation_id}/chat")
async def chat(conversation_id: str, body: ChatRequest) -> StreamingResponse:
    if not body.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a prompt",
        )
    try:
        conversations_service.get(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from exc
    logger.info(
        "chat stream conversation=%s prompt=%s",
        conversation_id,
        preview(body.prompt, 300),
    )

    async def events():
        try:
            async for event in chat_service.stream(conversation_id, body.prompt):
                if event.get("type") == "done":
                    payload = {
                        "type": "done",
                        "conversation": _conversation_out(event["record"]).model_dump(),
                    }
                else:
                    payload = event
                yield f"data: {json.dumps(payload, default=str)}\n\n"
        except Exception as exc:
            logger.exception("chat stream failed conversation=%s", conversation_id)
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
