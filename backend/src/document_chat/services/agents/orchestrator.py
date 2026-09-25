import asyncio
import base64
import json
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, Any, List, Literal

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from document_chat.config import config, get_client
from document_chat.logging import get_logger, preview
from document_chat.services.agents import citations
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


# Recording tools end their agent's loop (return_direct): the tool arguments are
# the output, so a follow-up model call would only cost tokens and rate limit.
@tool(return_direct=True)
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


@tool(return_direct=True)
def draft_answer(answer: str) -> str:
    """Record the synthesized draft answer."""
    return "draft recorded"


@tool(return_direct=True)
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


def _repeated_query(state: dict, tool_name: str, query: str) -> bool:
    """True if an earlier call in this agent run used the same (normalized) query."""
    wanted = " ".join(query.lower().split()).strip(" :?.")
    seen = 0
    for message in state.get("messages") or []:
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("name") != tool_name:
                continue
            previous = str((call.get("args") or {}).get("query", ""))
            if " ".join(previous.lower().split()).strip(" :?.") == wanted:
                seen += 1
    # The current call is already in the last AI message, so a repeat counts twice.
    return seen > 1


@tool
async def retrieval_tool(
    query: str,
    state: Annotated[SubAgentState, InjectedState],
    document_ids: List[str] | None = None,
) -> list:
    """Hybrid (keyword + semantic) search over this conversation's files.
    Optionally limit to document ids or filenames. Returns cited passages."""
    if _repeated_query(state, "retrieval_tool", query):
        return [
            {
                "type": "text",
                "text": "You already ran this query; its passages are above. Answer from them now.",
            }
        ]
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
    """Search images by content; returns caption and OCR text for the best matches.
    Optionally limit to document ids or filenames."""
    ids = [document.id for document in resolve_documents(state["documents"], document_ids)]
    logger.info("vision tool start query=%s document_ids=%s", preview(query, 300), ids)
    if not config.clip_images:
        image_ids = [document.id for document in state["documents"] if document.kind == IMAGE_KIND and document.id in ids]
        chunks = chroma_store.fetch(image_ids, {TEXT_KIND}) if image_ids else []
        if not chunks:
            return [{"type": "text", "text": "No images available."}]
        return [_image_text_block(chunk.filename, chunk.caption, chunk.ocr_text) for chunk in chunks]
    hits = chroma_store.query(query, ids, kinds={IMAGE_KIND})
    if not hits:
        return [{"type": "text", "text": "No images available."}]
    return [_image_text_block(hit.filename, hit.caption, hit.ocr_text) for hit in hits]


_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_MAX_ATTACHED_IMAGES = 4


def _image_text_block(filename: str, caption: str, ocr_text: str) -> dict:
    return {
        "type": "text",
        "text": (
            f"[{filename}, image]\n"
            f"caption: {caption or '(none)'}\n"
            f"ocr_text: {ocr_text or '(empty)'}"
        ),
    }


def image_blocks(documents: list[Document]) -> list[dict]:
    """Text + image_url block pairs for the vision agent's input message.

    Images go in the user message, not in tool results: several providers
    (Groq among them) only accept string or text content in tool messages.
    """
    blocks: list[dict] = []
    ocr = {
        chunk.document_id: chunk
        for chunk in chroma_store.fetch([document.id for document in documents], {TEXT_KIND})
    }
    for document in documents[:_MAX_ATTACHED_IMAGES]:
        path = Path(document.path)
        mime = _IMAGE_MIME.get(path.suffix.lower())
        if mime is None or not path.is_file():
            continue
        chunk = ocr.get(document.id)
        blocks.append(
            _image_text_block(
                document.filename,
                chunk.caption if chunk else "",
                chunk.ocr_text if chunk else "",
            )
        )
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        blocks.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
    return blocks


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

def _limits(tool_calls: int) -> list:
    # Each extra tool call resends the growing transcript; unbounded loops are what
    # exhaust tokens-per-minute limits. Past the cap the model must answer from what it has.
    return [
        ToolCallLimitMiddleware(run_limit=tool_calls, exit_behavior="continue"),
        ModelCallLimitMiddleware(run_limit=tool_calls + 1, exit_behavior="end"),
    ]


retrieval_agent = create_agent(
    model=model,
    tools=[retrieval_tool],
    system_prompt=RETRIEVAL_PROMPT,
    name="retrieval",
    state_schema=SubAgentState,
    middleware=_limits(3),
)

table_agent = create_agent(
    model=model,
    tools=[table_tool],
    system_prompt=TABLE_PROMPT,
    name="table",
    state_schema=SubAgentState,
    middleware=_limits(4),
)

vision_agent = create_agent(
    model=model,
    tools=[vision_tool],
    system_prompt=VISION_PROMPT,
    name="vision",
    state_schema=SubAgentState,
    middleware=_limits(2),
)

code_agent = create_agent(
    model=model,
    tools=[code_tool],
    system_prompt=CODE_PROMPT,
    name="code",
    state_schema=SubAgentState,
    middleware=_limits(2),
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


AGENT_TOOLS = {
    "planner": [submit_plan.name],
    "retrieval": [retrieval_tool.name],
    "table": [table_tool.name],
    "vision": [vision_tool.name],
    "code": [code_tool.name],
    "synthesis": [draft_answer.name],
    "verify": [finalize_answer.name],
}


def _is_bad_tool_call(exc: Exception) -> bool:
    text = str(exc)
    return "tool_use_failed" in text or "not in request.tools" in text


_IMAGE_REJECTIONS = ("content must be a string", "does not support image", "image input")
_images_rejected = False


def _is_image_rejection(exc: Exception) -> bool:
    text = str(exc).lower()
    return "400" in text and any(marker in text for marker in _IMAGE_REJECTIONS)


def _reject_images() -> None:
    """Remember for this process that the model is text-only, so later turns skip image blocks."""
    global _images_rejected
    _images_rejected = True


async def _try_agent(name: str, agent, query: str) -> dict | None:
    """Run a single-agent step; on failure emit agent_error and return None."""
    try:
        return await _run_agent(name, agent, query)
    except Exception as exc:
        await emit(
            {"type": "agent_error", "agent": name, "error": f"{type(exc).__name__}: {exc}"[:500]}
        )
        return None


_LIMIT_NOTES = ("call limit", "call limits exceeded", "You already ran this query")


def _report_text(messages: list) -> str:
    """The agent's final answer, or its raw tool results if a call cap cut it off."""
    if not messages:
        return ""
    last = messages[-1]
    answer = message_content(last.content)
    cut_off = getattr(last, "tool_calls", None) or any(note in answer for note in _LIMIT_NOTES)
    if answer.strip() and not cut_off:
        return answer
    results: list[str] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        text = message_content(message.content).strip()
        if text and text not in results and not any(note in text for note in _LIMIT_NOTES):
            results.append(text)
    return "\n\n".join(results) or answer


async def _run_agent(
    name: str,
    agent,
    query: str,
    documents: list[Document] | None = None,
    attachments: list[dict] | None = None,
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
    final = None
    note = ""
    for attempt in range(2):
        text = query + note
        if attachments and _images_rejected:
            text = "\n\n".join([text, *(block["text"] for block in attachments if "text" in block)])
        content: str | list[dict] = (
            [{"type": "text", "text": text}, *attachments]
            if attachments and not _images_rejected
            else text
        )
        payload: dict = {"messages": [{"role": "user", "content": content}]}
        if documents is not None:
            payload["documents"] = documents
        try:
            async for mode, chunk in agent.astream(
                payload,
                stream_mode=["updates", "values"],
            ):
                if mode == "updates":
                    await emit_messages(name, chunk)
                else:
                    final = chunk
            break
        except Exception as exc:
            if attempt == 0 and attachments and not _images_rejected and _is_image_rejection(exc):
                _reject_images()
                logger.warning("model rejected image input; using OCR text only from now on: %s", preview(str(exc), 300))
                await emit({"type": "agent_retry", "agent": name, "error": preview(str(exc), 300)})
                continue
            if attempt == 0 and _is_bad_tool_call(exc):
                logger.warning("agent called unknown tool name=%s; retrying: %s", name, preview(str(exc), 300))
                await emit({"type": "agent_retry", "agent": name, "error": preview(str(exc), 300)})
                allowed = ", ".join(AGENT_TOOLS.get(name, [])) or "none"
                note = (
                    "\n\nYour previous reply called a tool that does not exist. "
                    f"The only tools you may call are: {allowed}."
                )
                continue
            logger.exception("agent failed name=%s", name)
            raise
    messages = (final or {}).get("messages") or []
    answer = _report_text(messages)
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


_PRIOR_PLANS = 3


async def run_turn(
    prompt: str,
    documents: list[Document],
    prior: list[dict] | None = None,
) -> dict:
    manifest = _file_manifest(documents)
    planner_input = "\n\n".join(
        [
            f"File manifest:\n{json.dumps(manifest)}",
            f"Previous planner outputs:\n{json.dumps((prior or [])[-_PRIOR_PLANS:])}",
            f"Current question:\n{prompt.strip()}",
        ]
    )
    planner = await _try_agent("planner", planner_agent, planner_input)
    plan = _plan_from_messages(planner["messages"] if planner else [], prompt)
    await emit({"type": "message", "agent": "planner", "content": json.dumps(plan)})

    jobs = []
    attachments: dict[str, list[dict]] = {}
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
        if config.vision_images:
            attachments["vision"] = image_blocks(resolve_documents(docs, plan["target_files"]))
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
    failed: set[str] = set()
    evidence: list[str] = [
        block["text"] for blocks in attachments.values() for block in blocks if "text" in block
    ]
    if jobs:
        results = await asyncio.gather(
            *[
                _run_agent(name, agent, human, docs, attachments.get(name))
                for name, agent, human, docs in jobs
            ],
            return_exceptions=True,
        )
        for (name, *_), result in zip(jobs, results):
            if isinstance(result, BaseException):
                reports[name] = f"{name} specialist failed: {type(result).__name__}: {result}"[:500]
                failed.add(name)
                await emit({"type": "agent_error", "agent": name, "error": reports[name]})
                continue
            reports[result["name"]] = result["answer"]
            evidence.extend(
                message_content(message.content)
                for message in result["messages"]
                if getattr(message, "type", None) == "tool"
            )

    synthesis_input = (
        f"Question:\n{prompt.strip()}\n\n"
        f"Plan intent: {plan['intent']}\n\n"
        f"Specialist reports:\n{json.dumps(reports)}"
    )
    synthesis = await _try_agent("synthesis", synthesis_agent, synthesis_input)
    if synthesis is None:
        draft_text = "\n\n".join(f"{name}: {report}" for name, report in reports.items())
    else:
        draft = tool_call_args(synthesis["messages"], "draft_answer") or {}
        draft_text = str(draft.get("answer") or synthesis["answer"])

    verify = await _try_agent(
        "verify",
        verify_agent,
        f"Draft:\n{draft_text}\n\nSpecialist reports:\n{json.dumps(reports)}",
    )
    final = (tool_call_args(verify["messages"], "finalize_answer") if verify else None) or {}
    if synthesis is None and verify is None and len(failed) == len(reports):
        final = {
            "answer": (
                "I couldn't complete this answer: the language model provider rejected the "
                "requests (most often a rate limit or daily quota). Please retry in a minute, "
                "or switch PROVIDER. Details are in the agent trace."
            ),
            "unknown": True,
            "confidence": 0.0,
        }
    answer = citations.clean_text(str(final.get("answer") or draft_text))
    unknown = bool(final.get("unknown"))
    cited, confidence = citations.check(
        answer,
        evidence,
        {document.filename for document in documents},
        final.get("confidence"),
        unknown,
    )
    await emit({"type": "citations", "agent": "verify", "citations": cited})
    return {
        "content": answer,
        "plan": plan,
        "confidence": confidence,
        "unknown": unknown,
        "citations": cited,
        "reports": reports,
    }


logger.info(
    "agents ready pipeline=%s",
    ["planner", "retrieval", "table", "vision", "code", "synthesis", "verify"],
)
