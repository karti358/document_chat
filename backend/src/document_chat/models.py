from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str | None
    size: int
    conversation_id: str | None = None
    created_at: str
    updated_at: str


class DocumentListOut(BaseModel):
    documents: list[DocumentOut] = Field(default_factory=list)


class MessageOut(BaseModel):
    id: str | None = None
    role: str
    content: str
    created_at: str
    plan: dict | None = None
    trace: dict | None = None
    confidence: float | None = None
    unknown: bool | None = None


class ConversationSummaryOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    document_ids: list[str] = Field(default_factory=list)


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    document_ids: list[str] = Field(default_factory=list)
    documents: list[DocumentOut] = Field(default_factory=list)
    messages: list[MessageOut] = Field(default_factory=list)


class ConversationListOut(BaseModel):
    conversations: list[ConversationSummaryOut] = Field(default_factory=list)


class ChatRequest(BaseModel):
    prompt: str
