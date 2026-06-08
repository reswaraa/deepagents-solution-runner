"""Mock LLM gateway.

Resolves a logical model declaration to a concrete LangChain model
instance — or a ``provider:model`` string if no API key is present (so
unit tests can still inspect what would be passed to
``create_deep_agent``).

Supported provider prefixes:

* ``anthropic:<model>``         — needs ``ANTHROPIC_API_KEY``
* ``openai:<model>``            — needs ``OPENAI_API_KEY``
* ``google_genai:<model>``      — needs ``GOOGLE_API_KEY``
* ``bedrock_converse:<modelId>``— needs AWS credentials + ``AWS_REGION``
  (uses the Bedrock Converse API; recommended for Bedrock + tool-calling)
* ``bedrock:<modelId>``         — needs AWS credentials + ``AWS_REGION``
* ``openai_compatible:<model>`` — needs ``base_url`` + ``api_key_env`` in the
  YAML. Use this for Azure AI Foundry serverless deployments, vLLM, LM
  Studio, internal model gateways, or any other endpoint that speaks the
  OpenAI Chat Completions wire protocol.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
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
        "bedrock_default_reasoning_model": (
            "bedrock_converse:anthropic.claude-sonnet-4-5-20250929-v1:0"
        ),
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

        has_credentials = self._has_credentials_for(provider_model, cfg)

        # If credentials look present, try to materialise the model so
        # callers can pass either a string OR a configured instance.
        # For ``openai_compatible:`` we always materialise (even without a
        # key) because ``init_chat_model`` does not know our pseudo-prefix —
        # the runner's no-credentials short-circuit fires before any actual
        # network call.
        materialised: Any = provider_model
        try:
            if _is_openai_compatible(provider_model):
                materialised = self._build_openai_compatible(
                    cfg, allow_missing_key=not has_credentials
                )
            elif has_credentials:
                from langchain.chat_models import (  # type: ignore
                    init_chat_model,
                )

                kwargs: dict[str, Any] = {"temperature": cfg.temperature}
                if _is_bedrock(provider_model):
                    region = self._env.get("AWS_REGION") or self._env.get(
                        "AWS_DEFAULT_REGION"
                    )
                    if region:
                        kwargs["region_name"] = region
                    profile = self._env.get("AWS_PROFILE")
                    if profile:
                        kwargs["credentials_profile_name"] = profile
                materialised = init_chat_model(provider_model, **kwargs)
        except Exception:  # pragma: no cover - best effort
            materialised = provider_model

        return ResolvedModel(
            logical_name=cfg.logical_name,
            provider_model=provider_model,
            model=materialised,
            has_credentials=has_credentials,
        )

    # ------------------------------------------------------------------
    # OpenAI-compatible (Azure AI Foundry, vLLM, etc.)
    # ------------------------------------------------------------------

    _PLACEHOLDER_API_KEY = "stub-no-credentials"

    def _build_openai_compatible(
        self, cfg: ModelConfig, *, allow_missing_key: bool = False
    ) -> Any:
        """Build a ``ChatOpenAI`` pointed at the configured custom endpoint.

        If ``allow_missing_key`` is True (used when the runner has already
        decided to short-circuit to the no-credentials stub), a placeholder
        key is used so the model instance constructs cleanly. No real
        network call ever uses it.
        """

        from langchain_openai import ChatOpenAI

        if not cfg.api_key_env:
            raise ValueError("api_key_env is required for openai_compatible models")
        api_key = self._env.get(cfg.api_key_env)
        if not api_key:
            if not allow_missing_key:
                raise ValueError(
                    f"openai_compatible api key env var '{cfg.api_key_env}' is not set"
                )
            api_key = self._PLACEHOLDER_API_KEY
        model_name = cfg.provider_model.split(":", 1)[1]
        kwargs: dict[str, Any] = {
            "model": model_name,
            "base_url": cfg.base_url,
            "api_key": api_key,
            "temperature": cfg.temperature,
        }
        if cfg.extra_headers:
            kwargs["default_headers"] = dict(cfg.extra_headers)
        return ChatOpenAI(**kwargs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _has_credentials_for(
        self, provider_model: str, cfg: ModelConfig | None = None
    ) -> bool:
        provider = (
            provider_model.split(":", 1)[0].lower() if ":" in provider_model else ""
        )
        match provider:
            case "anthropic":
                return bool(self._env.get("ANTHROPIC_API_KEY"))
            case "openai":
                return bool(self._env.get("OPENAI_API_KEY"))
            case "google" | "google_genai":
                return bool(self._env.get("GOOGLE_API_KEY"))
            case "bedrock" | "bedrock_converse":
                return self._has_aws_credentials()
            case "openai_compatible":
                if cfg is None or not cfg.api_key_env:
                    return False
                return bool(self._env.get(cfg.api_key_env))
            case _:
                return False

    def _has_aws_credentials(self) -> bool:
        """Detect AWS credentials for Bedrock.

        Accept any of the standard AWS auth sources:
        * ``AWS_ACCESS_KEY_ID`` + ``AWS_SECRET_ACCESS_KEY`` env vars
        * ``AWS_PROFILE`` env var
        * a ``~/.aws/credentials`` or ``~/.aws/config`` file on disk
        * a container/EC2 metadata endpoint via
          ``AWS_CONTAINER_CREDENTIALS_RELATIVE_URI`` /
          ``AWS_WEB_IDENTITY_TOKEN_FILE``
        We also require a region (``AWS_REGION`` or ``AWS_DEFAULT_REGION``)
        because Bedrock is regional and missing it will fail at first call.
        """

        has_region = bool(
            self._env.get("AWS_REGION") or self._env.get("AWS_DEFAULT_REGION")
        )
        if not has_region:
            return False
        if self._env.get("AWS_ACCESS_KEY_ID") and self._env.get(
            "AWS_SECRET_ACCESS_KEY"
        ):
            return True
        if self._env.get("AWS_PROFILE"):
            return True
        if self._env.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
            return True
        if self._env.get("AWS_WEB_IDENTITY_TOKEN_FILE"):
            return True
        home = Path(self._env.get("HOME", "")).expanduser() if self._env.get(
            "HOME"
        ) else Path.home()
        if (home / ".aws" / "credentials").is_file():
            return True
        if (home / ".aws" / "config").is_file():
            return True
        return False


def _is_bedrock(provider_model: str) -> bool:
    head = provider_model.split(":", 1)[0].lower()
    return head in {"bedrock", "bedrock_converse"}


def _is_openai_compatible(provider_model: str) -> bool:
    head = provider_model.split(":", 1)[0].lower()
    return head == "openai_compatible"
