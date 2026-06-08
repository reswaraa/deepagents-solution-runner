"""Tests for the MockLLMGateway, including AWS Bedrock resolution."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.llm_gateway import MockLLMGateway
from app.schemas import ModelConfig


def _cfg(provider_model: str) -> ModelConfig:
    return ModelConfig(
        logical_name="x",
        temperature=0.1,
        provider_model=provider_model,
    )


# --- Anthropic --------------------------------------------------------------


def test_anthropic_no_credentials() -> None:
    gw = MockLLMGateway(env={})
    res = gw.resolve_model(_cfg("anthropic:claude-sonnet-4-6"))
    assert res.has_credentials is False
    assert res.model == "anthropic:claude-sonnet-4-6"


def test_anthropic_with_credentials() -> None:
    gw = MockLLMGateway(env={"ANTHROPIC_API_KEY": "fake"})
    res = gw.resolve_model(_cfg("anthropic:claude-sonnet-4-6"))
    assert res.has_credentials is True


# --- Bedrock ----------------------------------------------------------------


def test_bedrock_requires_region() -> None:
    gw = MockLLMGateway(
        env={
            "AWS_ACCESS_KEY_ID": "AKIA...",
            "AWS_SECRET_ACCESS_KEY": "secret",
            # no region
        }
    )
    res = gw.resolve_model(
        _cfg("bedrock_converse:anthropic.claude-sonnet-4-5-20250929-v1:0")
    )
    assert res.has_credentials is False


def test_bedrock_with_static_keys_and_region() -> None:
    gw = MockLLMGateway(
        env={
            "AWS_ACCESS_KEY_ID": "AKIA...",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "AWS_REGION": "ap-southeast-1",
        }
    )
    res = gw.resolve_model(
        _cfg("bedrock_converse:anthropic.claude-sonnet-4-5-20250929-v1:0")
    )
    assert res.has_credentials is True
    # If langchain-aws is installed the model will be materialised.
    assert res.model is not None


def test_bedrock_with_profile_and_region() -> None:
    gw = MockLLMGateway(
        env={
            "AWS_PROFILE": "prototype",
            "AWS_REGION": "us-east-1",
        }
    )
    res = gw.resolve_model(
        _cfg("bedrock_converse:us.anthropic.claude-3-5-sonnet-20241022-v2:0")
    )
    assert res.has_credentials is True


def test_bedrock_picks_up_credentials_file(tmp_path: Path) -> None:
    aws_dir = tmp_path / ".aws"
    aws_dir.mkdir()
    (aws_dir / "credentials").write_text(
        "[default]\naws_access_key_id=AKIA\naws_secret_access_key=...\n",
        encoding="utf-8",
    )
    gw = MockLLMGateway(
        env={
            "HOME": str(tmp_path),
            "AWS_DEFAULT_REGION": "ap-southeast-1",
        }
    )
    res = gw.resolve_model(
        _cfg("bedrock_converse:anthropic.claude-sonnet-4-5-20250929-v1:0")
    )
    assert res.has_credentials is True


def test_bedrock_no_credentials_at_all(tmp_path: Path) -> None:
    gw = MockLLMGateway(
        env={
            # HOME points at an empty dir → no ~/.aws files
            "HOME": str(tmp_path),
        }
    )
    res = gw.resolve_model(
        _cfg("bedrock_converse:anthropic.claude-sonnet-4-5-20250929-v1:0")
    )
    assert res.has_credentials is False


# --- OpenAI-compatible (Azure AI Foundry, vLLM, …) --------------------------


def test_openai_compatible_requires_base_url() -> None:
    with pytest.raises(Exception):
        ModelConfig(
            logical_name="kimi",
            temperature=0.1,
            provider_model="openai_compatible:kimi-k2.6",
            api_key_env="AZURE_KIMI_KEY",
            # missing base_url
        )


def test_openai_compatible_requires_api_key_env() -> None:
    with pytest.raises(Exception):
        ModelConfig(
            logical_name="kimi",
            temperature=0.1,
            provider_model="openai_compatible:kimi-k2.6",
            base_url="https://kimi.swedencentral.models.ai.azure.com/v1",
            # missing api_key_env
        )


def test_openai_compatible_requires_model_name() -> None:
    with pytest.raises(Exception):
        ModelConfig(
            logical_name="kimi",
            temperature=0.1,
            provider_model="openai_compatible:",  # bare prefix
            base_url="https://kimi.swedencentral.models.ai.azure.com/v1",
            api_key_env="AZURE_KIMI_KEY",
        )


def test_openai_compatible_no_key_in_env() -> None:
    """Without the API key env var the gateway still materialises a
    placeholder ``ChatOpenAI`` so ``create_deep_agent`` builds cleanly.
    The runner's no-credentials short-circuit prevents any real call."""

    cfg = ModelConfig(
        logical_name="kimi",
        temperature=0.1,
        provider_model="openai_compatible:kimi-k2.6",
        base_url="https://kimi.swedencentral.models.ai.azure.com/v1",
        api_key_env="AZURE_KIMI_KEY",
    )
    gw = MockLLMGateway(env={})
    res = gw.resolve_model(cfg)
    assert res.has_credentials is False
    assert type(res.model).__name__ == "ChatOpenAI"
    assert res.model.model_name == "kimi-k2.6"


def test_openai_compatible_materialises_chat_openai() -> None:
    cfg = ModelConfig(
        logical_name="kimi",
        temperature=0.1,
        provider_model="openai_compatible:kimi-k2.6",
        base_url="https://kimi.swedencentral.models.ai.azure.com/v1",
        api_key_env="AZURE_KIMI_KEY",
        extra_headers={"x-deployment-id": "kimi-prod"},
    )
    gw = MockLLMGateway(env={"AZURE_KIMI_KEY": "fake-key"})
    res = gw.resolve_model(cfg)
    assert res.has_credentials is True
    # Materialised model should be a ChatOpenAI pointed at the custom URL.
    assert type(res.model).__name__ == "ChatOpenAI"
    assert res.model.openai_api_base == (
        "https://kimi.swedencentral.models.ai.azure.com/v1"
    )
    # Model name strips the openai_compatible: prefix
    assert res.model.model_name == "kimi-k2.6"


def test_openai_compatible_azure_foundry_url_pattern() -> None:
    """Regression test for the exact Azure AI Foundry URL the supervisor uses."""

    cfg = ModelConfig(
        logical_name="kimi_main",
        temperature=0.1,
        provider_model="openai_compatible:Kimi-K2.6",
        base_url="https://singtelclaw-poc.services.ai.azure.com/openai/v1/",
        api_key_env="AZURE_AI_FOUNDRY_KEY",
    )
    gw = MockLLMGateway(env={"AZURE_AI_FOUNDRY_KEY": "fake"})
    res = gw.resolve_model(cfg)
    # Case-sensitive model name (it's a Foundry deployment name).
    assert res.model.model_name == "Kimi-K2.6"
    # URL passed through verbatim — trailing slash is fine; the OpenAI
    # client composes `/chat/completions` after it.
    assert (
        str(res.model.root_client.base_url)
        == "https://singtelclaw-poc.services.ai.azure.com/openai/v1/"
    )


def test_openai_compatible_same_resource_two_deployments() -> None:
    """Multiple Foundry deployments on the same resource share base_url + key."""

    env = {"AZURE_AI_FOUNDRY_KEY": "fake"}
    base = "https://singtelclaw-poc.services.ai.azure.com/openai/v1/"
    main = ModelConfig(
        logical_name="kimi_main",
        temperature=0.1,
        provider_model="openai_compatible:Kimi-K2.6",
        base_url=base,
        api_key_env="AZURE_AI_FOUNDRY_KEY",
    )
    sub = ModelConfig(
        logical_name="deepseek_flash",
        temperature=0.2,
        provider_model="openai_compatible:DeepSeek-V4-Flash",
        base_url=base,
        api_key_env="AZURE_AI_FOUNDRY_KEY",
    )
    gw = MockLLMGateway(env=env)
    main_res = gw.resolve_model(main)
    sub_res = gw.resolve_model(sub)
    assert main_res.model.model_name == "Kimi-K2.6"
    assert sub_res.model.model_name == "DeepSeek-V4-Flash"


def test_base_url_rejected_for_non_compatible_provider() -> None:
    with pytest.raises(Exception):
        ModelConfig(
            logical_name="x",
            temperature=0.1,
            provider_model="anthropic:claude-sonnet-4-6",
            base_url="https://nope/v1",
            api_key_env="WHATEVER",
        )


# --- Logical alias ----------------------------------------------------------


def test_logical_alias_bedrock_default() -> None:
    gw = MockLLMGateway(env={})
    cfg = ModelConfig(
        logical_name="bedrock_default_reasoning_model",
        temperature=0.1,
        # Override the default by reusing the alias's resolved provider_model.
        provider_model="bedrock_converse:anthropic.claude-sonnet-4-5-20250929-v1:0",
    )
    res = gw.resolve_model(cfg)
    assert "bedrock_converse" in res.provider_model
