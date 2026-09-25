from __future__ import annotations

import re
from pathlib import Path
from typing import List

from document_chat.services.parsers.chunks import make_chunk, split_text
from document_chat.services.parsers.kinds import TEXT_KIND, Chunk

_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def parse_text(path: Path, record: dict) -> List[Chunk]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".html":
        raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.I)
        raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.I)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = re.sub(r"\s+", " ", raw)

    sections = _sections(raw) if suffix == ".md" else [("", raw)]
    chunks: List[Chunk] = []
    for heading, body in sections:
        location = f"section '{heading}'" if heading else ""
        for piece in split_text(body):
            data = f"{heading}\n{piece}" if heading else piece
            chunks.append(make_chunk(record, TEXT_KIND, data, location=location))
    return chunks


def _sections(markdown: str) -> list[tuple[str, str]]:
    matches = list(_HEADING.finditer(markdown))
    if not matches:
        return [("", markdown)]
    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preface = markdown[: matches[0].start()].strip()
        if preface:
            sections.append(("", preface))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections.append((match.group(2).strip(), markdown[start:end]))
    return sections
