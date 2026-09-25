from document_chat.services.conversations.local import (
    ConversationNotFoundError,
    LocalConversationsService,
)

conversations_service = LocalConversationsService()

__all__ = [
    "ConversationNotFoundError",
    "LocalConversationsService",
    "conversations_service",
]
