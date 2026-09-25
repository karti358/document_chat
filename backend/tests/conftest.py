import os
import tempfile
from pathlib import Path

import pytest

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="document_chat_tests_")
os.environ.setdefault("MODEL", "test-model")
os.environ.setdefault("LOG_LEVEL", "WARNING")

CORPUS = Path(__file__).resolve().parents[2] / "document_chat_test_set"


@pytest.fixture(scope="session")
def corpus() -> Path:
    return CORPUS


def record_for(path: Path) -> dict:
    return {"id": path.stem, "filename": path.name, "path": str(path), "conversation_id": "test"}
