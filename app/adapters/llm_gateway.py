"""Mock LLM gateway.

Resolves a logical model declaration to a concrete LangChain model
instance — or a ``provider:model`` string if no API key is present (so
unit tests can still inspect what would be passed to
``create_deep_agent``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.schemas import ModelConfig


@dataclass
class ResolvedModel:
    """The result of resolving a logical model config.

    ``model`` is what we hand to ``create_deep_agent``. It is either a
    string ("provider:model") that DeepAgents will init itself, or a
    pre-initialised ``BaseChatModel`` instance.
    """

    logical_name: str
    provider_model: str
    model: Any  # str | BaseChatModel
    has_credentials: bool


class MockLLMGateway:
    """Mock of the Central AI Kitchen LLM gateway."""

    # Logical name -> provider:model fallback. Real gateway would look
    # this up in the Model Garden; we hard-code a few aliases for the
    # prototype.
    _LOGICAL_ALIASES: dict[str, str] = {
        "default_reasoning_model": "anthropic:claude-sonnet-4-6",
        "fast_model": "anthropic:claude-haiku-4-5",
    }

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = env if env is not None else os.environ

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_model(self, cfg: ModelConfig | dict[str, Any]) -> ResolvedModel:
        """Resolve a model config into something ``create_deep_agent`` accepts."""

        if isinstance(cfg, dict):
            cfg = ModelConfig.model_validate(cfg)

        provider_model = cfg.provider_model or self._LOGICAL_ALIASES.get(
            cfg.logical_name, ""
        )
        if not provider_model:
            raise ValueError(
                f"Cannot resolve logical model '{cfg.logical_name}': "
                "no provider_model declared and no alias known."
            )

        has_credentials = self._has_credentials_for(provider_model)

        # If credentials look present, try to materialise the model so
        # callers can pass either a string OR a configured instance.
        materialised: Any = provider_model
        if has_credentials:
            try:
                from langchain.chat_models import init_chat_model  # type: ignore

                materialised = init_chat_model(
                    provider_model, temperature=cfg.temperature
                )
            except Exception:  # pragma: no cover - best effort
                materialised = provider_model

        return ResolvedModel(
            logical_name=cfg.logical_name,
            provider_model=provider_model,
            model=materialised,
            has_credentials=has_credentials,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _has_credentials_for(self, provider_model: str) -> bool:
        provider = provider_model.split(":", 1)[0].lower() if ":" in provider_model else ""
        match provider:
            case "anthropic":
                return bool(self._env.get("ANTHROPIC_API_KEY"))
            case "openai":
                return bool(self._env.get("OPENAI_API_KEY"))
            case "google" | "google_genai":
                return bool(self._env.get("GOOGLE_API_KEY"))
            case _:
                return False
