"""Tests for governance / interrupt_on / permissions."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.governance_adapter import GovernanceError, MockGovernanceAdapter
from app.config_loader import load_solution
from app.schemas import (
    Decision,
    FilesystemPermissionConfig,
    PermissionsConfig,
    RiskLevel,
    ToolConfig,
)

SOLUTION = (
    Path(__file__).resolve().parent.parent
    / "solutions"
    / "it_incident_resolution"
    / "solution.yaml"
)


def test_interrupt_config_from_real_solution() -> None:
    loaded = load_solution(SOLUTION)
    gov = MockGovernanceAdapter()
    interrupt_on = gov.build_interrupt_config(loaded.config.tools)
    assert interrupt_on["get_ticket"] is False
    assert interrupt_on["search_sop"] is False
    assert interrupt_on["draft_ticket_update"] is False
    assert isinstance(interrupt_on["update_ticket"], dict)
    assert interrupt_on["update_ticket"]["allowed_decisions"] == [
        "approve",
        "edit",
        "reject",
    ]
    assert interrupt_on["escalate_ticket"]["allowed_decisions"] == [
        "approve",
        "reject",
    ]
    assert interrupt_on["notify_team"]["allowed_decisions"] == [
        "approve",
        "edit",
        "reject",
    ]


def test_sensitive_action_requires_approve_only() -> None:
    spec = ToolConfig(
        name="dangerous",
        adapter="mock_ticketing",
        risk=RiskLevel.SENSITIVE_ACTION,
        approval_required=True,
        allowed_decisions=[Decision.APPROVE, Decision.EDIT],
    )
    gov = MockGovernanceAdapter()
    with pytest.raises(GovernanceError):
        gov.build_interrupt_config([spec])


def test_filesystem_permissions_build() -> None:
    cfg = PermissionsConfig(
        filesystem=[
            FilesystemPermissionConfig(
                operations=["read", "write"], paths=["/workspace/**"], mode="allow"
            ),
            FilesystemPermissionConfig(
                operations=["write"], paths=["/memories/**"], mode="deny"
            ),
        ]
    )
    gov = MockGovernanceAdapter()
    perms = gov.build_filesystem_permissions(cfg)
    assert len(perms) == 2


def test_subagent_policy_blocks_write_tools() -> None:
    tools = [
        ToolConfig(name="search_sop", adapter="mock_knowledge", risk=RiskLevel.READ_ONLY),
        ToolConfig(
            name="update_ticket",
            adapter="mock_ticketing",
            risk=RiskLevel.INTERNAL_WRITE,
            approval_required=True,
            allowed_decisions=[Decision.APPROVE, Decision.REJECT],
        ),
    ]
    gov = MockGovernanceAdapter()
    with pytest.raises(GovernanceError):
        gov.validate_subagent_tool_policy(
            "researcher", ["search_sop", "update_ticket"], tools
        )


def test_subagent_policy_allows_read_tools() -> None:
    tools = [
        ToolConfig(name="search_sop", adapter="mock_knowledge", risk=RiskLevel.READ_ONLY),
    ]
    gov = MockGovernanceAdapter()
    gov.validate_subagent_tool_policy("researcher", ["search_sop"], tools)
