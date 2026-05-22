"""Fail-first model configuration loading for Agno agent runs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class AgentModelConfigLoader:
    """Load a real model profile and fail if required credentials are missing."""

    REAL_PROVIDER_KEYED = {
        "anthropic",
        "deepseek",
        "dashscope",
        "gemini_native",
        "openai_like",
        "opencode",
    }

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _load_env_file(cls) -> None:
        env_path = cls._project_root() / ".env"
        if not env_path.exists():
            return
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    @classmethod
    def load(cls, profile: str | None = None, config_path: str | None = None) -> dict[str, Any]:
        cls._load_env_file()
        resolved_config_path = (
            Path(config_path)
            if config_path is not None
            else cls._project_root() / "experiments" / "config" / "llm_config.yml"
        )
        if not resolved_config_path.exists():
            raise FileNotFoundError(f"Missing model config: {resolved_config_path}")

        with resolved_config_path.open("r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        if not isinstance(cfg, dict):
            raise ValueError(f"Model config must be a mapping: {resolved_config_path}")

        selected_profile = profile or cfg.get("default_profile")
        if not selected_profile:
            raise ValueError("Model config must define default_profile or receive profile explicitly")

        models_cfg = cfg.get("models")
        if not isinstance(models_cfg, dict) or selected_profile not in models_cfg:
            available = sorted(models_cfg) if isinstance(models_cfg, dict) else []
            raise ValueError(f"Unknown model profile {selected_profile!r}; available={available}")

        model_cfg = dict(models_cfg[selected_profile] or {})
        if model_cfg.get("disabled"):
            raise ValueError(f"Model profile {selected_profile!r} is disabled and cannot be executed")
        provider = str(model_cfg.get("provider", "")).strip()
        if not provider:
            raise ValueError(f"Model profile {selected_profile!r} is missing provider")
        if not model_cfg.get("model_id"):
            raise ValueError(f"Model profile {selected_profile!r} is missing model_id")

        api_key_env = model_cfg.pop("api_key_env", None)
        if api_key_env and not model_cfg.get("api_key"):
            env_value = os.getenv(str(api_key_env))
            if env_value:
                model_cfg["api_key"] = env_value

        base_url_env = model_cfg.pop("base_url_env", None)
        if base_url_env:
            env_value = os.getenv(str(base_url_env))
            if env_value:
                model_cfg["base_url"] = env_value
        if not model_cfg.get("base_url") and model_cfg.get("default_base_url"):
            model_cfg["base_url"] = model_cfg.get("default_base_url")

        if provider in cls.REAL_PROVIDER_KEYED and not model_cfg.get("api_key"):
            hint = api_key_env or "api_key"
            raise ValueError(
                f"Model profile {selected_profile!r} did not resolve a real API key. "
                f"Set {hint} or provide api_key in {resolved_config_path}."
            )

        model_cfg["provider"] = provider
        model_cfg["profile"] = selected_profile
        return model_cfg
