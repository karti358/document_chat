from __future__ import annotations

import re

_BRACKET = re.compile(r"\[([^\[\]\n]{3,200})\]")

UNSUPPORTED_CAP = 0.4
UNCITED_CAP = 0.5


def _normalize(citation: str) -> str:
    return re.sub(r"\s+", " ", citation.strip().strip("`").lower())


def _filename(citation: str) -> str:
    return _normalize(citation.split(",", 1)[0])


def extract(text: str, filenames: set[str]) -> list[str]:
    """Bracketed citations whose first part is one of the uploaded filenames."""
    known = {name.lower() for name in filenames}
    seen: list[str] = []
    for match in _BRACKET.findall(text or ""):
        for part in match.split(";"):
            part = part.strip()
            if _filename(part) in known and part not in seen:
                seen.append(part)
    return seen


def check(
    answer: str,
    evidence: list[str],
    filenames: set[str],
    confidence: float | None,
    unknown: bool,
) -> tuple[list[dict], float | None]:
    """Mark each answer citation as supported if the tools actually returned it.

    A citation is supported when the same [filename, location] appeared in a tool
    result, or when it names only a file that some tool result came from.
    """
    returned = {_normalize(item) for text in evidence for item in extract(text, filenames)}
    returned_files = {_filename(item) for item in returned}
    citations = []
    for citation in extract(answer, filenames):
        normalized = _normalize(citation)
        if "," in citation:
            supported = normalized in returned
        else:
            supported = normalized in returned_files
        citations.append({"citation": citation, "supported": supported})

    if confidence is not None:
        confidence = max(0.0, min(1.0, float(confidence)))
    if not unknown:
        if any(not item["supported"] for item in citations):
            confidence = min(confidence if confidence is not None else 1.0, UNSUPPORTED_CAP)
        elif not citations:
            confidence = min(confidence if confidence is not None else 1.0, UNCITED_CAP)
    return citations, confidence
