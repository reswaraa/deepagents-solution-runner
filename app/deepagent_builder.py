"""Compile a validated ``SolutionConfig`` into a DeepAgents runtime.

The builder is intentionally thin: every responsibility (knowledge,
tools, prompts, governance, memory) lives in a mock adapter. The
builder wires them into ``create_deep_agent``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.adapters.governance_adapter import MockGovernanceAdapter
from app.adapters.guardrail_adapter import MockGuardrailAdapter
from app.adapters.knowledge_adapter import MockKnowledgeAdapter
from app.adapters.llm_gateway import MockLLMGateway, ResolvedModel
from app.adapters.memory_adapter import MemoryWiring, MockMemoryAdapter
from app.adapters.observability_adapter import MockObservabilityAdapter
from app.adapters.prompt_registry import MockPromptRegistry
from app.adapters.tool_registry import MockToolRegistry
from app.config_loader import LoadedSolution
from app.schemas import SolutionConfig, SubagentConfig


@dataclass
class RuntimeContext:
    """Context object passed alongside every agent invocation.

    Bound to ``context_schema`` so the agent can read it at runtime.
    """

    user_id: str = "anonymous"
    department: str = "unknown"
    solution_id: str = "unknown"
    request_id: str = "unknown"


@dataclass
class BuiltAgent:
    """Everything the runner needs to invoke and observe an agent run."""

    agent: Any
    solution: LoadedSolution
    resolved_model: ResolvedModel
    tool_registry: MockToolRegistry
    knowledge_adapter: MockKnowledgeAdapter
    prompt_registry: MockPromptRegistry
    governance_adapter: MockGovernanceAdapter
    guardrail_adapter: MockGuardrailAdapter
    observability_adapter: MockObservabilityAdapter
    memory: MemoryWiring
    interrupt_on: dict[str, Any] = field(default_factory=dict)
    skill_paths: list[str] = field(default_factory=list)


class DeepAgentSolutionBuilder:
    """Build a DeepAgents agent from a validated solution config."""

    def __init__(
        self,
        *,
        llm_gateway: MockLLMGateway | None = None,
        memory_adapter: MockMemoryAdapter | None = None,
        governance_adapter: MockGovernanceAdapter | None = None,
        guardrail_adapter: MockGuardrailAdapter | None = None,
        observability_adapter: MockObservabilityAdapter | None = None,
    ) -> None:
        self.llm_gateway = llm_gateway or MockLLMGateway()
        self.memory_adapter = memory_adapter or MockMemoryAdapter()
        self.governance_adapter = governance_adapter or MockGovernanceAdapter()
        # Guardrail / observability adapters depend on config; default
        # versions are created in ``build`` if not provided.
        self._explicit_guardrail = guardrail_adapter
        self._explicit_observability = observability_adapter

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(
        self,
        loaded: LoadedSolution,
        *,
        skip_agent_creation: bool = False,
    ) -> BuiltAgent:
        cfg: SolutionConfig = loaded.config

        # 1. Per-solution adapters that need config or paths.
        prompt_registry = MockPromptRegistry(loaded.solution_dir)
        knowledge_adapter = MockKnowledgeAdapter.from_config(loaded)
        tool_registry = MockToolRegistry(knowledge_adapter=knowledge_adapter)
        tool_registry.build_tools(cfg.tools)

        guardrail_adapter = self._explicit_guardrail or MockGuardrailAdapter(
            cfg.guardrails
        )
        observability_adapter = (
            self._explicit_observability
            or MockObservabilityAdapter(cfg.observability)
        )

        # 2. Subagent tool policy check (read-only constraint).
        for sub in cfg.subagents:
            self.governance_adapter.validate_subagent_tool_policy(
                sub.name, sub.tools, cfg.tools
            )

        # 3. Model + prompt + tools + subagents + permissions + interrupts.
        resolved = self.llm_gateway.resolve_model(cfg.model)
        system_prompt = prompt_registry.load(cfg.prompt.system_prompt_ref)
        tools = tool_registry.tools()
        subagents = self._build_subagents(
            cfg.subagents, prompt_registry, tool_registry
        )
        permissions = self.governance_adapter.build_filesystem_permissions(
            cfg.permissions
        )
        interrupt_on = self.governance_adapter.build_interrupt_config(cfg.tools)

        # 4. Backend + store + checkpointer.
        memory = self.memory_adapter.build(cfg.backend)

        # 5. Compose.
        skill_paths = [
            str(loaded.resolve(s)) for s in cfg.skills
        ]

        agent: Any = None
        if not skip_agent_creation:
            agent = self._create_agent(
                cfg=cfg,
                model=resolved.model,
                system_prompt=system_prompt,
                tools=tools,
                subagents=subagents,
                permissions=permissions,
                interrupt_on=interrupt_on,
                memory=memory,
                skill_paths=skill_paths,
            )

        return BuiltAgent(
            agent=agent,
            solution=loaded,
            resolved_model=resolved,
            tool_registry=tool_registry,
            knowledge_adapter=knowledge_adapter,
            prompt_registry=prompt_registry,
            governance_adapter=self.governance_adapter,
            guardrail_adapter=guardrail_adapter,
            observability_adapter=observability_adapter,
            memory=memory,
            interrupt_on=interrupt_on,
            skill_paths=skill_paths,
        )

    # ------------------------------------------------------------------
    # Subagents
    # ------------------------------------------------------------------

    def _build_subagents(
        self,
        sub_configs: list[SubagentConfig],
        prompt_registry: MockPromptRegistry,
        tool_registry: MockToolRegistry,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for sub in sub_configs:
            sub_tools = tool_registry.tools_for(sub.tools)
            spec: dict[str, Any] = {
                "name": sub.name,
                "description": sub.description,
                "system_prompt": prompt_registry.load(sub.system_prompt_ref),
                "tools": sub_tools,
            }
            if sub.model is not None:
                resolved = self.llm_gateway.resolve_model(sub.model)
                # Pass through whatever we resolved — either a string the
                # DeepAgents harness can init itself, or a configured
                # BaseChatModel instance.
                spec["model"] = resolved.model
            out.append(spec)
        return out

    # ------------------------------------------------------------------
    # create_deep_agent — kept isolated for version-compatibility tweaks
    # ------------------------------------------------------------------

    def _create_agent(
        self,
        *,
        cfg: SolutionConfig,
        model: Any,
        system_prompt: str,
        tools: list[Any],
        subagents: list[dict[str, Any]],
        permissions: list[Any],
        interrupt_on: dict[str, Any],
        memory: MemoryWiring,
        skill_paths: list[str],
    ) -> Any:
        # Lazy imports so unit tests can import this module without
        # forcing a particular deepagents version on import.
        from deepagents import create_deep_agent

        kwargs: dict[str, Any] = dict(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            subagents=subagents,
            interrupt_on=interrupt_on,
            checkpointer=memory.checkpointer,
            store=memory.store,
            context_schema=RuntimeContext,
            name=cfg.solution_id,
        )
        if permissions:
            kwargs["permissions"] = permissions
        if memory.backend is not None:
            kwargs["backend"] = memory.backend
        if skill_paths:
            kwargs["skills"] = skill_paths
        if cfg.memory.files:
            kwargs["memory"] = list(cfg.memory.files)
        return create_deep_agent(**kwargs)
