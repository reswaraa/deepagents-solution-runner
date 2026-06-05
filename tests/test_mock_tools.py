"""Tests for the mock domain tools."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.tools import mock_knowledge, mock_notification, mock_ticketing


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    mock_ticketing.reset_ticketing_state()
    mock_notification.reset_notification_state()
    mock_notification.set_allowed_channels(
        ["#incident-room", "#status-public", "#ops-noise"]
    )
    yield
    mock_ticketing.reset_ticketing_state()
    mock_notification.reset_notification_state()


# --- ticketing --------------------------------------------------------------


def test_get_ticket_success() -> None:
    res = mock_ticketing.get_ticket_impl("INC-1007")
    assert res["status"] == "success"
    assert res["ticket"]["service"] == "payment-api"


def test_get_ticket_invalid_format() -> None:
    res = mock_ticketing.get_ticket_impl("not-a-ticket")
    assert res["status"] == "error"


def test_get_ticket_not_found() -> None:
    res = mock_ticketing.get_ticket_impl("INC-9999")
    assert res["status"] == "not_found"


def test_draft_does_not_mutate_ticket() -> None:
    before = mock_ticketing.snapshot_state()
    res = mock_ticketing.draft_ticket_update_impl(
        "INC-1007", "draft comment"
    )
    after = mock_ticketing.snapshot_state()
    assert res["status"] == "success"
    assert before["tickets"] == after["tickets"]
    assert after["drafts"]["INC-1007"][0]["comment"] == "draft comment"


def test_update_ticket_mutates_only_when_called() -> None:
    before = mock_ticketing.snapshot_state()
    res = mock_ticketing.update_ticket_impl("INC-1007", "diagnosis attached")
    after = mock_ticketing.snapshot_state()
    assert res["status"] == "success"
    assert (
        len(after["tickets"]["INC-1007"]["comments"])
        == len(before["tickets"]["INC-1007"]["comments"]) + 1
    )


def test_update_ticket_rejects_empty_comment() -> None:
    res = mock_ticketing.update_ticket_impl("INC-1007", "   ")
    assert res["status"] == "error"


def test_escalate_ticket_mutates_only_when_called() -> None:
    res = mock_ticketing.escalate_ticket_impl(
        "INC-1007", "payments-platform-oncall", "latency persists"
    )
    state = mock_ticketing.snapshot_state()
    assert res["status"] == "success"
    assert state["tickets"]["INC-1007"]["escalation"]["group"] == (
        "payments-platform-oncall"
    )
    assert state["tickets"]["INC-1007"]["status"] == "escalated"


# --- notification -----------------------------------------------------------


def test_notify_team_success() -> None:
    res = mock_notification.notify_team_impl(
        "#incident-room", "investigating INC-1007"
    )
    assert res["status"] == "success"
    log = mock_notification.get_notification_log()
    assert len(log) == 1


def test_notify_team_disallowed_channel() -> None:
    res = mock_notification.notify_team_impl("#not-a-real", "hi")
    assert res["status"] == "error"
    assert res["error"] == "channel_not_allowed"
    assert mock_notification.get_notification_log() == []


def test_notify_team_empty_message() -> None:
    res = mock_notification.notify_team_impl("#incident-room", "  ")
    assert res["status"] == "error"


# --- knowledge --------------------------------------------------------------


def test_knowledge_search_returns_hits() -> None:
    # Import here to avoid circular imports at collection time
    from app.adapters.knowledge_adapter import MockKnowledgeAdapter
    from app.config_loader import load_solution

    loaded = load_solution(
        Path(__file__).resolve().parent.parent
        / "solutions"
        / "it_incident_resolution"
        / "solution.yaml"
    )
    adapter = MockKnowledgeAdapter.from_config(loaded)
    res = adapter.search("it_incident_sop", "escalation")
    assert res
    assert any("escalat" in h["snippet"].lower() for h in res)


def test_tool_factory_returns_structured_tool() -> None:
    tool = mock_ticketing.build_get_ticket_tool()
    assert tool.name == "get_ticket"
    result = tool.invoke({"ticket_id": "INC-1007"})
    assert result["status"] == "success"
