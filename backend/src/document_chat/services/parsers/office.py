from __future__ import annotations

from pathlib import Path

from docx import Document
from pptx import Presentation
from document_chat.services.parsers.kinds import TEXT_KIND, Chunk
from document_chat.services.parsers.chunks import split_text
from typing import List
import uuid


def parse_docx(path: Path, record: dict) -> List[Chunk]:
    document = Document(path)
    sections: list[tuple[str, list[str]]] = [("", [])]
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name or "") if paragraph.style is not None else ""
        if style.lower().startswith("heading"):
            sections.append((text, []))
        else:
            sections[-1][1].append(text)
    chunks: List[Chunk] = []
    for heading, lines in sections:
        body = "\n".join(lines).strip()
        if heading and not body:
            body = heading
        for piece in split_text(body):
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
    return chunks


def parse_pptx(path: Path, record: dict) -> List[Chunk]:
    presentation = Presentation(path)
    chunks: List[Chunk] = []
    for index, slide in enumerate(presentation.slides, start=1):
        lines: list[str] = []
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            text = shape.text_frame.text.strip()
            if text:
                lines.append(text)
        body = "\n".join(lines)
        for piece in split_text(body):
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
    return chunks
