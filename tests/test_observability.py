"""Tests for the mock observability adapter."""
from __future__ import annotations

from pathlib import Path

from app.adapters.observability_adapter import (
    MockObservabilityAdapter,
    RunContext,
)
from app.schemas import ObservabilityConfig


def test_jsonl_round_trip(tmp_path: Path) -> None:
    log_path = tmp_path / "out.jsonl"
    adapter = MockObservabilityAdapter(
        ObservabilityConfig(output_path=str(log_path))
    )
    logger = adapter.run_logger(
        RunContext(solution_id="s", thread_id="t1", request_id="r1")
    )
    logger.log("run_started")
    logger.log("tool_called", tool_name="get_ticket", tool_args={"ticket_id": "INC-1"})
    logger.log("run_completed")

    events = adapter.read_events()
    assert len(events) == 3
    assert events[0]["event"] == "run_started"
    assert events[1]["tool_name"] == "get_ticket"
    assert all("timestamp" in e for e in events)
    assert all(e["thread_id"] == "t1" for e in events)


def test_truncate(tmp_path: Path) -> None:
    log_path = tmp_path / "out.jsonl"
    adapter = MockObservabilityAdapter(
        ObservabilityConfig(output_path=str(log_path))
    )
    logger = adapter.run_logger(
        RunContext(solution_id="s", thread_id="t1", request_id="r1")
    )
    logger.log("run_started")
    adapter.truncate()
    assert adapter.read_events() == []


def test_disabled_skips_writes(tmp_path: Path) -> None:
    log_path = tmp_path / "out.jsonl"
    adapter = MockObservabilityAdapter(
        ObservabilityConfig(output_path=str(log_path), enabled=False)
    )
    logger = adapter.run_logger(
        RunContext(solution_id="s", thread_id="t1", request_id="r1")
    )
    logger.log("run_started")
    assert adapter.read_events() == []
