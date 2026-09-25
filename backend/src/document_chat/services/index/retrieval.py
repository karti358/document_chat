from __future__ import annotations

import math
import re
from collections import Counter

from document_chat.logging import get_logger, preview
from document_chat.services.index.chroma_store import chroma_store
from document_chat.services.parsers.kinds import Chunk

logger = get_logger("document_chat.retrieval")

_TOKEN = re.compile(r"[a-z0-9_]+(?:-[a-z0-9_]+)*")
_RRF_K = 60


def search_chunks(
    query: str,
    document_ids: list[str],
    kinds: set[str],
    limit: int = 6,
) -> list[Chunk]:
    """Hybrid search: Chroma vectors and BM25 over the same chunks, merged with RRF."""
    if not query.strip() or not document_ids:
        return []
    corpus = chroma_store.fetch(document_ids, kinds)
    if not corpus:
        return []
    depth = max(limit * 3, 12)
    vector_hits = chroma_store.query(query, document_ids, limit=depth, kinds=kinds)
    lexical_hits = _bm25(query, corpus)[:depth]
    fused = _rrf(vector_hits, lexical_hits, limit)
    logger.info(
        "hybrid search corpus=%s vector=%s lexical=%s fused=%s query=%s",
        len(corpus),
        len(vector_hits),
        len(lexical_hits),
        [hit.citation for hit in fused],
        preview(query, 200),
    )
    return fused


def _tokenize(text: str) -> list[str]:
    tokens = _TOKEN.findall(text.lower())
    # Keep hyphenated IDs (po-1042) whole and also index their parts.
    parts = [part for token in tokens if "-" in token for part in token.split("-")]
    return tokens + parts


def _bm25(query: str, chunks: list[Chunk]) -> list[Chunk]:
    query_terms = set(_tokenize(query))
    if not query_terms:
        return []
    docs = [_tokenize(str(chunk.data)) for chunk in chunks]
    avg = sum(len(tokens) for tokens in docs) / max(len(docs), 1)
    df: Counter[str] = Counter()
    for tokens in docs:
        df.update(set(tokens))
    total = len(docs)
    scored: list[tuple[float, Chunk]] = []
    for chunk, tokens in zip(chunks, docs):
        counts = Counter(tokens)
        score = 0.0
        for term in query_terms:
            if term not in counts:
                continue
            idf = math.log(1 + (total - df[term] + 0.5) / (df[term] + 0.5))
            freq = counts[term]
            denom = freq + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / max(avg, 1))
            score += idf * (freq * 2.5) / denom
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored]


def _rrf(vector_hits: list[Chunk], lexical_hits: list[Chunk], limit: int) -> list[Chunk]:
    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    for hits in (vector_hits, lexical_hits):
        for rank, hit in enumerate(hits):
            scores[hit.id] = scores.get(hit.id, 0) + 1 / (_RRF_K + rank + 1)
            chunks.setdefault(hit.id, hit)
    ordered = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [chunks[chunk_id] for chunk_id in ordered[:limit]]
