"""Pydantic schemas for ``solution.yaml``.

These models are the source of truth for the config-first contract. They
validate the YAML *before* the agent is constructed so that bad config
fails closed.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """Risk classes that drive the approval policy."""

    READ_ONLY = "read_only"
    DRAFT_ONLY = "draft_only"
    INTERNAL_WRITE = "internal_write"
    INTERNAL_SIDE_EFFECT = "internal_side_effect"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    SENSITIVE_ACTION = "sensitive_action"


class Decision(str, Enum):
    """Decisions a human reviewer can take when interrupted."""

    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


# Tool risk classes that always require approval before execution.
APPROVAL_REQUIRED_RISKS: frozenset[RiskLevel] = frozenset(
    {
        RiskLevel.INTERNAL_WRITE,
        RiskLevel.INTERNAL_SIDE_EFFECT,
        RiskLevel.EXTERNAL_SIDE_EFFECT,
        RiskLevel.SENSITIVE_ACTION,
    }
)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


class ModelConfig(BaseModel):
    """Logical model declaration resolved by ``MockLLMGateway``."""

    logical_name: str = Field(..., min_length=1)
    temperature: float = Field(0.1, ge=0.0, le=2.0)
    provider_model: str = Field(
        ...,
        description="Concrete provider:model string, e.g. 'anthropic:claude-sonnet-4-6'.",
    )


class PromptConfig(BaseModel):
    system_prompt_ref: str = Field(..., min_length=1)
    response_format: str | None = None


class KnowledgeSourceConfig(BaseModel):
    id: str = Field(..., min_length=1)
    type: Literal["mock_rag"] = "mock_rag"
    path: str = Field(..., min_length=1)


class ToolConfig(BaseModel):
    name: str = Field(..., min_length=1)
    adapter: Literal["mock_ticketing", "mock_knowledge", "mock_notification"]
    risk: RiskLevel
    approval_required: bool = False
    allowed_decisions: list[Decision] | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _consistency(self) -> "ToolConfig":
        risk_requires_approval = self.risk in APPROVAL_REQUIRED_RISKS
        if risk_requires_approval and not self.approval_required:
            raise ValueError(
                f"Tool '{self.name}' has risk '{self.risk.value}' which requires "
                "approval_required=True."
            )
        if not risk_requires_approval and self.approval_required:
            raise ValueError(
                f"Tool '{self.name}' is risk '{self.risk.value}' (no mutation) "
                "but approval_required=True."
            )
        if self.approval_required:
            if not self.allowed_decisions:
                raise ValueError(
                    f"Tool '{self.name}' requires approval but no "
                    "allowed_decisions are configured."
                )
            if Decision.APPROVE not in self.allowed_decisions:
                raise ValueError(
                    f"Tool '{self.name}' must include 'approve' in allowed_decisions."
                )
        elif self.allowed_decisions:
            raise ValueError(
                f"Tool '{self.name}' has allowed_decisions but approval_required=False."
            )
        return self


class SubagentConfig(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    system_prompt_ref: str = Field(..., min_length=1)
    tools: list[str] = Field(default_factory=list)


class BackendMemoryConfig(BaseModel):
    enabled: bool = True
    route: str = "/memories/"
    scope: Literal["user", "thread", "global"] = "user"


class BackendWorkspaceConfig(BaseModel):
    route: str = "/workspace/"
    type: Literal["state"] = "state"


class BackendConfig(BaseModel):
    default: Literal["state", "store", "composite"] = "state"
    memory: BackendMemoryConfig = Field(default_factory=BackendMemoryConfig)
    workspace: BackendWorkspaceConfig = Field(default_factory=BackendWorkspaceConfig)


class MemoryConfig(BaseModel):
    files: list[str] = Field(default_factory=list)
    writable: bool = False


class FilesystemPermissionConfig(BaseModel):
    operations: list[Literal["read", "write"]]
    paths: list[str]
    mode: Literal["allow", "deny", "interrupt"] = "allow"


class PermissionsConfig(BaseModel):
    filesystem: list[FilesystemPermissionConfig] = Field(default_factory=list)


class GuardrailConfig(BaseModel):
    input: list[str] = Field(default_factory=list)
    output: list[str] = Field(default_factory=list)
    tool_call: list[str] = Field(default_factory=list)


class ObservabilityConfig(BaseModel):
    enabled: bool = True
    log_model_calls: bool = True
    log_tool_calls: bool = True
    log_human_approvals: bool = True
    log_subagents: bool = True
    output_path: str = ".runs/events.jsonl"


class EvaluationConfig(BaseModel):
    dataset: str = Field(..., min_length=1)
    checks: list[str] = Field(default_factory=list)


class KnowledgeConfig(BaseModel):
    sources: list[KnowledgeSourceConfig] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


class SolutionConfig(BaseModel):
    """Top-level ``solution.yaml`` model."""

    solution_id: str = Field(..., min_length=1)
    solution_name: str = Field(..., min_length=1)
    runtime: Literal["deepagents"] = "deepagents"
    environment: Literal["prototype", "staging", "production"] = "prototype"

    model: ModelConfig
    prompt: PromptConfig
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    tools: list[ToolConfig]
    subagents: list[SubagentConfig] = Field(default_factory=list)
    backend: BackendConfig = Field(default_factory=BackendConfig)
    skills: list[str] = Field(default_factory=list)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    guardrails: GuardrailConfig = Field(default_factory=GuardrailConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    evaluation: EvaluationConfig | None = None

    @model_validator(mode="after")
    def _cross_reference(self) -> "SolutionConfig":
        tool_names = {t.name for t in self.tools}
        if len(tool_names) != len(self.tools):
            seen: set[str] = set()
            dupes: list[str] = []
            for t in self.tools:
                if t.name in seen:
                    dupes.append(t.name)
                seen.add(t.name)
            raise ValueError(f"Duplicate tool names: {sorted(set(dupes))}")

        sub_names = {s.name for s in self.subagents}
        if len(sub_names) != len(self.subagents):
            raise ValueError("Duplicate subagent names")

        for sub in self.subagents:
            unknown = [t for t in sub.tools if t not in tool_names]
            if unknown:
                raise ValueError(
                    f"Subagent '{sub.name}' references undeclared tools: {unknown}"
                )

        return self

    def tool_by_name(self, name: str) -> ToolConfig | None:
        for t in self.tools:
            if t.name == name:
                return t
        return None

    def model_dump_yaml_safe(self) -> dict[str, Any]:
        """Return a YAML-serialisable dict (enums become their values)."""

        return self.model_dump(mode="json")
