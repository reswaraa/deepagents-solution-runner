"""Tests for the evaluation adapter."""
from __future__ import annotations

from pathlib import Path

from app.adapters.evaluation_adapter import (
    EvalCase,
    MockEvaluationAdapter,
)
from app.config_loader import load_solution

SOLUTION = (
    Path(__file__).resolve().parent.parent
    / "solutions"
    / "it_incident_resolution"
    / "solution.yaml"
)


def test_load_cases() -> None:
    loaded = load_solution(SOLUTION)
    cases = MockEvaluationAdapter.load_cases(loaded)
    assert len(cases) >= 10
    ids = [c.id for c in cases]
    assert "incident_001_read_only" in ids


def test_evaluate_passes_when_expected_satisfied() -> None:
    case = EvalCase(
        id="x",
        input="hi",
        expected={
            "must_call_tools": ["get_ticket"],
            "must_not_call_tools": ["update_ticket"],
            "must_request_approval_before": ["update_ticket"],
            "must_not_call_without_approval": ["update_ticket"],
            "final_answer_must_include": ["recommended"],
            "guardrail_must_trigger": [],
        },
    )
    events = [
        {"event": "tool_called", "tool_name": "get_ticket"},
        {"event": "tool_result", "tool_name": "get_ticket"},
        {"event": "tool_called", "tool_name": "update_ticket"},
        {"event": "approval_requested", "tool_name": "update_ticket"},
        {"event": "approval_decision", "tool_name": "update_ticket", "decision": "reject"},
    ]
    result = MockEvaluationAdapter.evaluate_case(
        case, events, "I recommended you wait.", triggered_guardrails=[]
    )
    assert result.passed, result.failure_summary()


def test_evaluate_fails_when_tool_not_called() -> None:
    case = EvalCase(
        id="x",
        input="hi",
        expected={"must_call_tools": ["get_ticket"]},
    )
    events = []
    result = MockEvaluationAdapter.evaluate_case(case, events, "")
    assert not result.passed
    assert "must_call:get_ticket" in result.failure_summary()


def test_evaluate_detects_unapproved_execution() -> None:
    case = EvalCase(
        id="x",
        input="hi",
        expected={"must_not_call_without_approval": ["update_ticket"]},
    )
    events = [
        {"event": "tool_called", "tool_name": "update_ticket"},
        {"event": "tool_result", "tool_name": "update_ticket"},
    ]
    result = MockEvaluationAdapter.evaluate_case(case, events, "")
    assert not result.passed


def test_evaluate_records_guardrail_trigger() -> None:
    case = EvalCase(
        id="x",
        input="hi",
        expected={"guardrail_must_trigger": ["block_prompt_injection"]},
    )
    result = MockEvaluationAdapter.evaluate_case(
        case, [], "blocked", triggered_guardrails=["block_prompt_injection"]
    )
    assert result.passed
