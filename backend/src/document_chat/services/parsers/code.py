from __future__ import annotations

from pathlib import Path
from typing import List

from document_chat.services.parsers.chunks import make_chunk
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
        body = "\n".join(
            f"{number}: {line}" for number, line in enumerate(lines[start:end], start=start + 1)
        )
        if any(line.strip() for line in lines[start:end]):
            chunks.append(make_chunk(record, CODE_KIND, body, location=f"L{start + 1}-{end}"))
        if end >= len(lines):
            break
        start = end - _OVERLAP
    return chunks
