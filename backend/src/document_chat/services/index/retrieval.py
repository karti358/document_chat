from __future__ import annotations

import math
import re
from collections import Counter

from document_chat.services.index.chroma_store import chroma_store

_TOKEN = re.compile(r"[a-z0-9_]+")
_RRF_K = 60


def search_chunks(
    query: str,
    document_ids: list[str],
    kinds: set[str],
    limit: int = 6,
) -> list[dict]:
    if not query.strip() or not document_ids:
        return []
    corpus = chroma_store.fetch(document_ids, kinds)
    if not corpus:
        return []
    vector_hits = chroma_store.query(query, document_ids, limit=max(limit * 3, 12), kinds=kinds)
    lexical_hits = _bm25(query, corpus)[: max(limit * 3, 12)]
    return _rrf(vector_hits, lexical_hits, limit)


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _bm25(query: str, chunks: list[dict]) -> list[dict]:
    query_terms = _tokenize(query)
    if not query_terms:
        return []
    docs = [_tokenize(chunk.get("text") or "") for chunk in chunks]
    avg = sum(len(tokens) for tokens in docs) / max(len(docs), 1)
    df: Counter[str] = Counter()
    for tokens in docs:
        df.update(set(tokens))
    total = len(docs)
    scored: list[tuple[float, dict]] = []
    for chunk, tokens in zip(chunks, docs):
        counts = Counter(tokens)
        score = 0.0
        for term in query_terms:
            if term not in counts or df[term] == 0:
                continue
            idf = math.log(1 + (total - df[term] + 0.5) / (df[term] + 0.5))
            freq = counts[term]
            denom = freq + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / max(avg, 1))
            score += idf * (freq * 2.5) / denom
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored]


def _rrf(vector_hits: list[dict], lexical_hits: list[dict], limit: int) -> list[dict]:
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}
    for rank, hit in enumerate(vector_hits):
        chunk_id = str(hit.get("id"))
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (_RRF_K + rank + 1)
        chunks[chunk_id] = hit
    for rank, hit in enumerate(lexical_hits):
        chunk_id = str(hit.get("id"))
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (_RRF_K + rank + 1)
        chunks.setdefault(chunk_id, hit)
    ordered = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [chunks[chunk_id] for chunk_id in ordered[:limit]]
