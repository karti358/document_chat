"""Streamlit UI entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    from streamlit.web import cli as stcli

    app = Path(__file__).with_name("app.py")
    sys.argv = [
        "streamlit",
        "run",
        str(app),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    stcli.main()
