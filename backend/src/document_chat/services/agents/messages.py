from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def serialize_message(message: BaseMessage) -> dict:
    content = message.content
    if not isinstance(content, str):
        content = _content_to_text(content)
    payload = {
        "type": message.type,
        "content": content,
    }
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.get("id"),
                "name": call.get("name"),
                "args": call.get("args") or {},
            }
            for call in tool_calls
        ]
    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        payload["tool_call_id"] = tool_call_id
    name = getattr(message, "name", None)
    if name:
        payload["name"] = name
    return payload


def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    return [serialize_message(message) for message in messages]


def tool_call_args(messages: list[BaseMessage], tool_name: str) -> dict | None:
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls or []:
            if call.get("name") == tool_name:
                args = call.get("args") or {}
                return args if isinstance(args, dict) else {"value": args}
    return None


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def as_human(content: str) -> HumanMessage:
    return HumanMessage(content=content)
