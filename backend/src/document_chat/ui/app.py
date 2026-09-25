"""Document Chat — Streamlit UI."""

from __future__ import annotations

import asyncio
import html
import io
import json
from types import SimpleNamespace

import streamlit as st

from document_chat.logging import configure_logging
from document_chat.services.chat import ChatService
from document_chat.services.conversations import (
    ConversationNotFoundError,
    conversations_service,
)
from document_chat.services.documents import (
    DocumentNotFoundError,
    UnsupportedDocumentError,
    documents_service,
)

configure_logging()
chat_service = ChatService(documents_service, conversations_service)

st.set_page_config(
    page_title="Document Chat",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap');

:root {
  --bg: #0f1419;
  --panel: #161c24;
  --text: #e8eef6;
  --muted: #8b9bb0;
  --accent: #3d9a8b;
  --accent-2: #c4a35a;
  --user: #243044;
  --assistant: #1a222d;
}

/* Lock the app shell — only inner panels scroll */
html, body, .stApp, [data-testid="stAppViewContainer"] {
  height: 100vh !important;
  max-height: 100vh !important;
  overflow: hidden !important;
  background:
    radial-gradient(1200px 600px at 10% -10%, #1a3a36 0%, transparent 55%),
    radial-gradient(900px 500px at 100% 0%, #2a2418 0%, transparent 50%),
    var(--bg) !important;
  color: var(--text);
  font-family: "IBM Plex Sans", sans-serif;
}
section.main {
  height: 100vh !important;
  overflow: hidden !important;
}
section.main .block-container {
  padding-top: 4.25rem !important;
  padding-right: 0.65rem !important;
  padding-left: 1rem !important;
  padding-bottom: 5.25rem !important;
  max-width: none !important;
  height: 100vh !important;
  overflow: hidden !important;
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #121820 0%, #0e1319 100%) !important;
  border-right: 1px solid #2a3444;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
  gap: 0.15rem !important;
}

/* One card per chat row — no divider between title and × */
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
  gap: 0 !important;
  align-items: center !important;
  background: rgba(28, 36, 48, 0.55) !important;
  border: 1px solid rgba(42, 52, 68, 0.35) !important;
  border-radius: 8px !important;
  padding: 0.1rem 0.15rem 0.1rem 0.15rem !important;
  margin-bottom: 0.15rem !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] > div {
  background: transparent !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button[data-testid="stBaseButton-secondary"],
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button[data-testid="stBaseButton-primary"] {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  color: var(--text) !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button[data-testid="stBaseButton-primary"] {
  color: #e8fff9 !important;
  font-weight: 600 !important;
  box-shadow: inset 2px 0 0 var(--accent) !important;
  border-radius: 6px !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has(button[data-testid="stBaseButton-primary"]) {
  border-color: rgba(61, 154, 139, 0.45) !important;
  background: rgba(26, 44, 42, 0.72) !important;
}

header[data-testid="stHeader"] {
  background: rgba(15, 20, 25, 0.92) !important;
}

h1, h2, h3 {
  font-family: "IBM Plex Serif", serif !important;
  letter-spacing: -0.02em;
  margin-top: 0.35rem !important;
  margin-bottom: 0.45rem !important;
  overflow-wrap: anywhere;
}

.brand {
  font-family: "IBM Plex Serif", serif;
  font-size: 1.45rem;
  font-weight: 600;
  margin: 0.5rem 0 0.2rem;
}
.brand-sub {
  color: var(--muted);
  font-size: 0.82rem;
  margin-bottom: 0.65rem;
}

.msg {
  border: none !important;
  border-radius: 10px;
  padding: 0.75rem 0.9rem;
  margin: 0.35rem 0;
  background: var(--assistant);
}
.msg.user { background: var(--user); }
.msg-role {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent-2);
  margin-bottom: 0.35rem;
  font-weight: 600;
}
.msg.user .msg-role { color: #7eb6ff; }

.turn-box {
  background: rgba(255,255,255,0.03);
  border: none;
  border-radius: 12px;
  padding: 0.55rem 0.7rem 0.15rem;
  margin: 0.55rem 0 1.15rem;
}

.row-title {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text);
}
.row-meta {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.75rem;
  color: var(--muted);
}

/* Force teal accent (override Streamlit coral theme) */
button[data-testid="stBaseButton-primary"],
.stButton > button[kind="primary"] {
  background: #3d9a8b !important;
  background-color: #3d9a8b !important;
  border-color: transparent !important;
  color: #041210 !important;
  font-weight: 600;
}

/* Chat title buttons: ellipsis */
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"],
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
  justify-content: flex-start !important;
  text-align: left !important;
  overflow: hidden !important;
}
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] p,
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] p,
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] span,
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] span,
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] div,
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] div {
  display: block !important;
  width: 100% !important;
  max-width: 100% !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}

/* Borderless × */
button[data-testid="stBaseButton-tertiary"],
.stButton > button[kind="tertiary"] {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  color: #8b9bb0 !important;
  min-width: 1.75rem !important;
  width: 1.75rem !important;
  padding: 0.15rem !important;
}
button[data-testid="stBaseButton-tertiary"]:hover,
.stButton > button[kind="tertiary"]:hover {
  color: #f07178 !important;
  background: transparent !important;
  border: none !important;
}

/* Turn footer × row */
section.main [data-testid="stHorizontalBlock"]:has(button[data-testid="stBaseButton-tertiary"]) {
  margin-top: 0.35rem !important;
  margin-bottom: 0.15rem !important;
  justify-content: flex-end !important;
}

/* Docs list: less right gap */
section.main [data-testid="stHorizontalBlock"] {
  gap: 0.15rem !important;
}

[data-testid="stBottomBlockContainer"] {
  padding: 0.5rem 1rem 0.75rem !important;
}
[data-testid="stChatInput"] textarea::placeholder {
  color: #8b9bb0 !important;
  opacity: 1 !important;
}
[data-testid="stChatInput"] textarea {
  background: #161c24 !important;
  padding: 0.4rem 0.6rem !important;
  min-height: 2.35rem !important;
  line-height: 1.3 !important;
}
[data-testid="stChatInput"] [data-baseweb="base-input"],
[data-testid="stChatInput"] [data-baseweb="textarea"] {
  padding: 0.15rem !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# Leave room for fixed chat input + header
PANEL_HEIGHT = 560


def _format_size(n: int | None) -> str:
    if not n:
        return "0 B"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _as_upload(name: str, data: bytes, content_type: str | None = None):
    return SimpleNamespace(
        filename=name,
        content_type=content_type,
        file=io.BytesIO(data),
    )


def _ensure_state() -> None:
    if "active_id" not in st.session_state:
        st.session_state.active_id = None
    if "error" not in st.session_state:
        st.session_state.error = ""


def _load_conversation(conversation_id: str) -> dict | None:
    try:
        return conversations_service.get(conversation_id)
    except ConversationNotFoundError:
        return None


def _refresh_list() -> list[dict]:
    return conversations_service.list()


def _delete_conversation(conversation_id: str) -> None:
    record = _load_conversation(conversation_id)
    if record:
        for document_id in record.get("document_ids") or []:
            try:
                documents_service.delete(document_id)
            except DocumentNotFoundError:
                pass
        conversations_service.delete(conversation_id)
    if st.session_state.active_id == conversation_id:
        st.session_state.active_id = None


def _x_button(key: str, help_text: str) -> bool:
    return st.button(
        "",
        key=key,
        help=help_text,
        type="tertiary",
        icon=":material/close:",
    )


def _render_trace(events: list[dict], plan: dict | None = None) -> None:
    if not events and not plan:
        return
    with st.expander(f"Agent trace · {len(events)} events", expanded=False):
        if plan:
            st.caption("Plan")
            st.code(json.dumps(plan, indent=2), language="json")
        for event in events:
            kind = event.get("type")
            agent = event.get("agent") or "?"
            if kind == "agent_start":
                st.markdown(f"**{agent}** started")
                if event.get("query"):
                    st.code(str(event["query"])[:2000])
            elif kind == "tool_call":
                st.markdown(f"`{agent}` → `{event.get('tool')}`")
                st.code(json.dumps(event.get("args") or {}, indent=2)[:3000], language="json")
            elif kind == "tool_result":
                st.markdown(f"`{agent}` ← `{event.get('tool')}`")
                st.code(str(event.get("content") or "(empty)")[:3000])
            elif kind == "message":
                st.markdown(f"**{agent}**")
                st.markdown(str(event.get("content") or ""))
            elif kind == "agent_done":
                elapsed = event.get("elapsed_ms")
                suffix = f" ({elapsed}ms)" if elapsed is not None else ""
                st.markdown(f"**{agent}** done{suffix}")
                if event.get("answer"):
                    st.markdown(str(event["answer"]))
            else:
                st.caption(f"{kind}: {json.dumps(event, default=str)[:500]}")


def _render_answer_meta(message: dict) -> None:
    parts = []
    if message.get("unknown"):
        parts.append(":orange-badge[I don't know]")
    confidence = message.get("confidence")
    if isinstance(confidence, (int, float)):
        color = "green" if confidence >= 0.7 else "orange" if confidence >= 0.4 else "red"
        parts.append(f":{color}-badge[confidence {confidence:.0%}]")
    for item in message.get("citations") or []:
        text = str(item.get("citation", "")).replace("[", "(").replace("]", ")")
        if item.get("supported"):
            parts.append(f":gray-badge[:material/description: {text}]")
        else:
            parts.append(f":red-badge[:material/warning: unverified: {text}]")
    if parts:
        st.markdown(" ".join(parts))


def _render_message_body(message: dict) -> None:
    role = message.get("role") or "assistant"
    css = "msg user" if role == "user" else "msg"
    label = "You" if role == "user" else "Assistant"
    st.markdown(
        f'<div class="{css}"><div class="msg-role">{label}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(message.get("content") or "")
    if role == "assistant":
        _render_answer_meta(message)
        events = []
        if isinstance(message.get("trace"), dict):
            events = list(message["trace"].get("events") or [])
        plan = message.get("plan") if isinstance(message.get("plan"), dict) else None
        _render_trace(events, plan)


def _message_pairs(messages: list[dict]) -> list[tuple[dict | None, dict | None]]:
    pairs: list[tuple[dict | None, dict | None]] = []
    index = 0
    while index < len(messages):
        current = messages[index]
        nxt = messages[index + 1] if index + 1 < len(messages) else None
        if (
            current.get("role") == "user"
            and nxt is not None
            and nxt.get("role") == "assistant"
        ):
            pairs.append((current, nxt))
            index += 2
        elif current.get("role") == "assistant":
            pairs.append((None, current))
            index += 1
        else:
            pairs.append((current, None))
            index += 1
    return pairs


def _render_turn(user_msg: dict | None, assistant_msg: dict | None, conversation_id: str) -> None:
    delete_id = None
    if assistant_msg and assistant_msg.get("id"):
        delete_id = assistant_msg["id"]
    elif user_msg and user_msg.get("id"):
        delete_id = user_msg["id"]

    if user_msg:
        _render_message_body(user_msg)
    if assistant_msg:
        _render_message_body(assistant_msg)
    if delete_id:
        _left, xcol = st.columns([24, 1])
        with xcol:
            if _x_button(f"del-turn-{delete_id}", "Delete this exchange"):
                try:
                    conversations_service.delete_message(conversation_id, delete_id)
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.session_state.error = str(exc)
        st.markdown('<div style="height:0.65rem"></div>', unsafe_allow_html=True)


async def _stream_chat(conversation_id: str, prompt: str, status, answer_box, trace_box):
    events: list[dict] = []
    answer = ""
    record = None
    async for event in chat_service.stream(conversation_id, prompt):
        kind = event.get("type")
        if kind == "error":
            raise RuntimeError(event.get("detail") or "Chat failed")
        if kind == "done":
            record = event.get("record")
            break
        events.append(event)
        if (
            kind == "message"
            and event.get("agent") == "orchestrator"
            and event.get("content")
        ):
            answer = event["content"]
        if (
            kind == "agent_done"
            and event.get("agent") == "orchestrator"
            and event.get("answer")
        ):
            answer = event["answer"]
        agent = event.get("agent") or "agent"
        if kind == "agent_start":
            status.update(label=f"Running {agent}…", state="running")
        elif kind == "tool_call":
            status.update(label=f"{agent} → {event.get('tool')}", state="running")
        elif kind == "agent_done":
            status.update(label=f"{agent} done", state="running")
        if answer:
            answer_box.markdown(answer)
        with trace_box.container():
            _render_trace(events)
    return record, events, answer


def _sidebar() -> None:
    st.markdown('<p class="brand">Document Chat</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="brand-sub">Ask across PDFs, sheets, images, and code.</p>',
        unsafe_allow_html=True,
    )
    if st.button("＋ New chat", use_container_width=True, type="primary", key="new-chat"):
        created = conversations_service.create()
        st.session_state.active_id = created["id"]
        st.session_state.error = ""
        st.rerun()

    conversations = _refresh_list()
    if not conversations:
        st.caption("No conversations yet")
        return

    current = st.session_state.active_id
    ids = [item["id"] for item in conversations]
    if current not in ids:
        st.session_state.active_id = ids[0]
        current = ids[0]

    for item in conversations:
        cid = item["id"]
        title = (item.get("title") or "Untitled").strip() or "Untitled"
        select_col, delete_col = st.columns([10, 1], gap="small")
        with select_col:
            if st.button(
                title,
                key=f"chat-select-{cid}",
                use_container_width=True,
                type="primary" if cid == current else "secondary",
                help=title,
            ):
                if cid != current:
                    st.session_state.active_id = cid
                    st.session_state.error = ""
                    st.rerun()
        with delete_col:
            if _x_button(f"chat-del-{cid}", "Delete conversation"):
                _delete_conversation(cid)
                st.rerun()


def _docs_panel(conversation: dict) -> None:
    st.markdown("### Documents")
    uploads = st.file_uploader(
        "Attach files",
        accept_multiple_files=True,
        type=[
            "pdf", "docx", "txt", "md", "pptx", "csv", "xlsx",
            "png", "jpg", "jpeg", "webp", "html",
            "py", "js", "ts", "tsx", "jsx", "java", "go", "rs", "c", "cpp", "h", "hpp",
        ],
        key=f"uploader-{conversation['id']}",
    )
    if uploads and st.button("Upload", type="primary", key=f"upload-btn-{conversation['id']}"):
        try:
            files = [
                _as_upload(item.name, item.getvalue(), getattr(item, "type", None))
                for item in uploads
            ]
            created = documents_service.create(files, conversation["id"])
            conversations_service.add_documents(conversation["id"], created)
            st.success(f"Uploaded {len(created)} file(s)")
            st.rerun()
        except UnsupportedDocumentError as exc:
            st.session_state.error = str(exc)
        except Exception as exc:  # noqa: BLE001
            st.session_state.error = str(exc)

    documents = conversation.get("documents") or []
    if not documents:
        st.caption("No documents in this chat yet.")
        return

    for doc in documents:
        name = doc.get("filename") or "file"
        safe = html.escape(name)
        kind = html.escape(str(doc.get("kind") or "file"))
        body_col, del_col = st.columns([10, 1], gap="small")
        with body_col:
            st.markdown(
                f'<span class="row-title" title="{safe}">{safe}</span>'
                f'<span class="row-meta">{_format_size(doc.get("size"))} · {kind}</span>',
                unsafe_allow_html=True,
            )
        with del_col:
            if _x_button(f"rm-doc-{doc['id']}", f"Remove {name}"):
                try:
                    documents_service.delete(doc["id"])
                    conversations_service.remove_document_id(conversation["id"], doc["id"])
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.session_state.error = str(exc)


def main() -> None:
    _ensure_state()

    with st.sidebar:
        _sidebar()

    active_id = st.session_state.active_id
    if not active_id:
        conversations = _refresh_list()
        if conversations:
            st.session_state.active_id = conversations[0]["id"]
            st.rerun()
        st.markdown("## Start a conversation")
        st.write("Create a new chat from the sidebar, attach documents, then ask a question.")
        return

    conversation = _load_conversation(active_id)
    if conversation is None:
        st.session_state.active_id = None
        st.rerun()
        return

    title = conversation.get("title") or "New chat"
    col_chat, col_docs = st.columns([2.4, 1], gap="medium")

    with col_docs:
        with st.container(height=PANEL_HEIGHT, border=False):
            _docs_panel(conversation)

    with col_chat:
        st.markdown(f"## {html.escape(title)}")
        if st.session_state.error:
            st.error(st.session_state.error)

        with st.container(height=PANEL_HEIGHT - 56, border=False):
            messages = conversation.get("messages") or []
            if not messages:
                st.info("Attach documents on the right, then ask anything about them.")
            for user_msg, assistant_msg in _message_pairs(messages):
                _render_turn(user_msg, assistant_msg, active_id)

    # Declared after columns so Streamlit docks it; CSS keeps it fixed on screen
    prompt = st.chat_input("Ask anything about your documents…")
    if prompt:
        st.session_state.error = ""
        try:
            with st.status("Working…", expanded=True) as status:
                answer_box = st.empty()
                trace_box = st.empty()
                record, _events, _answer = asyncio.run(
                    _stream_chat(active_id, prompt, status, answer_box, trace_box)
                )
                status.update(label="Done", state="complete")
            if record is None:
                raise RuntimeError("Chat ended without a result")
        except Exception as exc:  # noqa: BLE001
            st.session_state.error = str(exc)
        st.rerun()


main()
