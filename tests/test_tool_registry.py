"""Tests for the mock tool registry."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.knowledge_adapter import MockKnowledgeAdapter
from app.adapters.tool_registry import MockToolRegistry, UnknownToolError
from app.config_loader import load_solution
from app.schemas import RiskLevel, ToolConfig

SOLUTION = (
    Path(__file__).resolve().parent.parent
    / "solutions"
    / "it_incident_resolution"
    / "solution.yaml"
)


@pytest.fixture
def registry() -> MockToolRegistry:
    loaded = load_solution(SOLUTION)
    knowledge = MockKnowledgeAdapter.from_config(loaded)
    reg = MockToolRegistry(knowledge_adapter=knowledge)
    reg.build_tools(loaded.config.tools)
    return reg


def test_builds_all_configured_tools(registry: MockToolRegistry) -> None:
    names = registry.tool_names()
    for required in [
        "get_ticket",
        "search_sop",
        "search_service_catalog",
        "search_similar_incidents",
        "draft_ticket_update",
        "update_ticket",
        "escalate_ticket",
        "notify_team",
    ]:
        assert required in names


def test_subagent_tool_subset(registry: MockToolRegistry) -> None:
    subset = registry.tools_for(["search_sop", "search_service_catalog"])
    assert {t.name for t in subset} == {"search_sop", "search_service_catalog"}


def test_unknown_tool_raises() -> None:
    reg = MockToolRegistry()
    with pytest.raises(UnknownToolError):
        reg.build_tools(
            [
                ToolConfig(
                    name="mystery",
                    adapter="mock_ticketing",
                    risk=RiskLevel.READ_ONLY,
                )
            ]
        )


def test_get_unknown_tool_raises(registry: MockToolRegistry) -> None:
    with pytest.raises(UnknownToolError):
        registry.get("never_registered")
