from __future__ import annotations

from pathlib import Path
from typing import List
import uuid

import pytesseract
from PIL import Image

from document_chat.services.parsers.kinds import IMAGE_KIND, TEXT_KIND, Chunk


def parse_image(path: Path, record: dict) -> List[Chunk]:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    try:
        ocr_text = pytesseract.image_to_string(image).strip()
    except Exception:
        ocr_text = ""
    caption = (
        f"Image file {record['filename']} ({width}x{height}px). "
        + (
            f"Visible text preview: {ocr_text[:240]}"
            if ocr_text
            else "No OCR text detected."
        )
    )
    conversation_id = record.get("conversation_id") or ""
    image_chunk = Chunk(
        id=str(uuid.uuid4()),
        document_id=record["id"],
        conversation_id=conversation_id,
        filename=record["filename"],
        kind=IMAGE_KIND,
        data=str(path),
        ocr_text=ocr_text,
        caption=caption,
    )
    text_chunk = Chunk(
        id=str(uuid.uuid4()),
        document_id=record["id"],
        conversation_id=conversation_id,
        filename=record["filename"],
        kind=TEXT_KIND,
        data=f"{caption}\n\nOCR:\n{ocr_text or '(empty)'}",
        ocr_text=ocr_text,
        caption=caption,
    )
    return [image_chunk, text_chunk]
