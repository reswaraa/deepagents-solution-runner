"""Tests for the DeepAgentSolutionBuilder."""
from __future__ import annotations

from pathlib import Path

from app.config_loader import load_solution
from app.deepagent_builder import DeepAgentSolutionBuilder, RuntimeContext

SOLUTION = (
    Path(__file__).resolve().parent.parent
    / "solutions"
    / "it_incident_resolution"
    / "solution.yaml"
)


def test_build_without_creating_agent() -> None:
    loaded = load_solution(SOLUTION)
    built = DeepAgentSolutionBuilder().build(loaded, skip_agent_creation=True)
    assert built.agent is None
    assert built.resolved_model.provider_model.startswith(("anthropic:", "openai:"))
    assert "update_ticket" in built.interrupt_on
    assert built.interrupt_on["get_ticket"] is False
    assert built.tool_registry.tool_names()


def test_full_build_returns_runnable_agent() -> None:
    loaded = load_solution(SOLUTION)
    built = DeepAgentSolutionBuilder().build(loaded, skip_agent_creation=False)
    # We just check the runtime returned a compiled graph-like object;
    # actual invocation needs LLM credentials and is covered by the
    # integration test.
    assert built.agent is not None
    assert hasattr(built.agent, "invoke")
    assert built.agent.name == "it_incident_resolution_copilot"


def test_runtime_context_defaults() -> None:
    ctx = RuntimeContext(solution_id="x", request_id="r")
    assert ctx.user_id == "anonymous"
    assert ctx.department == "unknown"
