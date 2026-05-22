"""Agno model construction helpers."""

from __future__ import annotations

from typing import Any


def _missing_agno_error() -> RuntimeError:
    return RuntimeError(
        "Agno is required for real agent execution but is not installed. "
        "Install the project experiment dependencies, then rerun the workflow."
    )


def build_agno_model(
    model_cfg: dict[str, Any],
    temperature: float | None = None,
    seed: int | None = None,
):
    """Build a real Agno model from a validated model config."""
    provider = model_cfg.get("provider", "anthropic")
    model_id = model_cfg.get("model_id", "")
    api_key = model_cfg.get("api_key")
    base_url = model_cfg.get("base_url")
    max_tokens = model_cfg.get("max_tokens")
    extra_body = model_cfg.get("extra_body")

    def with_common(kwargs: dict[str, Any]) -> dict[str, Any]:
        if temperature is not None:
            kwargs["temperature"] = temperature
        if seed is not None and provider in {"deepseek", "gemini_native", "openai_like", "opencode"}:
            kwargs["seed"] = seed
        if max_tokens is not None:
            kwargs["max_tokens"] = int(max_tokens)
        if extra_body is not None:
            kwargs["extra_body"] = extra_body
        return kwargs

    try:
        if provider == "anthropic":
            from agno.models.anthropic import Claude

            kwargs = with_common({"id": model_id})
            if api_key:
                kwargs["api_key"] = api_key
            return Claude(**kwargs)

        if provider == "deepseek":
            from agno.models.deepseek import DeepSeek

            kwargs = with_common({"id": model_id})
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            return DeepSeek(**kwargs)

        if provider == "dashscope":
            from agno.models.dashscope import DashScope

            kwargs = with_common({"id": model_id})
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            return DashScope(**kwargs)

        if provider == "gemini_native":
            from agno.models.google import Gemini

            kwargs: dict[str, Any] = {"id": model_id}
            if temperature is not None:
                kwargs["temperature"] = temperature
            if seed is not None:
                kwargs["seed"] = seed
            if max_tokens is not None:
                kwargs["max_output_tokens"] = int(max_tokens)
            if api_key:
                kwargs["api_key"] = api_key
            return Gemini(**kwargs)

        if provider in {"openai_like", "opencode"}:
            from agno.models.openai.like import OpenAILike

            kwargs = with_common({"id": model_id})
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            return OpenAILike(**kwargs)
    except ImportError as exc:
        raise _missing_agno_error() from exc

    raise ValueError(
        f"Unsupported provider {provider!r}; expected anthropic, deepseek, "
        "dashscope, gemini_native, openai_like, or opencode"
    )
