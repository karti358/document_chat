import pytest

from document_chat.eval import grade, key_found, parse_questions


def test_question_bank_parses(corpus):
    questions = parse_questions(corpus / "document_chat_questions.md")
    assert len(questions) >= 100
    first = questions[0]
    assert first["id"] == 1 and first["sources"] == ["vendor_policy.md"]
    assert first["keys"]


@pytest.mark.parametrize(
    "key, answer, expected",
    [
        ("$12,500.00", "The amount is 12,500 USD", True),
        ("25,000", "The total is 2,500", False),
        ("August 4, 2024", "Due on 2024-08-04", True),
        ("PO-1042", "It is po-1042.", True),
        ("No", "No. There is no payment record.", True),
        ("No", "Yes, but there is no record.", False),
        ("30 days from the invoice date", "within 30 days of the invoice date", True),
    ],
)
def test_key_found(key, answer, expected):
    assert key_found(key, answer) is expected


def test_grade_source_recall():
    question = {"keys": ["Net-30"], "sources": ["vendor_policy.md", "contract_acme.pdf"]}
    result = {
        "content": "Net-30 [vendor_policy.md, section 'Terms']",
        "citations": [{"citation": "vendor_policy.md, section 'Terms'", "supported": True}],
    }
    graded = grade(question, result)
    assert graded["answer_ok"] and graded["source_recall"] == 0.5
