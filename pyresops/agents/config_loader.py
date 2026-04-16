from __future__ import annotations

import os
import pathlib

import yaml
from dotenv import load_dotenv


class AgentModelConfigLoader:
    """Load and validate model config for reservoir agent runtime only."""

    @staticmethod
    def _load_env_file() -> None:
        project_root = pathlib.Path(__file__).resolve().parents[2]
        load_dotenv(project_root / ".env", override=False)

    @staticmethod
    def load(profile: str | None = None, config_path: str | None = None) -> dict:
        AgentModelConfigLoader._load_env_file()

        if config_path is None:
            config_path = (
                pathlib.Path(__file__).resolve().parents[2]
                / "experiments"
                / "config"
                / "llm_config.yml"
            )

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        if profile is None:
            profile = cfg.get("default_profile", "claude")

        models_cfg = cfg.get("models", {})
        if profile not in models_cfg:
            available = list(models_cfg.keys())
            raise ValueError(f"模型配置 '{profile}' 不存在，可用配置：{available}")

        model_cfg = models_cfg[profile].copy()
        api_key_env = model_cfg.pop("api_key_env", None)
        if "api_key" not in model_cfg and api_key_env:
            api_key = os.getenv(api_key_env)
            if api_key:
                model_cfg["api_key"] = api_key
            elif str(api_key_env).startswith("sk-"):
                model_cfg["api_key"] = str(api_key_env)

        provider = model_cfg.get("provider", "")
        needs_api_key = provider in {
            "anthropic",
            "deepseek",
            "dashscope",
            "openai_like",
            "opencode",
        }
        if needs_api_key and not model_cfg.get("api_key"):
            missing_hint = api_key_env or "<api_key>"
            raise ValueError(
                f"模型配置 '{profile}' 未解析到 API Key。请设置环境变量 {missing_hint}，"
                "或在 experiments/config/llm_config.yml 中为该 profile 提供 api_key。"
            )

        return model_cfg
