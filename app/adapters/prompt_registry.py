"""Mock prompt registry.

Loads prompt files from the solution folder. A real Central AI Kitchen
prompt service would resolve a logical prompt id to a version-pinned
template, but for the prototype we just read files from disk.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


class PromptNotFoundError(FileNotFoundError):
    """Raised when a configured prompt file is missing."""


class MockPromptRegistry:
    def __init__(self, solution_dir: Path) -> None:
        self._solution_dir = Path(solution_dir).resolve()

    @property
    def solution_dir(self) -> Path:
        return self._solution_dir

    def load(self, ref: str) -> str:
        """Load a prompt file referenced from ``solution.yaml``.

        ``ref`` is resolved relative to the solution directory.
        """

        path = (self._solution_dir / ref).resolve()
        if not path.is_file():
            raise PromptNotFoundError(f"prompt file missing: {ref} ({path})")
        return _read_text_cached(str(path))


@lru_cache(maxsize=64)
def _read_text_cached(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")
