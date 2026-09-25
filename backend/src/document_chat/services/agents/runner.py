from __future__ import annotations

import time

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from document_chat.config import config, get_client
from document_chat.logging import get_logger, preview
from document_chat.services.agents.messages import as_human, serialize_messages

logger = get_logger("document_chat.agents")


def run_agent(
    name: str,
    system_prompt: str,
    human: str,
    tools: list[BaseTool],
) -> dict:
    tool_names = [tool.name for tool in tools]
    logger.info(
        "agent start name=%s tools=%s prompt=%s",
        name,
        tool_names,
        preview(human, 500),
    )
    started = time.perf_counter()
    agent = create_agent(
        get_client(config),
        tools=tools,
        system_prompt=system_prompt,
        name=name,
    )
    try:
        result = agent.invoke({"messages": [as_human(human)]})
    except Exception:
        logger.exception("agent failed name=%s", name)
        raise
    messages: list[BaseMessage] = list(result.get("messages") or [])
    serialized = serialize_messages(messages)
    _log_messages(name, serialized)
    logger.info(
        "agent done name=%s messages=%s elapsed_ms=%d",
        name,
        len(serialized),
        int((time.perf_counter() - started) * 1000),
    )
    return {
        "name": name,
        "messages": serialized,
        "_messages": messages,
    }


def public_trace(run: dict) -> dict:
    return {
        "name": run["name"],
        "messages": run["messages"],
    }


def _log_messages(agent_name: str, messages: list[dict]) -> None:
    for index, message in enumerate(messages):
        kind = message.get("type")
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            for call in tool_calls:
                logger.info(
                    "tool call agent=%s step=%s tool=%s args=%s",
                    agent_name,
                    index,
                    call.get("name"),
                    preview(call.get("args"), 500),
                )
        elif kind == "tool":
            logger.info(
                "tool result agent=%s step=%s tool=%s content=%s",
                agent_name,
                index,
                message.get("name"),
                preview(message.get("content"), 500),
            )
        else:
            logger.info(
                "message agent=%s step=%s type=%s content=%s",
                agent_name,
                index,
                kind,
                preview(message.get("content"), 300),
            )


def run_agent(
    name: str,
    system_prompt: str,
    human: str,
    tools: list[BaseTool],
) -> dict:
    agent = create_agent(
        get_client(config),
        tools=tools,
        system_prompt=system_prompt,
        name=name,
    )
    result = agent.invoke({"messages": [as_human(human)]})
    messages: list[BaseMessage] = list(result.get("messages") or [])
    return {
        "name": name,
        "messages": serialize_messages(messages),
        "_messages": messages,
    }


def public_trace(run: dict) -> dict:
    return {
        "name": run["name"],
        "messages": run["messages"],
    }
