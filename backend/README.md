# document_chat backend

Setup, configuration and run instructions are in the [root README](../README.md).
Design notes are in [docs/architecture.md](docs/architecture.md).

```bash
uv sync
cp .env.example .env      # then set API_KEY / MODEL
uv run document-chat-ui   # Streamlit UI on :8501
uv run document-chat      # FastAPI on :8000 (optional)
```
