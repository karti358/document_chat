# Build from the repository root: docker build -f backend/Dockerfile -t document-chat .
FROM python:3.14-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/README.md ./
COPY backend/.streamlit ./.streamlit
COPY backend/src ./src
RUN uv sync --frozen --no-dev

COPY document_chat_test_set /app/document_chat_test_set

ENV PATH="/app/backend/.venv/bin:$PATH" \
    DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8501 8000

CMD ["document-chat-ui"]
