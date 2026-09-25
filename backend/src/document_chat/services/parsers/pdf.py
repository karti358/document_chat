from __future__ import annotations

from pathlib import Path

import pymupdf
from document_chat.services.parsers.kinds import TEXT_KIND, Chunk
from document_chat.services.parsers.chunks import split_text
from typing import List
import uuid


def parse_pdf(path: Path, record: dict) -> List[Chunk]:
    chunks: List[Chunk] = []
    document = pymupdf.open(path)
    for page in document:
        text = page.get_text("text") or ""
        for piece in split_text(text):
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    document_id=record["id"],
                    conversation_id=record.get("conversation_id"),
                    filename=record["filename"],
                    kind=TEXT_KIND,
                    data=piece,
                )
            )
    document.close()
    return chunks
