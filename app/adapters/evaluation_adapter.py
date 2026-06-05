"""Mock evaluation adapter.

Deterministic eval runner. Cases live in JSONL files; checks are pure
functions over an event log (the JSONL stream produced by
``MockObservabilityAdapter``) plus the final assistant message.

The first prototype evaluator does **not** call an LLM — all checks
should hold even without a model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config_loader import LoadedSolution


@dataclass
class EvalCase:
    id: str
    input: str
    approval_decisions: list[dict[str, Any]] = field(default_factory=list)
    expected: dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str | None = None


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    checks: list[CheckResult]
    skipped: bool = False
    skipped_reason: str | None = None

    def failure_summary(self) -> str:
        bad = [f"{c.name}: {c.detail or 'failed'}" for c in self.checks if not c.passed]
        return "; ".join(bad)


@dataclass
class EvalReport:
    cases: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed and not c.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.cases if not c.passed and not c.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for c in self.cases if c.skipped)


class MockEvaluationAdapter:
    """Load and run deterministic eval cases."""

    @staticmethod
    def load_cases(loaded: LoadedSolution) -> list[EvalCase]:
        if loaded.config.evaluation is None:
            return []
        path = loaded.resolve(loaded.config.evaluation.dataset)
        cases: list[EvalCase] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            cases.append(
                EvalCase(
                    id=data["id"],
                    input=data["input"],
                    approval_decisions=data.get("approval_decisions", []),
                    expected=data.get("expected", {}),
                )
            )
        return cases

    # ------------------------------------------------------------------
    # Check primitives
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate_case(
        case: EvalCase,
        events: list[dict[str, Any]],
        final_answer: str,
        triggered_guardrails: list[str] | None = None,
    ) -> CaseResult:
        expected = case.expected
        checks: list[CheckResult] = []
        called = _tools_called(events)
        executed = _tools_executed(events)
        approval_for = _approval_requests(events)
        decisions = _approval_decisions(events)

        # must_call_tools
        for tn in expected.get("must_call_tools", []):
            ok = tn in called
            checks.append(
                CheckResult(
                    name=f"must_call:{tn}",
                    passed=ok,
                    detail=None if ok else f"tool '{tn}' was not called",
                )
            )

        # must_not_call_tools
        for tn in expected.get("must_not_call_tools", []):
            ok = tn not in executed
            checks.append(
                CheckResult(
                    name=f"must_not_call:{tn}",
                    passed=ok,
                    detail=None if ok else f"tool '{tn}' was executed but should not be",
                )
            )

        # must_request_approval_before
        for tn in expected.get("must_request_approval_before", []):
            ok = tn in approval_for
            checks.append(
                CheckResult(
                    name=f"must_request_approval_before:{tn}",
                    passed=ok,
                    detail=None
                    if ok
                    else f"no approval_requested event for '{tn}'",
                )
            )

        # must_not_call_without_approval
        for tn in expected.get("must_not_call_without_approval", []):
            if tn in executed:
                approved = decisions.get(tn) == "approve" or decisions.get(tn) == "edit"
                ok = approved
                checks.append(
                    CheckResult(
                        name=f"must_not_call_without_approval:{tn}",
                        passed=ok,
                        detail=None
                        if ok
                        else f"'{tn}' executed without an approve/edit decision",
                    )
                )
            else:
                checks.append(
                    CheckResult(
                        name=f"must_not_call_without_approval:{tn}",
                        passed=True,
                    )
                )

        # final_answer_must_include
        for needle in expected.get("final_answer_must_include", []):
            ok = needle.lower() in final_answer.lower()
            checks.append(
                CheckResult(
                    name=f"final_includes:{needle}",
                    passed=ok,
                    detail=None
                    if ok
                    else f"final answer missing required text: '{needle}'",
                )
            )

        # guardrail_must_trigger
        triggered = set(triggered_guardrails or [])
        for gn in expected.get("guardrail_must_trigger", []):
            ok = gn in triggered
            checks.append(
                CheckResult(
                    name=f"guardrail_triggered:{gn}",
                    passed=ok,
                    detail=None
                    if ok
                    else f"expected guardrail '{gn}' did not trigger",
                )
            )

        passed = all(c.passed for c in checks)
        return CaseResult(case_id=case.id, passed=passed, checks=checks)


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------


def _tools_called(events: list[dict[str, Any]]) -> set[str]:
    return {
        e["tool_name"]
        for e in events
        if e.get("event") == "tool_called" and e.get("tool_name")
    }


def _tools_executed(events: list[dict[str, Any]]) -> set[str]:
    return {
        e["tool_name"]
        for e in events
        if e.get("event") in {"tool_result", "action_executed"}
        and e.get("tool_name")
    }


def _approval_requests(events: list[dict[str, Any]]) -> set[str]:
    return {
        e["tool_name"]
        for e in events
        if e.get("event") == "approval_requested" and e.get("tool_name")
    }


def _approval_decisions(events: list[dict[str, Any]]) -> dict[str, str]:
    """Map tool_name → last decision (approve/edit/reject)."""

    out: dict[str, str] = {}
    for e in events:
        if e.get("event") == "approval_decision" and e.get("tool_name"):
            out[e["tool_name"]] = e.get("decision", "")
    return out
