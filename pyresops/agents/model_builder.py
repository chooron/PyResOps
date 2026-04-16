from __future__ import annotations


def build_agno_model(
    model_cfg: dict,
    temperature: float | None = None,
    seed: int | None = None,
):
    """Build agno model from normalized config only."""
    provider = model_cfg.get("provider", "anthropic")
    model_id = model_cfg.get("model_id", "")
    api_key = model_cfg.get("api_key")
    base_url = model_cfg.get("base_url")

    def _inject_common_runtime_kwargs(kwargs: dict) -> dict:
        if temperature is not None:
            kwargs["temperature"] = temperature
        if seed is not None and provider in {"deepseek", "openai_like", "opencode"}:
            kwargs["seed"] = seed
        return kwargs

    if provider == "anthropic":
        from agno.models.anthropic import Claude

        kwargs = _inject_common_runtime_kwargs({"id": model_id})
        if api_key:
            kwargs["api_key"] = api_key
        return Claude(**kwargs)

    if provider == "deepseek":
        from agno.models.deepseek import DeepSeek

        kwargs = _inject_common_runtime_kwargs({"id": model_id})
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return DeepSeek(**kwargs)

    if provider == "dashscope":
        from agno.models.dashscope import DashScope

        kwargs = _inject_common_runtime_kwargs({"id": model_id})
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return DashScope(**kwargs)

    if provider in ("openai_like", "opencode"):
        from agno.models.openai.like import OpenAILike

        kwargs = _inject_common_runtime_kwargs({"id": model_id})
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAILike(**kwargs)

    raise ValueError(
        f"不支持的 provider: '{provider}'，可选：anthropic, deepseek, dashscope, openai_like, opencode"
    )
