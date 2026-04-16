from __future__ import annotations

import textwrap

import pytest

from pyresops.agents import AgentModelConfigLoader


def _write_temp_config(tmp_path, api_key_env: str) -> str:
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(
        textwrap.dedent(
            f"""
            default_profile: test
            models:
              test:
                provider: openai_like
                model_id: fake-model
                base_url: https://example.com/v1
                api_key_env: '{api_key_env}'
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return str(cfg_path)


def test_config_loader_loads_valid_config(tmp_path) -> None:
    cfg_path = _write_temp_config(tmp_path, api_key_env="sk-literal-test-key")
    cfg = AgentModelConfigLoader.load(profile="test", config_path=cfg_path)
    assert cfg["provider"] == "openai_like"
    assert cfg["api_key"] == "sk-literal-test-key"


def test_config_loader_fails_when_profile_missing(tmp_path) -> None:
    cfg_path = _write_temp_config(tmp_path, api_key_env="sk-literal-test-key")
    with pytest.raises(ValueError, match="不存在"):
        AgentModelConfigLoader.load(profile="missing", config_path=cfg_path)


def test_config_loader_fails_when_api_key_missing(tmp_path) -> None:
    cfg_path = _write_temp_config(tmp_path, api_key_env="MISSING_ENV_KEY")
    with pytest.raises(ValueError, match="MISSING_ENV_KEY"):
        AgentModelConfigLoader.load(profile="test", config_path=cfg_path)


def test_config_loader_resolves_default_profile(tmp_path) -> None:
    cfg_path = _write_temp_config(tmp_path, api_key_env="sk-literal-test-key")
    cfg = AgentModelConfigLoader.load(profile=None, config_path=cfg_path)
    assert cfg["model_id"] == "fake-model"
