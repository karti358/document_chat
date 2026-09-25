from document_chat.services.documents.local import (
    DocumentNotFoundError,
    LocalDocumentsService,
    UnsupportedDocumentError,
)

documents_service = LocalDocumentsService()

__all__ = [
    "DocumentNotFoundError",
    "LocalDocumentsService",
    "UnsupportedDocumentError",
    "documents_service",
]
