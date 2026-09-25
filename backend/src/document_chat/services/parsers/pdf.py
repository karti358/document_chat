from __future__ import annotations

from pathlib import Path
from typing import List

import pymupdf

from document_chat.services.parsers.chunks import make_chunk, split_text
from document_chat.services.parsers.kinds import TEXT_KIND, Chunk


def parse_pdf(path: Path, record: dict) -> List[Chunk]:
    chunks: List[Chunk] = []
    with pymupdf.open(path) as document:
        for page in document:
            text = page.get_text("text") or ""
            for piece in split_text(text):
                chunks.append(
                    make_chunk(record, TEXT_KIND, piece, location=f"p. {page.number + 1}")
                )
    return chunks
