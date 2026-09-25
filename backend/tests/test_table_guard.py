import pytest

from document_chat.services.index.table_store import _validated_select

ALLOWED = {"t_doc_sheet"}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM t_doc_sheet",
        "select sum(amount) from t_doc_sheet where region = 'West';",
        "WITH x AS (SELECT * FROM t_doc_sheet) SELECT COUNT(*) FROM x",
    ],
)
def test_accepts_read_only_selects(sql):
    assert _validated_select(sql, ALLOWED)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE t_doc_sheet",
        "SELECT * FROM t_doc_sheet; DELETE FROM t_doc_sheet",
        "SELECT * FROM t_other_table",
        "COPY t_doc_sheet TO 'out.csv'",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM t_doc_sheet, read_text('/etc/passwd')",
        "SELECT * FROM t_doc_sheet JOIN '/etc/hosts.csv' ON true",
        "SELECT * FROM t_doc_sheet, sqlite_scan('x.db', 'users')",
        "",
    ],
)
def test_rejects_writes_multiple_statements_and_foreign_tables(sql):
    with pytest.raises(ValueError):
        _validated_select(sql, ALLOWED)
