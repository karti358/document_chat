from __future__ import annotations

from pathlib import Path
from typing import List
import uuid
from document_chat.services.parsers.kinds import CODE_KIND, Chunk

_WINDOW = 80
_OVERLAP = 10

def parse_code(path: Path, record: dict) -> List[Chunk]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    if not lines:
        return []
    chunks: List[Chunk] = []
    start = 0
    while start < len(lines):
        end = min(len(lines), start + _WINDOW)
        body = "\n".join(lines[start:end]).strip()
        if body:
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    document_id=record["id"],
                    conversation_id=record.get("conversation_id"),
                    filename=record["filename"],
                    kind=CODE_KIND,
                    data=body,
                )
            )
        if end >= len(lines):
            break
        start = end - _OVERLAP
    return chunks
