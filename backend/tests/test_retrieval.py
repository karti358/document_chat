import pytest

from document_chat.services.index.retrieval import _bm25, _rrf, _tokenize, search_chunks
from document_chat.services.ingest import index_document
from document_chat.services.parsers.kinds import TEXT_KIND, Chunk

from conftest import record_for

FILES = ["vendor_policy.md", "contract_acme.pdf", "q3_review.pptx", "reconcile.py", "q3_summary.csv"]


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(id=chunk_id, document_id="d", conversation_id="", filename="f", kind=TEXT_KIND, data=text)


def test_tokenize_keeps_hyphenated_ids_and_parts():
    tokens = _tokenize("Paid twice on PO-1042.")
    assert "po-1042" in tokens and "po" in tokens and "1042" in tokens


def test_bm25_ranks_exact_id_first():
    chunks = [_chunk("a", "general vendor terms"), _chunk("b", "invoice for PO-1042 and PO-2000")]
    assert [chunk.id for chunk in _bm25("PO-1042", chunks)] == ["b"]


def test_rrf_rewards_agreement():
    a, b, c = _chunk("a", ""), _chunk("b", ""), _chunk("c", "")
    fused = _rrf([a, b], [b, c], limit=3)
    assert fused[0].id == "b"


@pytest.fixture(scope="module")
def indexed(corpus):
    ids = []
    for name in FILES:
        path = corpus / name
        index_document(record_for(path))
        ids.append(path.stem)
    return ids


@pytest.mark.parametrize(
    "query, expected",
    [
        ("refund window", "vendor_policy.md"),
        ("duplicate po_id detection function", "reconcile.py"),
        ("Acme paid twice", "q3_review.pptx"),
        ("West region total", "q3_summary.csv"),
    ],
)
def test_hybrid_search_finds_source_in_top_three(indexed, query, expected):
    hits = search_chunks(query, indexed, {TEXT_KIND, "code"})
    assert expected in [hit.filename for hit in hits[:3]]
