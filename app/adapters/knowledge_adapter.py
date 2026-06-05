"""Mock knowledge/RAG adapter.

Loads Markdown or JSON sources declared in ``solution.yaml`` and offers
a tiny keyword-scoring search. The shape is small on purpose: real
Central AI Kitchen RAG would be a network call returning ranked
passages with citations — we just match the interface.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config_loader import LoadedSolution
from app.schemas import KnowledgeSourceConfig


@dataclass
class _LoadedSource:
    id: str
    path: Path
    chunks: list[dict[str, Any]]


class MockKnowledgeAdapter:
    """Search local Markdown/JSON knowledge files by id."""

    def __init__(self, sources: dict[str, _LoadedSource]) -> None:
        self._sources = sources

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, loaded: LoadedSolution) -> "MockKnowledgeAdapter":
        sources: dict[str, _LoadedSource] = {}
        for src in loaded.config.knowledge.sources:
            path = loaded.resolve(src.path)
            sources[src.id] = _LoadedSource(
                id=src.id,
                path=path,
                chunks=_load_chunks(src, path),
            )
        return cls(sources)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def source_ids(self) -> list[str]:
        return list(self._sources.keys())

    def search(self, source_id: str, query: str, limit: int = 3) -> list[dict[str, Any]]:
        src = self._sources.get(source_id)
        if src is None:
            return []
        tokens = _tokenise(query)
        if not tokens:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in src.chunks:
            score = _score(chunk["_search_text"], tokens)
            if score > 0:
                hit = {k: v for k, v in chunk.items() if not k.startswith("_")}
                hit["score"] = round(score, 4)
                scored.append((score, hit))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in scored[:limit]]


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


_SECTION_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _load_chunks(src: KnowledgeSourceConfig, path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        chunks: list[dict[str, Any]] = []
        if isinstance(data, list):
            for item in data:
                chunks.append(
                    {
                        "source": src.id,
                        "title": item.get("id") or item.get("title") or "",
                        "snippet": json.dumps(item, ensure_ascii=False),
                        "data": item,
                        "_search_text": _flatten_for_search(item),
                    }
                )
        elif isinstance(data, dict):
            chunks.append(
                {
                    "source": src.id,
                    "title": str(data.get("id", path.stem)),
                    "snippet": json.dumps(data, ensure_ascii=False),
                    "data": data,
                    "_search_text": _flatten_for_search(data),
                }
            )
        return chunks

    # Markdown: split by H1/H2/H3 headings.
    text = path.read_text(encoding="utf-8")
    matches = list(_SECTION_RE.finditer(text))
    chunks = []
    if not matches:
        chunks.append(
            {
                "source": src.id,
                "title": path.stem,
                "snippet": text.strip(),
                "_search_text": text.lower(),
            }
        )
        return chunks
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        title = m.group(2).strip()
        chunks.append(
            {
                "source": src.id,
                "title": title,
                "snippet": section_text,
                "_search_text": section_text.lower(),
            }
        )
    return chunks


def _flatten_for_search(obj: Any) -> str:
    parts: list[str] = []

    def _walk(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                parts.append(str(k))
                _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)
        elif o is not None:
            parts.append(str(o))

    _walk(obj)
    return " ".join(parts).lower()


_WORD_RE = re.compile(r"[a-zA-Z0-9\-]+")


def _tokenise(query: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(query) if len(t) > 1]


def _score(text: str, tokens: list[str]) -> float:
    total = 0.0
    for tok in tokens:
        total += text.count(tok)
    return total
