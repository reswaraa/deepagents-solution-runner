"""Mock access provisioning tools.

Simulates an internal IAM / access provisioning system. All state lives
in module-level dicts so tests can reset to a known baseline.

Tools follow the same pattern as mock_ticketing: factory functions that
return StructuredTool objects, typed args via Pydantic, and a ``status``
field in every response so the agent cannot guess the outcome.
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

_BASE_REQUESTS: dict[str, dict[str, Any]] = {
    "REQ-2001": {
        "id": "REQ-2001",
        "type": "onboarding",
        "employee_id": "EMP-1042",
        "employee_name": "Alice Chen",
        "department": "Software Engineering",
        "role": "Junior Developer",
        "manager_id": "EMP-0331",
        "start_date": "2026-06-10",
        "requested_systems": ["github-org", "jira", "slack", "vpn-basic"],
        "status": "pending",
        "submitted_at": "2026-06-08T09:00:00Z",
        "notes": [],
        "provisioned_systems": [],
        "revoked_systems": [],
    },
    "REQ-2002": {
        "id": "REQ-2002",
        "type": "role_change",
        "employee_id": "EMP-0774",
        "employee_name": "Bob Martinez",
        "department": "Platform Engineering",
        "role": "Senior DevOps Engineer",
        "previous_role": "IT Support Engineer",
        "manager_id": "EMP-0215",
        "requested_systems": ["aws-console-prod", "kubernetes-dashboard-prod", "datadog"],
        "remove_systems": ["it-helpdesk-portal"],
        "status": "pending",
        "submitted_at": "2026-06-08T10:30:00Z",
        "notes": [],
        "provisioned_systems": [],
        "revoked_systems": [],
    },
    "REQ-2003": {
        "id": "REQ-2003",
        "type": "offboarding",
        "employee_id": "EMP-0512",
        "employee_name": "Carol Tan",
        "department": "Finance",
        "role": "Finance Analyst",
        "last_day": "2026-06-09",
        "systems_to_revoke": [
            "github-org", "jira", "slack", "vpn-basic",
            "finance-reporting", "sap-hana",
        ],
        "status": "pending",
        "submitted_at": "2026-06-08T08:00:00Z",
        "notes": [],
        "provisioned_systems": [],
        "revoked_systems": [],
    },
}

_REQUESTS: dict[str, dict[str, Any]] = copy.deepcopy(_BASE_REQUESTS)
_DRAFTS: dict[str, list[dict[str, Any]]] = {}

_REQUEST_ID_RE = re.compile(r"^REQ-\d+$")


def reset_provisioning_state() -> None:
    global _REQUESTS, _DRAFTS
    _REQUESTS = copy.deepcopy(_BASE_REQUESTS)
    _DRAFTS = {}


def snapshot_state() -> dict[str, Any]:
    return {
        "requests": copy.deepcopy(_REQUESTS),
        "drafts": copy.deepcopy(_DRAFTS),
    }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_request_id(request_id: str) -> str | None:
    if not _REQUEST_ID_RE.match(request_id):
        return f"invalid_request_id_format: expected REQ-<digits>, got '{request_id}'"
    return None


# ---------------------------------------------------------------------------
# Pydantic argument models
# ---------------------------------------------------------------------------


class GetAccessRequestArgs(BaseModel):
    request_id: str = Field(..., description="Access request id, e.g. REQ-2001.")


class DraftAccessChangeArgs(BaseModel):
    request_id: str = Field(..., description="Access request id, e.g. REQ-2001.")
    action: str = Field(
        ...,
        description="Action type: 'grant' or 'revoke'.",
    )
    systems: list[str] = Field(
        ..., description="List of system ids to grant or revoke, e.g. ['github-org', 'slack']."
    )
    justification: str = Field(..., description="Business justification for this change.")


class GrantAccessArgs(BaseModel):
    request_id: str = Field(..., description="Access request id, e.g. REQ-2001.")
    employee_id: str = Field(..., description="Employee id, e.g. EMP-1042.")
    systems: list[str] = Field(
        ..., description="Systems to grant access to, e.g. ['github-org', 'slack']."
    )
    role: str = Field(..., description="Role being provisioned for, e.g. 'Junior Developer'.")


class RevokeAccessArgs(BaseModel):
    request_id: str = Field(..., description="Access request id, e.g. REQ-2001.")
    employee_id: str = Field(..., description="Employee id, e.g. EMP-0512.")
    systems: list[str] = Field(
        ..., description="Systems to revoke access from."
    )
    reason: str = Field(..., description="Reason for revocation, e.g. 'offboarding'.")


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def get_access_request_impl(request_id: str) -> dict[str, Any]:
    err = _validate_request_id(request_id)
    if err:
        return {"status": "error", "error": err}
    req = _REQUESTS.get(request_id)
    if req is None:
        return {"status": "not_found", "request_id": request_id}
    return {"status": "success", "request": copy.deepcopy(req)}


def draft_access_change_impl(
    request_id: str, action: str, systems: list[str], justification: str
) -> dict[str, Any]:
    err = _validate_request_id(request_id)
    if err:
        return {"status": "error", "error": err}
    if not justification or not justification.strip():
        return {"status": "error", "error": "empty_justification"}
    if request_id not in _REQUESTS:
        return {"status": "not_found", "request_id": request_id}
    if action not in {"grant", "revoke"}:
        return {"status": "error", "error": f"invalid_action: must be 'grant' or 'revoke', got '{action}'"}
    draft = {
        "request_id": request_id,
        "action": action,
        "systems": systems,
        "justification": justification.strip(),
        "drafted_at": _now(),
    }
    _DRAFTS.setdefault(request_id, []).append(draft)
    return {"status": "success", "draft": draft}


def grant_access_impl(
    request_id: str, employee_id: str, systems: list[str], role: str
) -> dict[str, Any]:
    err = _validate_request_id(request_id)
    if err:
        return {"status": "error", "error": err}
    if request_id not in _REQUESTS:
        return {"status": "not_found", "request_id": request_id}
    record = {
        "employee_id": employee_id,
        "systems": systems,
        "role": role,
        "granted_at": _now(),
        "operator": "access-provisioning-copilot",
    }
    _REQUESTS[request_id]["provisioned_systems"].extend(systems)
    _REQUESTS[request_id]["status"] = "provisioned"
    return {"status": "success", "request_id": request_id, "grant": record}


def revoke_access_impl(
    request_id: str, employee_id: str, systems: list[str], reason: str
) -> dict[str, Any]:
    err = _validate_request_id(request_id)
    if err:
        return {"status": "error", "error": err}
    if request_id not in _REQUESTS:
        return {"status": "not_found", "request_id": request_id}
    if not reason or not reason.strip():
        return {"status": "error", "error": "empty_reason"}
    record = {
        "employee_id": employee_id,
        "systems": systems,
        "reason": reason.strip(),
        "revoked_at": _now(),
        "operator": "access-provisioning-copilot",
    }
    _REQUESTS[request_id]["revoked_systems"].extend(systems)
    _REQUESTS[request_id]["status"] = "revoked"
    return {"status": "success", "request_id": request_id, "revocation": record}


# ---------------------------------------------------------------------------
# StructuredTool factories
# ---------------------------------------------------------------------------


def build_get_access_request_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="get_access_request",
        description=(
            "Fetch a mock access provisioning request by id. Returns the "
            "employee, role, requested systems, and current status. Read-only."
        ),
        func=get_access_request_impl,
        args_schema=GetAccessRequestArgs,
    )


def build_draft_access_change_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="draft_access_change",
        description=(
            "Compose a draft access change (grant or revoke) without executing it. "
            "Use this before grant_access or revoke_access to prepare the change."
        ),
        func=draft_access_change_impl,
        args_schema=DraftAccessChangeArgs,
    )


def build_grant_access_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="grant_access",
        description=(
            "Grant system access to an employee for the specified systems and role. "
            "Mutates provisioning state. Requires human approval."
        ),
        func=grant_access_impl,
        args_schema=GrantAccessArgs,
    )


def build_revoke_access_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="revoke_access",
        description=(
            "Revoke system access from an employee for the specified systems. "
            "Mutates provisioning state. Requires human approval."
        ),
        func=revoke_access_impl,
        args_schema=RevokeAccessArgs,
    )
