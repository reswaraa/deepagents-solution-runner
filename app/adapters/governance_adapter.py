"""Mock governance adapter.

Turns the risk/approval config into DeepAgents ``interrupt_on`` and
``FilesystemPermission`` objects. This is the boundary between
declarative ``solution.yaml`` and what the runtime actually enforces.
"""
from __future__ import annotations

from typing import Any

from app.schemas import (
    APPROVAL_REQUIRED_RISKS,
    FilesystemPermissionConfig,
    PermissionsConfig,
    RiskLevel,
    ToolConfig,
)


class GovernanceError(ValueError):
    """Raised when risk/approval config is internally inconsistent."""


class MockGovernanceAdapter:
    """Converts risk/approval config into runtime governance objects."""

    # ------------------------------------------------------------------
    # Interrupt config
    # ------------------------------------------------------------------

    def build_interrupt_config(
        self, tool_configs: list[ToolConfig]
    ) -> dict[str, Any]:
        """Build the ``interrupt_on`` dict expected by ``create_deep_agent``.

        Read-only and draft tools resolve to ``False`` (no interruption).
        Tools whose risk requires approval resolve to an
        :class:`InterruptOnConfig`-shaped dict with their declared
        ``allowed_decisions``.

        ``sensitive_action`` is always approval-only unless the config
        explicitly allows other decisions.
        """

        interrupt_on: dict[str, Any] = {}
        for spec in tool_configs:
            requires = self.requires_approval(spec)
            if not requires:
                interrupt_on[spec.name] = False
                continue

            if spec.risk == RiskLevel.SENSITIVE_ACTION and (
                not spec.allowed_decisions
                or set(d.value for d in spec.allowed_decisions) != {"approve"}
            ):
                raise GovernanceError(
                    f"Tool '{spec.name}' is sensitive_action: only "
                    "['approve'] is allowed unless explicitly overridden."
                )

            interrupt_on[spec.name] = {
                "allowed_decisions": [d.value for d in (spec.allowed_decisions or [])],
                "description": spec.description
                or f"Approve before executing risky tool '{spec.name}'.",
            }
        return interrupt_on

    def requires_approval(self, spec: ToolConfig) -> bool:
        if spec.approval_required:
            return True
        if spec.risk in APPROVAL_REQUIRED_RISKS:
            return True
        return False

    def approval_required_tool_names(
        self, tool_configs: list[ToolConfig]
    ) -> list[str]:
        return [t.name for t in tool_configs if self.requires_approval(t)]

    # ------------------------------------------------------------------
    # Filesystem permissions
    # ------------------------------------------------------------------

    def build_filesystem_permissions(
        self, permissions: PermissionsConfig | dict[str, Any]
    ) -> list[Any]:
        """Build a list of ``FilesystemPermission`` for DeepAgents.

        We import the type lazily so unit tests don't fail if the
        deepagents version we have does not export the symbol.
        """

        if isinstance(permissions, dict):
            permissions = PermissionsConfig.model_validate(permissions)

        try:
            from deepagents import FilesystemPermission  # type: ignore
        except Exception:  # pragma: no cover - defensive
            return [self._permission_to_dict(p) for p in permissions.filesystem]

        out: list[Any] = []
        for p in permissions.filesystem:
            out.append(
                FilesystemPermission(  # type: ignore[call-arg]
                    operations=list(p.operations),
                    paths=list(p.paths),
                    mode=p.mode,
                )
            )
        return out

    @staticmethod
    def _permission_to_dict(p: FilesystemPermissionConfig) -> dict[str, Any]:
        return {
            "operations": list(p.operations),
            "paths": list(p.paths),
            "mode": p.mode,
        }

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def validate_subagent_tool_policy(
        self,
        subagent_name: str,
        subagent_tools: list[str],
        tool_configs: list[ToolConfig],
    ) -> None:
        """Subagents must only receive read/draft tools in the prototype."""

        tool_lookup = {t.name: t for t in tool_configs}
        bad: list[str] = []
        for tn in subagent_tools:
            cfg = tool_lookup.get(tn)
            if cfg is None:
                bad.append(f"{tn} (unknown)")
                continue
            if self.requires_approval(cfg):
                bad.append(f"{tn} ({cfg.risk.value})")
        if bad:
            raise GovernanceError(
                f"Subagent '{subagent_name}' is not allowed to use "
                f"approval-required tools: {bad}"
            )
