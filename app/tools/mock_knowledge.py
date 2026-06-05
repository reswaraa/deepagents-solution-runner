"""Mock knowledge / RAG tools.

The search functions are intentionally simple: keyword scoring over
chunked Markdown / JSON. The point of the prototype is to prove the
config-first wiring, not to ship a real retriever.

Tool factories accept a :class:`MockKnowledgeAdapter` so the same code
can be used against different solution folders.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.adapters.knowledge_adapter import MockKnowledgeAdapter


class SearchArgs(BaseModel):
    query: str = Field(..., description="Free-text search query.")
    limit: int = Field(3, ge=1, le=10, description="Max number of hits to return.")


def _make_search_tool(
    *,
    name: str,
    description: str,
    source_id: str,
    adapter: "MockKnowledgeAdapter",
) -> StructuredTool:
    def _search(query: str, limit: int = 3) -> dict[str, Any]:
        hits = adapter.search(source_id, query, limit=limit)
        return {
            "status": "success",
            "source": source_id,
            "query": query,
            "hits": hits,
        }

    return StructuredTool.from_function(
        name=name,
        description=description,
        func=_search,
        args_schema=SearchArgs,
    )


def build_search_sop_tool(adapter: "MockKnowledgeAdapter") -> StructuredTool:
    return _make_search_tool(
        name="search_sop",
        description=(
            "Search the approved IT incident SOP for the most relevant "
            "section. Read-only."
        ),
        source_id="it_incident_sop",
        adapter=adapter,
    )


def build_search_service_catalog_tool(
    adapter: "MockKnowledgeAdapter",
) -> StructuredTool:
    return _make_search_tool(
        name="search_service_catalog",
        description=(
            "Search the internal service catalog for owners, tiers, and "
            "escalation groups. Read-only."
        ),
        source_id="service_catalog",
        adapter=adapter,
    )


def build_search_similar_incidents_tool(
    adapter: "MockKnowledgeAdapter",
) -> StructuredTool:
    return _make_search_tool(
        name="search_similar_incidents",
        description=(
            "Search historical incidents for cases similar to the current "
            "ticket. Read-only."
        ),
        source_id="historical_incidents",
        adapter=adapter,
    )
