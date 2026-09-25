from document_chat.services.agents.citations import UNCITED_CAP, UNSUPPORTED_CAP, check, extract

FILES = {"vendor_policy.md", "contract_acme.pdf", "q3_invoices.xlsx"}
EVIDENCE = [
    "[vendor_policy.md, section 'Commercial Terms'] Refunds within 30 days.",
    "[q3_invoices.xlsx, table t_q3]\nrows: 1",
]


def test_extract_ignores_non_file_brackets():
    text = "rows[0] and [vendor_policy.md, p. 1]; see [note]"
    assert extract(text, FILES) == ["vendor_policy.md, p. 1"]


def test_supported_citations_keep_confidence():
    answer = "30 days [vendor_policy.md, section 'Commercial Terms']; total [q3_invoices.xlsx]"
    citations, confidence = check(answer, EVIDENCE, FILES, 0.9, False)
    assert all(item["supported"] for item in citations)
    assert confidence == 0.9


def test_citation_never_returned_by_tools_is_flagged():
    citations, confidence = check("Signed [contract_acme.pdf, p. 1]", EVIDENCE, FILES, 0.9, False)
    assert citations == [{"citation": "contract_acme.pdf, p. 1", "supported": False}]
    assert confidence == UNSUPPORTED_CAP


def test_uncited_answer_is_capped():
    _, confidence = check("The window is 30 days.", EVIDENCE, FILES, 0.9, False)
    assert confidence == UNCITED_CAP


def test_unknown_answers_are_not_capped():
    _, confidence = check("I don't know.", EVIDENCE, FILES, 0.2, True)
    assert confidence == 0.2
