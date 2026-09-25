from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from document_chat.logging import get_logger
from document_chat.models import DocumentListOut, DocumentOut
from document_chat.services.documents import (
    DocumentNotFoundError,
    UnsupportedDocumentError,
    documents_service,
)

logger = get_logger("document_chat.api")

router = APIRouter(prefix="/documents", tags=["documents"])


def _to_out(record: dict) -> DocumentOut:
    return DocumentOut(
        id=record["id"],
        filename=record["filename"],
        content_type=record.get("content_type"),
        size=record["size"],
        conversation_id=record.get("conversation_id"),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


@router.get("", response_model=DocumentListOut)
def list_documents() -> DocumentListOut:
    return DocumentListOut(
        documents=[_to_out(item) for item in documents_service.list()]
    )


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str) -> DocumentOut:
    try:
        return _to_out(documents_service.get(document_id))
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc


@router.get("/{document_id}/file")
def download_document(document_id: str) -> FileResponse:
    try:
        record = documents_service.get(document_id)
        path = documents_service.path_for(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    return FileResponse(
        path,
        filename=record["filename"],
        media_type=record.get("content_type") or "application/octet-stream",
    )


@router.put("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: str,
    document: UploadFile = File(...),
) -> DocumentOut:
    try:
        logger.info("document replace id=%s file=%s", document_id, document.filename)
        updated = documents_service.update(document_id, document)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _to_out(updated)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str) -> None:
    try:
        logger.info("document delete id=%s", document_id)
        documents_service.delete(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
