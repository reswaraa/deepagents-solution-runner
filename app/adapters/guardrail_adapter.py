"""Mock guardrail adapter.

Provides simple, deterministic checks (input / tool-call / output) that
the runtime can use to gate behaviour. Each guardrail is a tiny pure
function with a stable name so it can be referenced from
``solution.yaml`` and from the eval expectations.

The middleware wiring is intentionally minimal — for the prototype we
return a single ``AgentMiddleware`` subclass that runs the configured
guardrails. If the installed deepagents/langchain version's middleware
API changes, only ``build_middleware`` needs to change.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.schemas import GuardrailConfig

# ---------------------------------------------------------------------------
# Guardrail registry (deterministic pure functions)
# ---------------------------------------------------------------------------

_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore (the )?previous instructions", re.IGNORECASE),
    re.compile(r"disregard (the )?(prior|above) instructions", re.IGNORECASE),
    re.compile(r"reveal (your )?system prompt", re.IGNORECASE),
    re.compile(r"override (the )?(safety|policy)", re.IGNORECASE),
]

_SENSITIVE_DATA_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
]

_TICKET_ID_RE = re.compile(r"^INC-\d+$")
_REQUEST_ID_RE = re.compile(r"^REQ-\d+$")


@dataclass
class GuardrailResult:
    name: str
    triggered: bool
    detail: str | None = None


# Input guardrails -----------------------------------------------------------


def block_prompt_injection(message: str) -> GuardrailResult:
    for pat in _PROMPT_INJECTION_PATTERNS:
        if pat.search(message):
            return GuardrailResult(
                name="block_prompt_injection",
                triggered=True,
                detail=f"matched pattern: {pat.pattern}",
            )
    return GuardrailResult(name="block_prompt_injection", triggered=False)


def detect_sensitive_data(message: str) -> GuardrailResult:
    for pat in _SENSITIVE_DATA_PATTERNS:
        if pat.search(message):
            return GuardrailResult(
                name="detect_sensitive_data",
                triggered=True,
                detail="possible secret-like string in input",
            )
    return GuardrailResult(name="detect_sensitive_data", triggered=False)


# Tool-call guardrails -------------------------------------------------------


def validate_ticket_id(args: dict[str, Any]) -> GuardrailResult:
    tid = args.get("ticket_id")
    if tid is None:
        return GuardrailResult(
            name="validate_ticket_id", triggered=False
        )
    if not isinstance(tid, str) or not _TICKET_ID_RE.match(tid):
        return GuardrailResult(
            name="validate_ticket_id",
            triggered=True,
            detail=f"invalid ticket id: {tid!r}",
        )
    return GuardrailResult(name="validate_ticket_id", triggered=False)


def validate_escalation_group(
    args: dict[str, Any],
    allowed_groups: set[str] | None = None,
) -> GuardrailResult:
    group = args.get("group")
    if group is None:
        return GuardrailResult(name="validate_escalation_group", triggered=False)
    if allowed_groups and group not in allowed_groups:
        return GuardrailResult(
            name="validate_escalation_group",
            triggered=True,
            detail=f"escalation group not in catalog: {group!r}",
        )
    return GuardrailResult(name="validate_escalation_group", triggered=False)


def non_empty_ticket_comment(args: dict[str, Any]) -> GuardrailResult:
    if "comment" not in args:
        return GuardrailResult(name="non_empty_ticket_comment", triggered=False)
    comment = args.get("comment")
    if not isinstance(comment, str) or not comment.strip():
        return GuardrailResult(
            name="non_empty_ticket_comment",
            triggered=True,
            detail="empty ticket comment",
        )
    return GuardrailResult(name="non_empty_ticket_comment", triggered=False)


def allowed_notification_channel(
    args: dict[str, Any],
    allowed_channels: set[str] | None = None,
) -> GuardrailResult:
    channel = args.get("channel")
    if channel is None:
        return GuardrailResult(name="allowed_notification_channel", triggered=False)
    if allowed_channels and channel not in allowed_channels:
        return GuardrailResult(
            name="allowed_notification_channel",
            triggered=True,
            detail=f"channel not in allowlist: {channel!r}",
        )
    return GuardrailResult(name="allowed_notification_channel", triggered=False)


def validate_request_id(args: dict[str, Any]) -> GuardrailResult:
    rid = args.get("request_id")
    if rid is None:
        return GuardrailResult(name="validate_request_id", triggered=False)
    if not isinstance(rid, str) or not _REQUEST_ID_RE.match(rid):
        return GuardrailResult(
            name="validate_request_id",
            triggered=True,
            detail=f"invalid request id: {rid!r}",
        )
    return GuardrailResult(name="validate_request_id", triggered=False)


def non_empty_justification(args: dict[str, Any]) -> GuardrailResult:
    if "justification" not in args:
        return GuardrailResult(name="non_empty_justification", triggered=False)
    justification = args.get("justification")
    if not isinstance(justification, str) or not justification.strip():
        return GuardrailResult(
            name="non_empty_justification",
            triggered=True,
            detail="empty justification in access change draft",
        )
    return GuardrailResult(name="non_empty_justification", triggered=False)


# Output guardrails ----------------------------------------------------------


def require_sop_reference(answer: str) -> GuardrailResult:
    text = answer.lower()
    if "sop" in text or "section" in text or "policy" in text:
        return GuardrailResult(name="require_sop_reference", triggered=False)
    return GuardrailResult(
        name="require_sop_reference",
        triggered=True,
        detail="final answer does not reference SOP/policy",
    )


def no_fake_action_claims(
    answer: str,
    executed_tools: set[str] | None = None,
) -> GuardrailResult:
    executed_tools = executed_tools or set()
    text = answer.lower()
    claims_update = (
        "ticket updated" in text
        or "updated the ticket" in text
        or "comment posted" in text
    )
    claims_escalation = (
        "escalated" in text and "escalated to" in text
    )
    claims_notification = (
        "notified" in text or "notification sent" in text
    )
    triggered_for: list[str] = []
    if claims_update and "update_ticket" not in executed_tools:
        triggered_for.append("update_ticket")
    if claims_escalation and "escalate_ticket" not in executed_tools:
        triggered_for.append("escalate_ticket")
    if claims_notification and "notify_team" not in executed_tools:
        triggered_for.append("notify_team")
    if triggered_for:
        return GuardrailResult(
            name="no_fake_action_claims",
            triggered=True,
            detail=f"claimed actions without execution: {triggered_for}",
        )
    return GuardrailResult(name="no_fake_action_claims", triggered=False)


def require_policy_reference(answer: str) -> GuardrailResult:
    text = answer.lower()
    if "policy" in text or "section" in text or "tier" in text:
        return GuardrailResult(name="require_policy_reference", triggered=False)
    return GuardrailResult(
        name="require_policy_reference",
        triggered=True,
        detail="final answer does not reference access policy or system tier",
    )


def no_fake_provisioning_claims(
    answer: str,
    executed_tools: set[str] | None = None,
) -> GuardrailResult:
    executed_tools = executed_tools or set()
    text = answer.lower()
    claims_grant = (
        "access granted" in text
        or "granted access" in text
        or "provisioned" in text
    )
    claims_revoke = (
        "access revoked" in text
        or "revoked access" in text
        or "deprovisioned" in text
    )
    triggered_for: list[str] = []
    if claims_grant and "grant_access" not in executed_tools:
        triggered_for.append("grant_access")
    if claims_revoke and "revoke_access" not in executed_tools:
        triggered_for.append("revoke_access")
    if triggered_for:
        return GuardrailResult(
            name="no_fake_provisioning_claims",
            triggered=True,
            detail=f"claimed provisioning actions without execution: {triggered_for}",
        )
    return GuardrailResult(name="no_fake_provisioning_claims", triggered=False)


# ---------------------------------------------------------------------------
# Registry & adapter
# ---------------------------------------------------------------------------


_INPUT_GUARDRAILS: dict[str, Callable[[str], GuardrailResult]] = {
    "block_prompt_injection": block_prompt_injection,
    "detect_sensitive_data": detect_sensitive_data,
}

_TOOL_CALL_GUARDRAILS: dict[str, Callable[..., GuardrailResult]] = {
    "validate_ticket_id": lambda args, ctx=None: validate_ticket_id(args),
    "validate_escalation_group": lambda args, ctx=None: validate_escalation_group(
        args, allowed_groups=(ctx or {}).get("allowed_groups")
    ),
    "non_empty_ticket_comment": lambda args, ctx=None: non_empty_ticket_comment(args),
    "allowed_notification_channel": lambda args, ctx=None: allowed_notification_channel(
        args, allowed_channels=(ctx or {}).get("allowed_channels")
    ),
    # Employee Access Provisioning guardrails
    "validate_request_id": lambda args, ctx=None: validate_request_id(args),
    "non_empty_justification": lambda args, ctx=None: non_empty_justification(args),
}

_OUTPUT_GUARDRAILS: dict[str, Callable[..., GuardrailResult]] = {
    "require_sop_reference": lambda ans, ctx=None: require_sop_reference(ans),
    "no_fake_action_claims": lambda ans, ctx=None: no_fake_action_claims(
        ans, executed_tools=(ctx or {}).get("executed_tools")
    ),
    # Employee Access Provisioning guardrails
    "require_policy_reference": lambda ans, ctx=None: require_policy_reference(ans),
    "no_fake_provisioning_claims": lambda ans, ctx=None: no_fake_provisioning_claims(
        ans, executed_tools=(ctx or {}).get("executed_tools")
    ),
}


class MockGuardrailAdapter:
    """Run the configured deterministic guardrails."""

    def __init__(self, config: GuardrailConfig | dict[str, Any]) -> None:
        if isinstance(config, dict):
            config = GuardrailConfig.model_validate(config)
        self.config = config

    # ------------------------------------------------------------------
    # Run individual guardrails
    # ------------------------------------------------------------------

    def check_input(self, message: str) -> list[GuardrailResult]:
        out: list[GuardrailResult] = []
        for name in self.config.input:
            fn = _INPUT_GUARDRAILS.get(name)
            if fn is None:
                continue
            out.append(fn(message))
        return out

    def check_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> list[GuardrailResult]:
        out: list[GuardrailResult] = []
        for name in self.config.tool_call:
            fn = _TOOL_CALL_GUARDRAILS.get(name)
            if fn is None:
                continue
            out.append(fn(args, context))
        return out

    def check_output(
        self,
        answer: str,
        context: dict[str, Any] | None = None,
    ) -> list[GuardrailResult]:
        out: list[GuardrailResult] = []
        for name in self.config.output:
            fn = _OUTPUT_GUARDRAILS.get(name)
            if fn is None:
                continue
            out.append(fn(answer, context))
        return out

    # ------------------------------------------------------------------
    # Middleware (best-effort; runtime may not call all guardrails)
    # ------------------------------------------------------------------

    def build_middleware(self, config: dict[str, Any] | None = None) -> list[Any]:
        """Return a list of AgentMiddleware objects.

        For the prototype we don't wire middleware into the agent —
        guardrails are invoked from the runner where we have a clear
        view of inputs, tool calls, and final answers. This method is
        kept for interface symmetry with the future Central AI Kitchen
        guardrail service.
        """

        return []


def known_guardrails() -> dict[str, list[str]]:
    return {
        "input": sorted(_INPUT_GUARDRAILS.keys()),
        "tool_call": sorted(_TOOL_CALL_GUARDRAILS.keys()),
        "output": sorted(_OUTPUT_GUARDRAILS.keys()),
    }
