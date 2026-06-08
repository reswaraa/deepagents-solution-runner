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
    assert ":" in built.resolved_model.provider_model
    assert built.resolved_model.provider_model.startswith(
        (
            "anthropic:",
            "openai:",
            "bedrock:",
            "bedrock_converse:",
            "google_genai:",
            "openai_compatible:",
        )
    )
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


def test_subagent_model_override(monkeypatch) -> None:
    """A subagent with its own ``model:`` block is routed to that endpoint.

    Demonstrates the Azure AI Foundry pattern: main agent uses one model,
    subagents that do code-writing or other specialist work use another.
    """

    from app.adapters.llm_gateway import MockLLMGateway
    from app.deepagent_builder import DeepAgentSolutionBuilder

    monkeypatch.setenv("AZURE_KIMI_KEY", "main-fake")
    monkeypatch.setenv("AZURE_DEEPSEEK_KEY", "sub-fake")

    loaded = load_solution(SOLUTION)

    # Patch the top-level model to Kimi
    loaded.config.model.provider_model = "openai_compatible:kimi-k2.6"
    loaded.config.model.base_url = (
        "https://kimi.swedencentral.models.ai.azure.com/v1"
    )
    loaded.config.model.api_key_env = "AZURE_KIMI_KEY"

    # Patch one subagent to use DeepSeek
    from app.schemas import ModelConfig

    loaded.config.subagents[0].model = ModelConfig(
        logical_name="deepseek_flash",
        temperature=0.2,
        provider_model="openai_compatible:deepseek-v4-flash",
        base_url="https://deepseek.swedencentral.models.ai.azure.com/v1",
        api_key_env="AZURE_DEEPSEEK_KEY",
    )

    builder = DeepAgentSolutionBuilder(llm_gateway=MockLLMGateway())
    built = builder.build(loaded, skip_agent_creation=True)
    assert built.resolved_model.provider_model == "openai_compatible:kimi-k2.6"
    assert type(built.resolved_model.model).__name__ == "ChatOpenAI"
    # Verify the resolved subagent model was wired in by re-running the
    # subagent builder against the mutated config.
    spec_list = builder._build_subagents(
        loaded.config.subagents, built.prompt_registry, built.tool_registry
    )
    assert "model" in spec_list[0]
    assert type(spec_list[0]["model"]).__name__ == "ChatOpenAI"
    assert spec_list[0]["model"].model_name == "deepseek-v4-flash"
    # Subagents without an override don't get a model key (inherit main)
    assert "model" not in spec_list[1]
