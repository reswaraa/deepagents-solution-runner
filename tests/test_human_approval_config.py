"""Tests for the generated interrupt_on / approval configuration."""
from __future__ import annotations

from pathlib import Path

from app.adapters.governance_adapter import MockGovernanceAdapter
from app.config_loader import load_solution

SOLUTION = (
    Path(__file__).resolve().parent.parent
    / "solutions"
    / "it_incident_resolution"
    / "solution.yaml"
)


def test_only_write_tools_are_approval_gated() -> None:
    loaded = load_solution(SOLUTION)
    gov = MockGovernanceAdapter()
    approval_needed = set(gov.approval_required_tool_names(loaded.config.tools))
    assert approval_needed == {"update_ticket", "escalate_ticket", "notify_team"}


def test_read_tools_not_gated() -> None:
    loaded = load_solution(SOLUTION)
    gov = MockGovernanceAdapter()
    interrupt_on = gov.build_interrupt_config(loaded.config.tools)
    for read_tool in [
        "get_ticket",
        "search_sop",
        "search_service_catalog",
        "search_similar_incidents",
        "draft_ticket_update",
    ]:
        assert interrupt_on[read_tool] is False, read_tool
