from __future__ import annotations

from pathlib import Path
from typing import List

import pytesseract
from PIL import Image

from document_chat.logging import get_logger
from document_chat.services.parsers.chunks import make_chunk
from document_chat.services.parsers.kinds import IMAGE_KIND, TEXT_KIND, Chunk

logger = get_logger("document_chat.parsers.images")


def parse_image(path: Path, record: dict) -> List[Chunk]:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    try:
        ocr_text = pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError:
        logger.warning("tesseract binary not found; OCR skipped file=%s", record.get("filename"))
        ocr_text = ""
    except Exception:
        logger.exception("ocr failed file=%s", record.get("filename"))
        ocr_text = ""
    caption = (
        f"Image file {record['filename']} ({width}x{height}px). "
        + (
            f"Visible text preview: {ocr_text[:240]}"
            if ocr_text
            else "No OCR text detected."
        )
    )
    image_chunk = make_chunk(
        record, IMAGE_KIND, str(path), location="image", ocr_text=ocr_text, caption=caption
    )
    text_chunk = make_chunk(
        record,
        TEXT_KIND,
        f"{caption}\n\nOCR:\n{ocr_text or '(empty)'}",
        location="OCR",
        ocr_text=ocr_text,
        caption=caption,
    )
    return [image_chunk, text_chunk]
