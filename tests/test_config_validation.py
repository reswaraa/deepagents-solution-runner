"""Tests for solution config schema and loader."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.config_loader import ConfigError, load_solution
from app.schemas import (
    APPROVAL_REQUIRED_RISKS,
    Decision,
    RiskLevel,
    SolutionConfig,
    ToolConfig,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SOLUTION = REPO_ROOT / "solutions" / "it_incident_resolution" / "solution.yaml"


def _solution_dict() -> dict:
    return yaml.safe_load(SOLUTION.read_text(encoding="utf-8"))


# --- Loader happy path ------------------------------------------------------


def test_real_solution_loads() -> None:
    loaded = load_solution(SOLUTION)
    assert loaded.config.solution_id == "it_incident_resolution_copilot"
    assert loaded.config.runtime == "deepagents"
    # Required tools present
    names = [t.name for t in loaded.config.tools]
    for required in [
        "get_ticket",
        "search_sop",
        "search_service_catalog",
        "search_similar_incidents",
        "draft_ticket_update",
        "update_ticket",
        "escalate_ticket",
        "notify_team",
    ]:
        assert required in names


def test_loader_resolves_paths(tmp_path: Path) -> None:
    loaded = load_solution(SOLUTION)
    p = loaded.resolve(loaded.config.prompt.system_prompt_ref)
    assert p.is_file()


# --- Failure modes ----------------------------------------------------------


def test_unknown_risk_level_fails() -> None:
    data = _solution_dict()
    data["tools"][0]["risk"] = "totally_made_up"
    with pytest.raises(Exception):
        SolutionConfig.model_validate(data)


def test_subagent_referencing_unknown_tool_fails() -> None:
    data = _solution_dict()
    data["subagents"][0]["tools"].append("not_a_tool")
    with pytest.raises(Exception):
        SolutionConfig.model_validate(data)


def test_internal_write_tool_requires_approval() -> None:
    with pytest.raises(Exception):
        ToolConfig(
            name="update_ticket",
            adapter="mock_ticketing",
            risk=RiskLevel.INTERNAL_WRITE,
            approval_required=False,
        )


def test_approval_tool_requires_allowed_decisions() -> None:
    with pytest.raises(Exception):
        ToolConfig(
            name="update_ticket",
            adapter="mock_ticketing",
            risk=RiskLevel.INTERNAL_WRITE,
            approval_required=True,
        )


def test_approval_tool_must_allow_approve() -> None:
    with pytest.raises(Exception):
        ToolConfig(
            name="update_ticket",
            adapter="mock_ticketing",
            risk=RiskLevel.INTERNAL_WRITE,
            approval_required=True,
            allowed_decisions=[Decision.REJECT],
        )


def test_read_only_tool_cannot_require_approval() -> None:
    with pytest.raises(Exception):
        ToolConfig(
            name="get_ticket",
            adapter="mock_ticketing",
            risk=RiskLevel.READ_ONLY,
            approval_required=True,
            allowed_decisions=[Decision.APPROVE],
        )


def test_missing_prompt_file_fails(tmp_path: Path) -> None:
    target = tmp_path / "solution.yaml"
    data = _solution_dict()
    data["prompt"]["system_prompt_ref"] = "prompts/does_not_exist.md"
    target.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_solution(target)


def test_missing_knowledge_file_fails(tmp_path: Path) -> None:
    target = tmp_path / "solution.yaml"
    data = _solution_dict()
    data["knowledge"]["sources"].append(
        {"id": "ghost", "type": "mock_rag", "path": "knowledge/missing.md"}
    )
    target.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_solution(target)


def test_missing_dataset_fails(tmp_path: Path) -> None:
    target = tmp_path / "solution.yaml"
    data = _solution_dict()
    data["evaluation"]["dataset"] = "evals/nope.jsonl"
    target.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_solution(target)


def test_duplicate_tool_names_fails() -> None:
    data = _solution_dict()
    data["tools"].append(dict(data["tools"][0]))
    with pytest.raises(Exception):
        SolutionConfig.model_validate(data)


def test_approval_required_risks_set() -> None:
    assert RiskLevel.INTERNAL_WRITE in APPROVAL_REQUIRED_RISKS
    assert RiskLevel.READ_ONLY not in APPROVAL_REQUIRED_RISKS
