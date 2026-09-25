import asyncio

from langchain_core.messages import AIMessage

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
