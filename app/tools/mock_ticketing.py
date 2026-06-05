"""Mock ticketing tools.

These tools simulate an internal ticket system. All state lives in
module-level dicts so the prototype stays simple and deterministic; tests
can call :func:`reset_ticketing_state` to start from a known baseline.

The tools are exposed via factory functions (``build_*``) so the
``MockToolRegistry`` can register them with the agent. Each tool returns
structured data with a ``status`` field; the agent must rely on that
field rather than its own confidence.
"""
from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Mock state
# ---------------------------------------------------------------------------

_BASE_TICKETS: dict[str, dict[str, Any]] = {
    "INC-1007": {
        "id": "INC-1007",
        "title": "Payment API latency has breached SLA",
        "service": "payment-api",
        "severity": "SEV-2",
        "status": "open",
        "opened_at": "2026-06-05T08:12:00Z",
        "symptoms": [
            "p95 latency above 1.2s for 25 minutes",
            "Tier-1 service",
        ],
        "comments": [
            {
                "author": "monitoring-bot",
                "timestamp": "2026-06-05T08:12:01Z",
                "body": "Alert: payment-api p95 latency above SLO.",
            }
        ],
        "escalation": None,
        "tags": ["payments", "latency"],
    },
    "INC-1008": {
        "id": "INC-1008",
        "title": "Login error spike",
        "service": "login-service",
        "severity": "SEV-1",
        "status": "open",
        "opened_at": "2026-06-05T09:01:00Z",
        "symptoms": ["401 error spike", "user complaints"],
        "comments": [],
        "escalation": None,
        "tags": ["identity"],
    },
    "INC-1009": {
        "id": "INC-1009",
        "title": "Data pipeline delay",
        "service": "data-pipeline",
        "severity": "SEV-3",
        "status": "open",
        "opened_at": "2026-06-05T07:45:00Z",
        "symptoms": ["data freshness 30 min behind SLA"],
        "comments": [],
        "escalation": None,
        "tags": ["data"],
    },
}

_TICKETS: dict[str, dict[str, Any]] = copy.deepcopy(_BASE_TICKETS)
_DRAFTS: dict[str, list[dict[str, Any]]] = {}


def reset_ticketing_state() -> None:
    """Reset all in-memory ticket state to the baseline."""

    global _TICKETS, _DRAFTS
    _TICKETS = copy.deepcopy(_BASE_TICKETS)
    _DRAFTS = {}


def snapshot_state() -> dict[str, Any]:
    """Return a deep copy of the current ticket / draft state (for tests)."""

    return {
        "tickets": copy.deepcopy(_TICKETS),
        "drafts": copy.deepcopy(_DRAFTS),
    }


_TICKET_ID_RE = re.compile(r"^INC-\d+$")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Pydantic argument models — used so the LLM gets a typed tool schema
# ---------------------------------------------------------------------------


class GetTicketArgs(BaseModel):
    ticket_id: str = Field(..., description="Incident ticket id, e.g. INC-1007.")


class DraftTicketUpdateArgs(BaseModel):
    ticket_id: str = Field(..., description="Incident ticket id, e.g. INC-1007.")
    comment: str = Field(..., description="Proposed update text.")


class UpdateTicketArgs(BaseModel):
    ticket_id: str = Field(..., description="Incident ticket id, e.g. INC-1007.")
    comment: str = Field(..., description="Update comment to post to the ticket.")


class EscalateTicketArgs(BaseModel):
    ticket_id: str = Field(..., description="Incident ticket id, e.g. INC-1007.")
    group: str = Field(
        ...,
        description="Escalation group name from the service catalog, e.g. payments-platform-oncall.",
    )
    reason: str = Field(..., description="One-line reason for escalation.")


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _validate_ticket_id(ticket_id: str) -> str | None:
    if not _TICKET_ID_RE.match(ticket_id):
        return f"invalid_ticket_id_format: expected INC-<digits>, got '{ticket_id}'"
    return None


def get_ticket_impl(ticket_id: str) -> dict[str, Any]:
    err = _validate_ticket_id(ticket_id)
    if err:
        return {"status": "error", "error": err}
    ticket = _TICKETS.get(ticket_id)
    if ticket is None:
        return {"status": "not_found", "ticket_id": ticket_id}
    return {"status": "success", "ticket": copy.deepcopy(ticket)}


def draft_ticket_update_impl(ticket_id: str, comment: str) -> dict[str, Any]:
    err = _validate_ticket_id(ticket_id)
    if err:
        return {"status": "error", "error": err}
    if not comment or not comment.strip():
        return {"status": "error", "error": "empty_comment"}
    if ticket_id not in _TICKETS:
        return {"status": "not_found", "ticket_id": ticket_id}
    draft = {
        "ticket_id": ticket_id,
        "comment": comment.strip(),
        "drafted_at": _now(),
    }
    _DRAFTS.setdefault(ticket_id, []).append(draft)
    return {"status": "success", "draft": draft}


def update_ticket_impl(ticket_id: str, comment: str) -> dict[str, Any]:
    err = _validate_ticket_id(ticket_id)
    if err:
        return {"status": "error", "error": err}
    if not comment or not comment.strip():
        return {"status": "error", "error": "empty_comment"}
    if ticket_id not in _TICKETS:
        return {"status": "not_found", "ticket_id": ticket_id}
    entry = {
        "author": "incident-copilot",
        "timestamp": _now(),
        "body": comment.strip(),
    }
    _TICKETS[ticket_id]["comments"].append(entry)
    return {"status": "success", "ticket_id": ticket_id, "comment": entry}


def escalate_ticket_impl(ticket_id: str, group: str, reason: str) -> dict[str, Any]:
    err = _validate_ticket_id(ticket_id)
    if err:
        return {"status": "error", "error": err}
    if ticket_id not in _TICKETS:
        return {"status": "not_found", "ticket_id": ticket_id}
    if not group or not group.strip():
        return {"status": "error", "error": "empty_group"}
    escalation = {
        "group": group.strip(),
        "reason": reason.strip(),
        "timestamp": _now(),
    }
    _TICKETS[ticket_id]["escalation"] = escalation
    _TICKETS[ticket_id]["status"] = "escalated"
    return {"status": "success", "ticket_id": ticket_id, "escalation": escalation}


# ---------------------------------------------------------------------------
# StructuredTool factories
# ---------------------------------------------------------------------------


def build_get_ticket_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="get_ticket",
        description=(
            "Fetch a mock incident ticket by id. Returns ticket metadata, "
            "current status, comments, and escalation. Read-only."
        ),
        func=get_ticket_impl,
        args_schema=GetTicketArgs,
    )


def build_draft_ticket_update_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="draft_ticket_update",
        description=(
            "Compose a draft ticket update comment without modifying the "
            "ticket. Use this before update_ticket to prepare the text."
        ),
        func=draft_ticket_update_impl,
        args_schema=DraftTicketUpdateArgs,
    )


def build_update_ticket_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="update_ticket",
        description=(
            "Append an update comment to a mock ticket. This mutates "
            "ticket state and requires human approval."
        ),
        func=update_ticket_impl,
        args_schema=UpdateTicketArgs,
    )


def build_escalate_ticket_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="escalate_ticket",
        description=(
            "Escalate a mock ticket to a named oncall group. Mutates "
            "ticket state. Requires human approval."
        ),
        func=escalate_ticket_impl,
        args_schema=EscalateTicketArgs,
    )
