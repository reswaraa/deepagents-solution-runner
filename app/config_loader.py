"""Load and validate ``solution.yaml``.

The loader is intentionally strict:

* unknown fields surface as schema errors
* prompt / knowledge / dataset paths are resolved relative to the solution
  folder and verified on disk
* approval-required tools must include allowed decisions
* subagents must only reference declared tools
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .schemas import SolutionConfig, SubagentConfig


class ConfigError(Exception):
    """Raised when ``solution.yaml`` cannot be loaded or validated."""


@dataclass
class LoadedSolution:
    """A validated solution config and the folder it was loaded from."""

    config: SolutionConfig
    solution_dir: Path
    config_path: Path

    def resolve(self, rel: str) -> Path:
        """Resolve a path relative to the solution directory."""

        candidate = (self.solution_dir / rel).resolve()
        return candidate


def load_solution(config_path: str | Path) -> LoadedSolution:
    """Load and validate a ``solution.yaml`` file.

    Args:
        config_path: Path to the solution YAML.

    Returns:
        ``LoadedSolution`` carrying the parsed config plus the solution dir.

    Raises:
        ConfigError: If the file is missing, malformed, or references
            files that do not exist on disk.
    """

    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise ConfigError(f"solution.yaml not found: {path}")

    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Top-level YAML must be a mapping in {path}")

    try:
        config = SolutionConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Config validation failed for {path}:\n{exc}") from exc

    loaded = LoadedSolution(
        config=config, solution_dir=path.parent, config_path=path
    )
    _validate_paths_exist(loaded)
    return loaded


def _validate_paths_exist(loaded: LoadedSolution) -> None:
    cfg = loaded.config
    errors: list[str] = []

    system_prompt = loaded.resolve(cfg.prompt.system_prompt_ref)
    if not system_prompt.is_file():
        errors.append(
            f"prompt.system_prompt_ref missing: {cfg.prompt.system_prompt_ref}"
        )

    for sub in cfg.subagents:
        sub_prompt = loaded.resolve(sub.system_prompt_ref)
        if not sub_prompt.is_file():
            errors.append(
                f"subagent '{sub.name}' prompt missing: {sub.system_prompt_ref}"
            )

    for ks in cfg.knowledge.sources:
        ks_path = loaded.resolve(ks.path)
        if not ks_path.is_file():
            errors.append(f"knowledge source '{ks.id}' missing: {ks.path}")

    for skill_path in cfg.skills:
        sp = loaded.resolve(skill_path)
        if not sp.is_dir():
            errors.append(f"skill folder missing: {skill_path}")
        else:
            if not (sp / "SKILL.md").is_file():
                errors.append(f"skill folder missing SKILL.md: {skill_path}")

    if cfg.evaluation is not None:
        ds = loaded.resolve(cfg.evaluation.dataset)
        if not ds.is_file():
            errors.append(f"evaluation dataset missing: {cfg.evaluation.dataset}")

    if errors:
        joined = "\n  - ".join(errors)
        raise ConfigError(f"Config references missing files:\n  - {joined}")


def find_subagent(cfg: SolutionConfig, name: str) -> SubagentConfig | None:
    for sub in cfg.subagents:
        if sub.name == name:
            return sub
    return None
