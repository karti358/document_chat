from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

TEXT_KIND = "text"
CODE_KIND = "code"
IMAGE_KIND = "image"
TABLE_KIND = "table"

TABLE_SUFFIXES = {".csv", ".xlsx", ".xls"}
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


def kind_for_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in TABLE_SUFFIXES:
        return TABLE_KIND
    if suffix in CODE_SUFFIXES:
        return CODE_KIND
    if suffix in IMAGE_SUFFIXES:
        return IMAGE_KIND
    return TEXT_KIND


class Chunk(BaseModel):
    id: str
    document_id: str
    conversation_id: str
    filename: str
    kind: Literal[TEXT_KIND, CODE_KIND, IMAGE_KIND, TABLE_KIND]
    data: Any
    location: str = ""
    ocr_text: str = ""
    caption: str = ""

    @property
    def citation(self) -> str:
        return f"{self.filename}, {self.location}" if self.location else self.filename