import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from document_chat.services.agents import orchestrator


class FakeAgent:
    """Raises a Groq-style tool_use_failed error for the first `failures` runs."""

    def __init__(self, failures: int, answer: str = "ok"):
        self.failures = failures
        self.calls: list[str] = []
        self.answer = answer

    async def astream(self, payload, stream_mode):
        self.calls.append(payload["messages"][0]["content"])
        if len(self.calls) <= self.failures:
            raise RuntimeError(
                "Error code: 400 - tool_use_failed: attempted to call tool 'retrieve' "
                "which was not in request.tools"
            )
        yield "values", {"messages": [AIMessage(content=self.answer)]}


def test_unknown_tool_call_is_retried_with_allowed_tools():
    agent = FakeAgent(failures=1)
    result = asyncio.run(orchestrator._run_agent("synthesis", agent, "question"))
    assert result["answer"] == "ok"
    assert len(agent.calls) == 2
    assert "draft_answer" in agent.calls[1]


class TextOnlyAgent:
    """Rejects list content the way Groq does for text-only models."""

    def __init__(self):
        self.calls: list = []

    async def astream(self, payload, stream_mode):
        content = payload["messages"][0]["content"]
        self.calls.append(content)
        if not isinstance(content, str):
            raise RuntimeError("Error code: 400 - messages[1].content must be a string")
        yield "values", {"messages": [AIMessage(content="seen")]}


def test_image_rejection_falls_back_to_text(monkeypatch):
    monkeypatch.setattr(orchestrator, "_images_rejected", False)
    attachments = [
        {"type": "text", "text": "Image photo.png OCR: PO-1042"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
    ]
    agent = TextOnlyAgent()
    result = asyncio.run(orchestrator._run_agent("vision", agent, "question", [], attachments))
    assert result["answer"] == "seen"
    assert isinstance(agent.calls[1], str) and "PO-1042" in agent.calls[1]
    asyncio.run(orchestrator._run_agent("vision", agent, "again", [], attachments))
    assert isinstance(agent.calls[2], str)


def test_try_agent_returns_none_after_repeated_failure():
    agent = FakeAgent(failures=5)
    assert asyncio.run(orchestrator._try_agent("synthesis", agent, "question")) is None
    assert len(agent.calls) == 2


def test_turn_survives_synthesis_and_verify_failures(monkeypatch):
    monkeypatch.setattr(orchestrator, "planner_agent", FakeAgent(failures=5))
    monkeypatch.setattr(orchestrator, "retrieval_agent", FakeAgent(failures=0, answer="30 days"))
    monkeypatch.setattr(orchestrator, "synthesis_agent", FakeAgent(failures=5))
    monkeypatch.setattr(orchestrator, "verify_agent", FakeAgent(failures=5))
    result = asyncio.run(orchestrator.run_turn("refund window?", [], []))
    assert "30 days" in result["content"]
    assert result["plan"]["need_retrieval"] is True


def test_repeated_query_detection():
    call = lambda query: AIMessage(  # noqa: E731
        content="", tool_calls=[{"name": "retrieval_tool", "args": {"query": query}, "id": query}]
    )
    first = {"messages": [call("Contract ID:")]}
    assert not orchestrator._repeated_query(first, "retrieval_tool", "Contract ID:")
    repeat = {"messages": [call("Contract ID:"), call("contract id")]}
    assert orchestrator._repeated_query(repeat, "retrieval_tool", "contract id")


def test_capped_agent_reports_its_tool_results():
    messages = [
        AIMessage(content="", tool_calls=[{"name": "retrieval_tool", "args": {"query": "a"}, "id": "1"}]),
        ToolMessage(content="[contract_acme.pdf, p. 1] Contract ID: ACME-PO1042-2024", tool_call_id="1"),
        AIMessage(content="", tool_calls=[{"name": "retrieval_tool", "args": {"query": "b"}, "id": "2"}]),
        ToolMessage(content="Tool call limit exceeded. Do not make additional tool calls.", tool_call_id="2"),
        AIMessage(content="Model call limits exceeded: run limit (4/4)"),
    ]
    assert orchestrator._report_text(messages) == "[contract_acme.pdf, p. 1] Contract ID: ACME-PO1042-2024"
    assert orchestrator._report_text([AIMessage(content="Found it.")]) == "Found it."


def test_turn_reports_provider_failure_when_everything_fails(monkeypatch):
    for name in ("planner_agent", "retrieval_agent", "synthesis_agent", "verify_agent"):
        monkeypatch.setattr(orchestrator, name, FakeAgent(failures=5))
    result = asyncio.run(orchestrator.run_turn("refund window?", [], []))
    assert result["unknown"] is True
    assert "rate limit" in result["content"]
