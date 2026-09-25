from __future__ import annotations

from pathlib import Path

import pandas as pd
from document_chat.services.index.table_store import table_store

def parse_csv(path: Path, record: dict) -> None:
    frame = pd.read_csv(path)
    table_store.load_frame(record["id"], record["filename"], frame)

def parse_xlsx(path: Path, record: dict) -> None:
    workbook = pd.ExcelFile(path)
    for sheet in workbook.sheet_names:
        frame = pd.read_excel(workbook, sheet_name=sheet)
        table_store.load_frame(record["id"], sheet, frame)
