from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from .kinds import Chunk

def split_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    cleaned = text.replace("\x00", "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        if end < len(cleaned):
            break_at = cleaned.rfind("\n", start, end)
            if break_at > start + size // 2:
                end = break_at
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks