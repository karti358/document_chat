from __future__ import annotations

from pathlib import Path

from document_chat.services.parsers.code import parse_code
from document_chat.services.parsers.images import parse_image
from document_chat.services.parsers.office import parse_docx, parse_pptx
from document_chat.services.parsers.pdf import parse_pdf
from document_chat.services.parsers.tables import parse_csv, parse_xlsx
from document_chat.services.parsers.text import parse_text
from document_chat.logging import get_logger
from document_chat.services.parsers.kinds import Chunk

logger = get_logger("document_chat.parsers")

CODE_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_SUFFIXES = {".txt", ".md", ".html"}


def parse_document(path: Path, record: dict) -> list[Chunk]:
    suffix = path.suffix.lower()
    logger.info(
        "parse start id=%s file=%s suffix=%s",
        record.get("id"),
        record.get("filename"),
        suffix,
    )
    if suffix == ".pdf":
        chunks = parse_pdf(path, record)
    elif suffix == ".docx":
        chunks = parse_docx(path, record)
    elif suffix == ".pptx":
        chunks = parse_pptx(path, record)
    elif suffix == ".csv":
        chunks = parse_csv(path, record)
    elif suffix == ".xlsx":
        chunks = parse_xlsx(path, record)
    elif suffix in IMAGE_SUFFIXES:
        chunks = parse_image(path, record)
    elif suffix in CODE_SUFFIXES:
        chunks = parse_code(path, record)
    elif suffix in TEXT_SUFFIXES:
        chunks = parse_text(path, record)
    else:
        raise ValueError(f"No parser for {suffix or 'unknown type'}")
    logger.info(
        "parse done id=%s file=%s chunks=%s",
        record.get("id"),
        record.get("filename"),
        len(chunks),
    )
    return chunks
