"""Mock notification tool.

Sends nothing externally — records to an in-memory log. The list of
allowed channels is loaded from the service catalog at construction
time so guardrails stay in sync with config.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

_NOTIFICATION_LOG: list[dict[str, Any]] = []
_ALLOWED_CHANNELS: set[str] = {"#incident-room", "#status-public", "#ops-noise"}


def reset_notification_state() -> None:
    global _NOTIFICATION_LOG
    _NOTIFICATION_LOG = []


def set_allowed_channels(channels: list[str] | set[str]) -> None:
    """Configure the allowlist of notification channels."""

    global _ALLOWED_CHANNELS
    _ALLOWED_CHANNELS = set(channels)


def get_notification_log() -> list[dict[str, Any]]:
    return copy.deepcopy(_NOTIFICATION_LOG)


class NotifyTeamArgs(BaseModel):
    channel: str = Field(..., description="Channel name, e.g. #incident-room.")
    message: str = Field(..., description="Notification body.")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def notify_team_impl(channel: str, message: str) -> dict[str, Any]:
    if not message or not message.strip():
        return {"status": "error", "error": "empty_message"}
    if channel not in _ALLOWED_CHANNELS:
        return {
            "status": "error",
            "error": "channel_not_allowed",
            "channel": channel,
            "allowed": sorted(_ALLOWED_CHANNELS),
        }
    entry = {
        "channel": channel,
        "message": message.strip(),
        "timestamp": _now(),
    }
    _NOTIFICATION_LOG.append(entry)
    return {"status": "success", "notification": entry}


def build_notify_team_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="notify_team",
        description=(
            "Post a mock notification to an allowed channel. Channel "
            "must be in the service catalog allowlist. Requires human "
            "approval."
        ),
        func=notify_team_impl,
        args_schema=NotifyTeamArgs,
    )
