from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from document_chat.services.index.table_store import table_store
from document_chat.services.parsers.chunks import make_chunk, split_text
from document_chat.services.parsers.kinds import TEXT_KIND, Chunk

_MAX_TEXT_ROWS = 200


def parse_csv(path: Path, record: dict) -> List[Chunk]:
    frame = pd.read_csv(path)
    table = table_store.load_frame(record["id"], record["filename"], frame)
    return _sheet_chunks(record, table, "", frame)


def parse_xlsx(path: Path, record: dict) -> List[Chunk]:
    chunks: List[Chunk] = []
    workbook = pd.ExcelFile(path)
    for sheet in workbook.sheet_names:
        frame = pd.read_excel(workbook, sheet_name=sheet)
        table = table_store.load_frame(record["id"], sheet, frame)
        chunks.extend(_sheet_chunks(record, table, sheet, frame))
    return chunks


def _sheet_chunks(record: dict, table: str, sheet: str, frame: pd.DataFrame) -> List[Chunk]:
    # Text copy is for finding the sheet by retrieval; numeric answers go through SQL.
    header = (
        f"Spreadsheet {record['filename']}"
        + (f" sheet '{sheet}'" if sheet else "")
        + f" (SQL table {table}, {len(frame)} rows)\n"
        + f"Columns: {', '.join(str(column) for column in frame.columns)}\n"
    )
    rows = frame.head(_MAX_TEXT_ROWS).to_csv(index=False)
    location = f"sheet '{sheet}'" if sheet else "table"
    return [
        make_chunk(record, TEXT_KIND, header + piece, location=location)
        for piece in split_text(rows, size=1200, overlap=0)
    ]
