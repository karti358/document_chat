from document_chat.services.parsers import parse_document
from document_chat.services.parsers.chunks import split_text
from document_chat.services.parsers.kinds import CODE_KIND, IMAGE_KIND, TEXT_KIND

from conftest import record_for


def _parse(corpus, name):
    path = corpus / name
    return parse_document(path, record_for(path))


def test_pdf_chunks_carry_page_numbers(corpus):
    chunks = _parse(corpus, "contract_acme.pdf")
    assert chunks
    assert all(chunk.location.startswith("p. ") for chunk in chunks)
    assert any("PO-1042" in chunk.data for chunk in chunks)


def test_markdown_chunks_carry_sections(corpus):
    chunks = _parse(corpus, "vendor_policy.md")
    locations = {chunk.location for chunk in chunks}
    assert any(location.startswith("section '") for location in locations)


def test_pptx_chunks_carry_slide_numbers(corpus):
    chunks = _parse(corpus, "q3_review.pptx")
    assert chunks[0].location == "slide 1"
    assert "Acme paid twice on PO-1042" in chunks[0].data


def test_code_chunks_are_line_numbered(corpus):
    chunks = _parse(corpus, "reconcile.py")
    assert chunks[0].kind == CODE_KIND
    assert chunks[0].location.startswith("L1-")
    assert chunks[0].data.startswith("1: ")


def test_spreadsheet_loads_table_and_text_chunk(corpus):
    from document_chat.services.index.table_store import table_store

    chunks = _parse(corpus, "q3_invoices.xlsx")
    assert chunks and chunks[0].kind == TEXT_KIND
    assert chunks[0].location.startswith("sheet '")
    tables = table_store.tables_for(["q3_invoices"])
    assert tables
    result = table_store.query_select(
        f'SELECT COUNT(*) AS n FROM "{tables[0]}" WHERE po_id = \'PO-1042\'', tables
    )
    assert "\n2\n" in result


def test_image_yields_image_and_ocr_chunks(corpus):
    chunks = _parse(corpus, "invoice_scan.png")
    assert [chunk.kind for chunk in chunks] == [IMAGE_KIND, TEXT_KIND]
    assert chunks[1].location == "OCR"


def test_split_text_overlaps_and_bounds_size():
    text = "\n".join(f"line {index} " + "x" * 50 for index in range(100))
    pieces = split_text(text, size=500, overlap=50)
    assert len(pieces) > 1
    assert all(len(piece) <= 500 for piece in pieces)
