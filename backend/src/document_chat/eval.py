"""Run the question bank in document_chat_test_set/ against the agent pipeline.

Grading is deterministic (no judge LLM): each **bold** value in the expected
answer must appear in the system's answer, numbers compared by value and dates
in any common format. Source recall is the share of expected files the answer
cited. Results go to <data_dir>/eval/report.md and results.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

_QUESTION = re.compile(r"^## Q(\d+)\. (.+)$", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_SOURCES = re.compile(r"^\*\*Sources?:\*\*\s*(.+)$", re.MULTILINE)
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_STOPWORDS = {"from", "with", "that", "this", "than", "into", "their", "there", "which", "under"}
_DATE_FORMATS = ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%d %B %Y", "%b %d, %Y")


def parse_questions(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    matches = list(_QUESTION.finditer(text))
    questions = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        expected = body.split("**Expected answer:**", 1)[-1]
        expected = re.split(r"^\*\*(?:Sources?|Tests):\*\*", expected, flags=re.MULTILINE)[0]
        expected = expected.split("\n---", 1)[0].strip()
        sources_match = _SOURCES.search(body)
        sources = re.findall(r"`([^`]+)`", sources_match.group(1)) if sources_match else []
        keys = [value.strip().rstrip(".") for value in _BOLD.findall(expected)]
        if not keys:
            first = expected.splitlines()[0].strip().rstrip(".") if expected else ""
            if first and len(first.split()) <= 3:
                keys = [first]
        questions.append(
            {
                "id": int(match.group(1)),
                "question": match.group(2).strip(),
                "expected": expected,
                "keys": keys,
                "sources": sources,
            }
        )
    return questions


def _numbers(text: str) -> set[float]:
    values = set()
    for raw in _NUMBER.findall(text):
        try:
            values.add(float(raw.replace(",", "")))
        except ValueError:
            continue
    return values


def _date(text: str) -> datetime | None:
    cleaned = text.strip().rstrip(".")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def key_found(key: str, answer: str) -> bool:
    lowered = answer.lower()
    if key.lower() in {"yes", "no"}:
        first = re.split(r"[.!,;\n]", answer.strip(), maxsplit=1)[0].lower()
        return re.search(rf"\b{key.lower()}\b", first) is not None
    if key.lower() in lowered:
        return True
    date = _date(key)
    if date is not None:
        variants = {
            date.strftime("%Y-%m-%d"),
            date.strftime("%B %-d, %Y").lower(),
            date.strftime("%-d %B %Y").lower(),
            date.strftime("%b %-d, %Y").lower(),
        }
        return any(variant.lower() in lowered for variant in variants)
    key_numbers = _numbers(key)
    if key_numbers and not re.search(r"[a-z]{3,}", key.lower().replace("inv", "").replace("po", "")):
        return key_numbers <= _numbers(answer)
    words = [
        word
        for word in re.findall(r"[a-z0-9$.,-]+", key.lower())
        if (len(word) > 3 and word not in _STOPWORDS) or word[0].isdigit()
    ]
    if len(words) >= 2:
        answer_words = set(re.findall(r"[a-z0-9$.,-]+", lowered))
        return all(word.strip(".,") in {item.strip(".,") for item in answer_words} for word in words)
    return False


def grade(question: dict, result: dict) -> dict:
    answer = result.get("content") or ""
    found = [key for key in question["keys"] if key_found(key, answer)]
    cited = {item["citation"].split(",", 1)[0].strip().lower() for item in result.get("citations") or []}
    expected_sources = [source.lower() for source in question["sources"]]
    source_hits = [source for source in expected_sources if source in cited]
    return {
        "answer_ok": bool(question["keys"]) and len(found) == len(question["keys"]),
        "keys_found": found,
        "source_recall": (len(source_hits) / len(expected_sources)) if expected_sources else None,
        "unsupported_citations": sum(
            1 for item in result.get("citations") or [] if not item.get("supported")
        ),
    }


async def _run(args: argparse.Namespace) -> None:
    from document_chat.config import config
    from document_chat.services.agents.orchestrator import Document, run_turn
    from document_chat.services.ingest import index_document
    from document_chat.services.parsers.kinds import kind_for_filename

    corpus = Path(args.corpus)
    questions = parse_questions(corpus / "document_chat_questions.md")
    if args.ids:
        wanted = {int(item) for item in args.ids.split(",")}
        questions = [question for question in questions if question["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]

    documents: list[Document] = []
    for path in sorted(corpus.iterdir()):
        if path.name in ("document_chat_questions.md", "MANIFEST.txt") or not path.is_file():
            continue
        record = {"id": path.stem, "filename": path.name, "path": str(path.resolve())}
        index_document(record)
        documents.append(
            Document(
                id=path.stem,
                filename=path.name,
                path=str(path.resolve()),
                kind=kind_for_filename(path.name),
            )
        )

    out_dir = Path(config.data_dir) / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for question in questions:
        started = time.perf_counter()
        try:
            result = await run_turn(question["question"], documents, [])
            error = ""
        except Exception as exc:
            result, error = {}, f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - started
        row = {
            **question,
            "answer": result.get("content", ""),
            "plan": result.get("plan"),
            "confidence": result.get("confidence"),
            "unknown": result.get("unknown"),
            "citations": result.get("citations", []),
            "seconds": round(elapsed, 1),
            "error": error,
            **grade(question, result),
        }
        rows.append(row)
        mark = "PASS" if row["answer_ok"] else "FAIL"
        print(f"Q{question['id']:>3} {mark} {elapsed:5.1f}s  {question['question'][:70]}", flush=True)
        (out_dir / "results.json").write_text(json.dumps(rows, indent=2, default=str))
        if args.pause:
            await asyncio.sleep(args.pause)

    report = _report(rows, config.provider, config.model)
    (out_dir / "report.md").write_text(report)
    print(report)
    print(f"Wrote {out_dir / 'report.md'} and {out_dir / 'results.json'}")


def _report(rows: list[dict], provider: str, model: str) -> str:
    graded = [row for row in rows if row["keys"]]
    passed = sum(1 for row in graded if row["answer_ok"])
    recalls = [row["source_recall"] for row in rows if row["source_recall"] is not None]
    seconds = [row["seconds"] for row in rows]
    lines = [
        f"# Eval report — {provider} / {model}",
        "",
        f"- Questions run: {len(rows)} (auto-graded: {len(graded)})",
        f"- Answer accuracy: {passed}/{len(graded)}"
        + (f" ({passed / len(graded):.0%})" if graded else ""),
        f"- Mean source recall: {sum(recalls) / len(recalls):.0%}" if recalls else "- Mean source recall: n/a",
        f"- Unsupported citations: {sum(row['unsupported_citations'] for row in rows)}",
        f"- Errors: {sum(1 for row in rows if row['error'])}",
        f"- Median latency: {sorted(seconds)[len(seconds) // 2]:.1f}s" if seconds else "",
        "",
        "| Q | Result | Source recall | Confidence | Seconds | Question |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        result = "error" if row["error"] else ("pass" if row["answer_ok"] else "fail" if row["keys"] else "n/a")
        recall = f"{row['source_recall']:.0%}" if row["source_recall"] is not None else "–"
        confidence = f"{row['confidence']:.2f}" if isinstance(row["confidence"], (int, float)) else "–"
        question = row["question"].replace("|", "\\|")
        lines.append(f"| {row['id']} | {result} | {recall} | {confidence} | {row['seconds']} | {question} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", default="../document_chat_test_set")
    parser.add_argument("--ids", help="Comma-separated question numbers, e.g. 1,7,13")
    parser.add_argument("--limit", type=int, help="Run only the first N questions")
    parser.add_argument("--pause", type=float, default=0, help="Seconds between questions (rate limits)")
    parser.add_argument("--data-dir", default="data/eval_run", help="Isolated data dir for the eval index")
    args = parser.parse_args()
    os.environ["DATA_DIR"] = args.data_dir
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
