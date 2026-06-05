"""Mock tool registry.

Builds typed LangChain tools from configured ``ToolConfig`` entries. The
registry knows the small fixed set of tools the prototype ships; unknown
tool names fail closed.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool

from app.adapters.knowledge_adapter import MockKnowledgeAdapter
from app.schemas import ToolConfig
from app.tools import mock_knowledge, mock_notification, mock_ticketing


class UnknownToolError(KeyError):
    """Raised when ``solution.yaml`` references a tool name we don't know."""


@dataclass
class BuiltTool:
    name: str
    tool: BaseTool
    config: ToolConfig


_ToolFactory = Callable[["MockToolRegistry"], BaseTool]


def _ticketing_factory(name: str) -> _ToolFactory:
    builders: dict[str, Callable[[], BaseTool]] = {
        "get_ticket": mock_ticketing.build_get_ticket_tool,
        "draft_ticket_update": mock_ticketing.build_draft_ticket_update_tool,
        "update_ticket": mock_ticketing.build_update_ticket_tool,
        "escalate_ticket": mock_ticketing.build_escalate_ticket_tool,
    }

    def _factory(_registry: "MockToolRegistry") -> BaseTool:
        return builders[name]()

    return _factory


def _knowledge_factory(name: str) -> _ToolFactory:
    builders: dict[str, Callable[[MockKnowledgeAdapter], BaseTool]] = {
        "search_sop": mock_knowledge.build_search_sop_tool,
        "search_service_catalog": mock_knowledge.build_search_service_catalog_tool,
        "search_similar_incidents": mock_knowledge.build_search_similar_incidents_tool,
    }

    def _factory(registry: "MockToolRegistry") -> BaseTool:
        if registry.knowledge_adapter is None:
            raise ValueError(
                f"Tool '{name}' requires a knowledge adapter; none was provided."
            )
        return builders[name](registry.knowledge_adapter)

    return _factory


def _notification_factory(name: str) -> _ToolFactory:
    builders: dict[str, Callable[[], BaseTool]] = {
        "notify_team": mock_notification.build_notify_team_tool,
    }

    def _factory(_registry: "MockToolRegistry") -> BaseTool:
        return builders[name]()

    return _factory


# Mapping of (adapter, tool_name) → factory function. New tools must be
# registered here as well as in the YAML schema's tool config.
_TOOL_FACTORIES: dict[tuple[str, str], _ToolFactory] = {
    ("mock_ticketing", "get_ticket"): _ticketing_factory("get_ticket"),
    ("mock_ticketing", "draft_ticket_update"): _ticketing_factory(
        "draft_ticket_update"
    ),
    ("mock_ticketing", "update_ticket"): _ticketing_factory("update_ticket"),
    ("mock_ticketing", "escalate_ticket"): _ticketing_factory("escalate_ticket"),
    ("mock_knowledge", "search_sop"): _knowledge_factory("search_sop"),
    ("mock_knowledge", "search_service_catalog"): _knowledge_factory(
        "search_service_catalog"
    ),
    ("mock_knowledge", "search_similar_incidents"): _knowledge_factory(
        "search_similar_incidents"
    ),
    ("mock_notification", "notify_team"): _notification_factory("notify_team"),
}


class MockToolRegistry:
    """Builds typed LangChain tools for the configured tool specs."""

    def __init__(
        self, knowledge_adapter: MockKnowledgeAdapter | None = None
    ) -> None:
        self.knowledge_adapter = knowledge_adapter
        self._built: dict[str, BuiltTool] = {}

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build_tools(self, tool_configs: list[ToolConfig]) -> list[BaseTool]:
        self._built.clear()
        for spec in tool_configs:
            key = (spec.adapter, spec.name)
            factory = _TOOL_FACTORIES.get(key)
            if factory is None:
                raise UnknownToolError(
                    f"No factory registered for tool '{spec.name}' "
                    f"under adapter '{spec.adapter}'."
                )
            tool = factory(self)
            self._built[spec.name] = BuiltTool(
                name=spec.name, tool=tool, config=spec
            )
        return [bt.tool for bt in self._built.values()]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def tools(self) -> list[BaseTool]:
        return [bt.tool for bt in self._built.values()]

    def tool_names(self) -> list[str]:
        return list(self._built.keys())

    def get(self, name: str) -> BaseTool:
        bt = self._built.get(name)
        if bt is None:
            raise UnknownToolError(f"Tool '{name}' is not configured.")
        return bt.tool

    def tools_for(self, names: list[str]) -> list[BaseTool]:
        out: list[BaseTool] = []
        for n in names:
            out.append(self.get(n))
        return out

    def config_for(self, name: str) -> ToolConfig:
        bt = self._built.get(name)
        if bt is None:
            raise UnknownToolError(f"Tool '{name}' is not configured.")
        return bt.config

    def all_built(self) -> list[BuiltTool]:
        return list(self._built.values())


def supported_tool_names() -> list[str]:
    return sorted({name for (_adapter, name) in _TOOL_FACTORIES.keys()})


def supported_adapters() -> list[str]:
    return sorted({adapter for (adapter, _name) in _TOOL_FACTORIES.keys()})
