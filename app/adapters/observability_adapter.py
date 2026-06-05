"""Mock observability adapter.

Append-only JSONL logger. The minimum event types are listed in the
prototype context. Each event includes ``thread_id``, ``request_id``,
``solution_id``, and ``timestamp``.

The runner is responsible for creating one ``RunLogger`` per agent run
and passing it down to the components that need to log (tools, HITL
helper, guardrail middleware).
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas import ObservabilityConfig


@dataclass
class RunContext:
    solution_id: str
    thread_id: str
    request_id: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


@dataclass
class _JsonlSink:
    path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def write(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


class MockObservabilityAdapter:
    """Builds run-scoped loggers and reads back JSONL events."""

    def __init__(self, config: ObservabilityConfig | dict[str, Any]) -> None:
        if isinstance(config, dict):
            config = ObservabilityConfig.model_validate(config)
        self.config = config
        self._sink = _JsonlSink(path=Path(config.output_path).resolve())

    @property
    def output_path(self) -> Path:
        return self._sink.path

    # ------------------------------------------------------------------
    # Run logger
    # ------------------------------------------------------------------

    def run_logger(self, ctx: RunContext) -> "RunLogger":
        return RunLogger(sink=self._sink, ctx=ctx, enabled=self.config.enabled)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_events(self) -> list[dict[str, Any]]:
        if not self.output_path.is_file():
            return []
        events: list[dict[str, Any]] = []
        for line in self.output_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def truncate(self) -> None:
        """Clear the log file (used by eval/tests)."""

        if self.output_path.is_file():
            self.output_path.unlink()

    # ------------------------------------------------------------------
    # Middleware (interface symmetry; runner logs directly for prototype)
    # ------------------------------------------------------------------

    def build_middleware(self, config: dict[str, Any] | None = None) -> list[Any]:
        return []


@dataclass
class RunLogger:
    sink: _JsonlSink
    ctx: RunContext
    enabled: bool = True

    def log(self, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        record = {
            "event": event,
            "timestamp": _now(),
            "solution_id": self.ctx.solution_id,
            "thread_id": self.ctx.thread_id,
            "request_id": self.ctx.request_id,
            **fields,
        }
        self.sink.write(record)
