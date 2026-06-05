"""Mock memory adapter.

Provides a checkpointer (required for HITL), an in-memory store, and
the backend used by DeepAgents for its virtual filesystem.

Real Central AI Kitchen memory would back this with Postgres / Redis;
here we use the in-memory variants shipped with langgraph.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas import BackendConfig


@dataclass
class MemoryWiring:
    backend: Any
    store: Any
    checkpointer: Any


class MockMemoryAdapter:
    def build(self, backend_cfg: BackendConfig | dict[str, Any]) -> MemoryWiring:
        if isinstance(backend_cfg, dict):
            backend_cfg = BackendConfig.model_validate(backend_cfg)

        # Lazy imports so unit tests that don't need a backend can run
        # even on minimal installs.
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        checkpointer = InMemorySaver()

        backend: Any = None
        try:
            from deepagents.backends import StateBackend, StoreBackend
            from deepagents.backends.composite import CompositeBackend
        except Exception:  # pragma: no cover - defensive
            return MemoryWiring(backend=None, store=store, checkpointer=checkpointer)

        if backend_cfg.default == "store":
            backend = StoreBackend(store=store)
        elif backend_cfg.default == "composite" and backend_cfg.memory.enabled:
            # Workspace files go to state; memory namespace goes to store.
            backend = CompositeBackend(
                routes={
                    backend_cfg.workspace.route: StateBackend(),
                    backend_cfg.memory.route: StoreBackend(store=store),
                }
            )
        else:
            backend = StateBackend()

        return MemoryWiring(
            backend=backend, store=store, checkpointer=checkpointer
        )
