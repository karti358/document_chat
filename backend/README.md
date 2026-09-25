# document_chat

FastAPI API plus a Streamlit UI. Both talk to the same local services (SQLite, Chroma, DuckDB).

## Setup

```bash
cd backend
uv sync
```

## API

```bash
uv run document-chat
```

API: `http://127.0.0.1:8000` (docs at `/docs`).

## UI (Streamlit)

```bash
uv run document-chat-ui
```

UI: `http://127.0.0.1:8501`.

Metadata (documents + conversations) is stored in SQLite at `data/document_chat.sqlite`.
Each table has two columns: `id` and `json` (the full record serialized as text).
Uploaded file bytes stay on disk under `data/documents/`.

Optional env: `SQLITE_PATH` (via `sqlite_path` in settings) to override the DB file.
If you change the schema, delete the sqlite file and start fresh.

PDF parsing later uses Docling:

```bash
uv pip install docling --extra-index-url https://download.pytorch.org/whl/cpu
```
