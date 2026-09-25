import asyncio
import base64
import json
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, Any, List, Literal

from langchain.agents import AgentState, create_agent
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from document_chat.config import config, get_client
from document_chat.logging import get_logger, preview
from document_chat.services.agents.messages import tool_call_args
from document_chat.services.agents.prompts import (
    CODE_PROMPT,
    PLANNER_PROMPT,
    RETRIEVAL_PROMPT,
    SYNTHESIS_PROMPT,
    TABLE_PROMPT,
    VERIFY_PROMPT,
    VISION_PROMPT,
)
from document_chat.services.index.chroma_store import chroma_store
from document_chat.services.index.retrieval import search_chunks
from document_chat.services.index.table_store import table_store
from document_chat.services.parsers.kinds import (
    CODE_KIND,
    IMAGE_KIND,
    TABLE_KIND,
    TEXT_KIND,
)

logger = get_logger("document_chat.orchestrator")

_stream_queue: ContextVar[asyncio.Queue | None] = ContextVar("stream_queue", default=None)
_stream_events: ContextVar[list | None] = ContextVar("stream_events", default=None)


class Document(BaseModel):
    id: str = Field(description="The id of the document")
    filename: str = Field(description="The filename of the document")
    path: str = Field(description="The path of the document")
    kind: Literal[TEXT_KIND, IMAGE_KIND, CODE_KIND, TABLE_KIND] = Field(
        description="The kind of the document"
    )


class OrchestratorState(AgentState):
    documents: List[Document] = Field(
        description="The list of documents to be used by the orchestrator"
    )


class SubAgentState(AgentState):
    documents: List[Document] = Field(
        description="The list of documents to be used by the subagent"
    )


def message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


async def emit(event: dict) -> None:
    events = _stream_events.get()
    if events is not None:
        events.append(event)
    queue = _stream_queue.get()
    if queue is not None:
        await queue.put(event)
    kind = event.get("type")
    agent = event.get("agent")
    if kind == "tool_call":
        logger.info(
            "stream tool call agent=%s tool=%s args=%s",
            agent,
            event.get("tool"),
            preview(event.get("args"), 400),
        )
    elif kind == "tool_result":
        logger.info(
            "stream tool result agent=%s tool=%s content=%s",
            agent,
            event.get("tool"),
            preview(event.get("content"), 400),
        )
    elif kind == "message":
        logger.info(
            "stream message agent=%s content=%s",
            agent,
            preview(event.get("content"), 300),
        )
    else:
        logger.info("stream %s agent=%s", kind, agent)


async def emit_messages(agent: str, update: dict) -> None:
    for payload in update.values():
        if not isinstance(payload, dict):
            continue
        for message in payload.get("messages") or []:
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                for call in tool_calls:
                    await emit(
                        {
                            "type": "tool_call",
                            "agent": agent,
                            "tool": call.get("name"),
                            "args": call.get("args") or {},
                            "id": call.get("id"),
                        }
                    )
                continue
            kind = getattr(message, "type", None)
            content = message_content(getattr(message, "content", ""))
            if kind == "tool":
                await emit(
                    {
                        "type": "tool_result",
                        "agent": agent,
                        "tool": getattr(message, "name", None),
                        "content": content,
                        "id": getattr(message, "tool_call_id", None),
                    }
                )
            elif content:
                await emit(
                    {
                        "type": "message",
                        "agent": agent,
                        "content": content,
                    }
                )


@tool
def submit_plan(
    intent: str,
    need_retrieval: bool = True,
    need_table: bool = False,
    need_vision: bool = False,
    need_code: bool = False,
    subqueries: List[str] | None = None,
    target_files: List[str] | None = None,
) -> str:
    """Record the routing plan for this turn."""
    return "plan recorded"


@tool
def draft_answer(answer: str) -> str:
    """Record the synthesized draft answer."""
    return "draft recorded"


@tool
def finalize_answer(
    answer: str,
    confidence: float = 0.5,
    unknown: bool = False,
) -> str:
    """Record the final verified answer."""
    return "final recorded"


def resolve_documents(
    documents: list[Document], requested: list[str] | None
) -> list[Document]:
    """Match requested ids or filenames; fall back to every document in scope."""
    wanted = {str(item).strip().lower() for item in requested or [] if str(item).strip()}
    matched = [
        document
        for document in documents
        if document.id.lower() in wanted or document.filename.lower() in wanted
    ]
    return matched or list(documents)


@tool
async def retrieval_tool(
    query: str,
    state: Annotated[SubAgentState, InjectedState],
    document_ids: List[str] | None = None,
) -> list:
    """Hybrid (keyword + semantic) search over this conversation's files.
    Optionally limit to document ids or filenames. Returns cited passages."""
    ids = [document.id for document in resolve_documents(state["documents"], document_ids)]
    logger.info("retrieval tool start query=%s document_ids=%s", preview(query, 300), ids)
    hits = search_chunks(query, ids, kinds={TEXT_KIND, CODE_KIND})
    if not hits:
        return [{"type": "text", "text": "No matching passages."}]
    result = []
    for hit in hits:
        result.append(
            {
                "type": "text",
                "text": f"[{hit.citation}] {hit.data}",
                "filename": hit.filename,
                "location": hit.location,
                "chunk_id": hit.id,
            }
        )
    return result


@tool
async def table_tool(
    sql: str,
    state: Annotated[SubAgentState, InjectedState],
) -> dict:
    """Run one read-only SELECT against this conversation's spreadsheet tables."""
    document_ids = [document.id for document in state["documents"]]
    allowed_tables = table_store.tables_for(document_ids)
    logger.info(
        "table tool start sql=%s tables=%s",
        preview(sql, 500),
        allowed_tables,
    )
    try:
        result = table_store.query_select(sql, allowed_tables)
    except Exception as exc:
        logger.warning("table tool rejected sql=%s error=%s", preview(sql, 300), exc)
        return {
            "type": "text",
            "text": f"SQL rejected: {exc}\n\n{table_catalog(state['documents'])}",
        }
    lowered = sql.lower()
    sources = [
        f"[{document.filename}, table {name}]"
        for document in state["documents"]
        for name in table_store.tables_for([document.id])
        if name.lower() in lowered
    ]
    text = f"{' '.join(sources)}\n{result}" if sources else result
    return {"type": "text", "table": result, "text": text}


@tool
async def vision_tool(
    query: str,
    state: Annotated[SubAgentState, InjectedState],
    document_ids: List[str] | None = None,
) -> list:
    """Search images and return caption, OCR text, and the image itself.
    Optionally limit to document ids or filenames."""
    ids = [document.id for document in resolve_documents(state["documents"], document_ids)]
    logger.info("vision tool start query=%s document_ids=%s", preview(query, 300), ids)
    hits = chroma_store.query(query, ids, kinds={IMAGE_KIND})
    sources: list[tuple[str, str, str, str]]
    if hits:
        sources = [
            (str(hit.data), hit.filename, hit.caption or "", hit.ocr_text or "")
            for hit in hits
        ]
    else:
        image_docs = [
            document for document in state["documents"] if document.kind == IMAGE_KIND
        ]
        if not image_docs:
            return [{"type": "text", "text": "No images available."}]
        sources = [
            (document.path, document.filename, "", "") for document in image_docs
        ]

    result: list[dict] = []
    for path, filename, caption, ocr_text in sources:
        result.append(
            {
                "type": "text",
                "text": (
                    f"[{filename}]\n"
                    f"caption: {caption or '(none)'}\n"
                    f"ocr_text: {ocr_text or '(empty)'}"
                ),
                "filename": filename,
            }
        )
        file_path = Path(path)
        if not file_path.is_file():
            result.append(
                {
                    "type": "text",
                    "text": f"Image file missing at path={path}",
                    "filename": filename,
                }
            )
            continue
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(file_path.suffix.lower(), "application/octet-stream")
        encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
        result.append(
            {
                "type": "image",
                "image": f"data:{mime};base64,{encoded}",
                "path": str(file_path),
                "filename": filename,
            }
        )
    return result


_CODE_FULL_LINES = 300
_CODE_HEADER_LINES = 40


@tool
async def code_tool(
    document_id: str,
    state: Annotated[SubAgentState, InjectedState],
    question: str = "",
) -> list:
    """Read an uploaded source file by document id or filename. Does not execute code.
    Small files are returned whole; for large files pass `question` to get the relevant parts."""
    documents = state["documents"]
    wanted = document_id.strip().lower()
    document = next(
        (item for item in documents if wanted in (item.id.lower(), item.filename.lower())),
        documents[0] if len(documents) == 1 else None,
    )
    if document is None:
        known = ", ".join(item.filename for item in documents) or "(none)"
        return [{"type": "text", "text": f"Code file not found. Available: {known}"}]
    path = Path(document.path)
    if not path.is_file():
        return [{"type": "text", "text": "Source file is missing."}]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    def numbered(start: int, end: int) -> str:
        return "\n".join(f"{index}: {lines[index - 1]}" for index in range(start, end + 1))

    if len(lines) <= _CODE_FULL_LINES:
        return [
            {
                "type": "text",
                "text": f"[{document.filename}, L1-{len(lines)}]\n{numbered(1, len(lines))}",
                "filename": document.filename,
            }
        ]
    blocks = [
        {
            "type": "text",
            "text": (
                f"[{document.filename}, L1-{_CODE_HEADER_LINES}] "
                f"(file has {len(lines)} lines)\n{numbered(1, _CODE_HEADER_LINES)}"
            ),
            "filename": document.filename,
        }
    ]
    for hit in search_chunks(question or document.filename, [document.id], {CODE_KIND}, limit=4):
        blocks.append(
            {
                "type": "text",
                "text": f"[{hit.citation}]\n{hit.data}",
                "filename": document.filename,
                "location": hit.location,
            }
        )
    return blocks


def table_catalog(documents: list[Document]) -> str:
    parts = []
    for document in documents:
        tables = table_store.tables_for([document.id])
        if tables:
            parts.append(f"File {document.filename}:\n{table_store.describe(tables)}")
    return "\n\n".join(parts) or table_store.describe([])


model = get_client(config)

planner_agent = create_agent(
    model=model,
    tools=[submit_plan],
    system_prompt=PLANNER_PROMPT,
    name="planner",
)

retrieval_agent = create_agent(
    model=model,
    tools=[retrieval_tool],
    system_prompt=RETRIEVAL_PROMPT,
    name="retrieval",
    state_schema=SubAgentState,
)

table_agent = create_agent(
    model=model,
    tools=[table_tool],
    system_prompt=TABLE_PROMPT,
    name="table",
    state_schema=SubAgentState,
)

vision_agent = create_agent(
    model=model,
    tools=[vision_tool],
    system_prompt=VISION_PROMPT,
    name="vision",
    state_schema=SubAgentState,
)

code_agent = create_agent(
    model=model,
    tools=[code_tool],
    system_prompt=CODE_PROMPT,
    name="code",
    state_schema=SubAgentState,
)

synthesis_agent = create_agent(
    model=model,
    tools=[draft_answer],
    system_prompt=SYNTHESIS_PROMPT,
    name="synthesis",
)

verify_agent = create_agent(
    model=model,
    tools=[finalize_answer],
    system_prompt=VERIFY_PROMPT,
    name="verify",
)


async def _run_agent(
    name: str,
    agent,
    query: str,
    documents: list[Document] | None = None,
) -> dict:
    await emit(
        {
            "type": "agent_start",
            "agent": name,
            "query": query,
            "documents": [
                {"id": document.id, "filename": document.filename, "kind": document.kind}
                for document in (documents or [])
            ],
        }
    )
    started = time.perf_counter()
    payload: dict = {"messages": [{"role": "user", "content": query}]}
    if documents is not None:
        payload["documents"] = documents
    final = None
    try:
        async for mode, chunk in agent.astream(
            payload,
            stream_mode=["updates", "values"],
        ):
            if mode == "updates":
                await emit_messages(name, chunk)
            else:
                final = chunk
    except Exception:
        logger.exception("agent failed name=%s", name)
        raise
    messages = (final or {}).get("messages") or []
    answer = message_content(messages[-1].content) if messages else ""
    await emit(
        {
            "type": "agent_done",
            "agent": name,
            "answer": answer,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    )
    return {"name": name, "messages": messages, "answer": answer}


def _plan_from_messages(messages: list, prompt: str) -> dict:
    args = tool_call_args(messages, "submit_plan") or {}
    return {
        "intent": str(args.get("intent") or prompt.strip()[:200]),
        "need_retrieval": bool(args.get("need_retrieval", True)),
        "need_table": bool(args.get("need_table", False)),
        "need_vision": bool(args.get("need_vision", False)),
        "need_code": bool(args.get("need_code", False)),
        "subqueries": list(args.get("subqueries") or [prompt.strip()]),
        "target_files": list(args.get("target_files") or []),
    }


def _file_manifest(documents: list[Document]) -> list[dict]:
    return [
        {
            "id": document.id,
            "filename": document.filename,
            "kind": document.kind,
            "path": document.path,
        }
        for document in documents
    ]


def prior_plans(messages: list[dict]) -> list[dict]:
    plans = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        plan = message.get("plan")
        if isinstance(plan, dict):
            plans.append(plan)
    return plans


async def run_turn(
    prompt: str,
    documents: list[Document],
    prior: list[dict] | None = None,
) -> dict:
    manifest = _file_manifest(documents)
    planner_input = "\n\n".join(
        [
            f"File manifest:\n{json.dumps(manifest, indent=2)}",
            f"Previous planner outputs:\n{json.dumps(prior or [], indent=2)}",
            f"Current question:\n{prompt.strip()}",
        ]
    )
    planner = await _run_agent("planner", planner_agent, planner_input)
    plan = _plan_from_messages(planner["messages"], prompt)
    await emit({"type": "message", "agent": "planner", "content": json.dumps(plan)})

    jobs = []
    query = " | ".join(plan["subqueries"]) if plan["subqueries"] else prompt
    if plan["need_retrieval"]:
        jobs.append(("retrieval", retrieval_agent, query, documents))
    if plan["need_table"]:
        docs = [document for document in documents if document.kind == TABLE_KIND]
        catalog = table_catalog(docs)
        jobs.append(
            (
                "table",
                table_agent,
                f"{query}\n\nTable catalog:\n{catalog}",
                docs,
            )
        )
    if plan["need_vision"]:
        docs = [document for document in documents if document.kind == IMAGE_KIND]
        jobs.append(("vision", vision_agent, query, docs))
    if plan["need_code"]:
        docs = [document for document in documents if document.kind == CODE_KIND]
        listing = "\n".join(
            f"Document Id: {document.id}, Filename: {document.filename}"
            for document in docs
        )
        jobs.append(
            (
                "code",
                code_agent,
                f"{query}\n\nAvailable files:\n{listing}",
                docs,
            )
        )

    reports: dict[str, str] = {}
    if jobs:
        results = await asyncio.gather(
            *[_run_agent(name, agent, human, docs) for name, agent, human, docs in jobs]
        )
        for result in results:
            reports[result["name"]] = result["answer"]

    synthesis_input = (
        f"Question:\n{prompt.strip()}\n\n"
        f"Plan:\n{json.dumps(plan)}\n\n"
        f"File manifest:\n{json.dumps(manifest)}\n\n"
        f"Specialist reports:\n{json.dumps(reports)}"
    )
    synthesis = await _run_agent("synthesis", synthesis_agent, synthesis_input)
    draft = tool_call_args(synthesis["messages"], "draft_answer") or {}
    draft_text = str(draft.get("answer") or synthesis["answer"])

    verify = await _run_agent(
        "verify",
        verify_agent,
        f"Draft:\n{draft_text}\n\nSpecialist reports:\n{json.dumps(reports)}",
    )
    final = tool_call_args(verify["messages"], "finalize_answer") or {}
    answer = str(final.get("answer") or draft_text)
    return {
        "content": answer,
        "plan": plan,
        "confidence": final.get("confidence"),
        "unknown": bool(final.get("unknown")),
        "reports": reports,
    }


logger.info(
    "agents ready pipeline=%s",
    ["planner", "retrieval", "table", "vision", "code", "synthesis", "verify"],
)
