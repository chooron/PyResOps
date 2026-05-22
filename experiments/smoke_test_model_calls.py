"""Smoke-test simple chat calls for candidate Phase G models.

This script intentionally sends a tiny prompt and reports only connectivity,
response text, and token usage. It does not run PyResOps workflows.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI


@dataclass(frozen=True)
class ModelProbe:
    name: str
    model_id: str
    api_key_env: str
    base_url_env: str
    default_base_url: str
    provider: str = "openai_like"
    extra_body: dict[str, Any] | None = None
    fallback_base_urls: tuple[str, ...] = ()


@dataclass
class ProbeResult:
    name: str
    model_id: str
    base_url: str
    api_key_env: str
    status: str
    latency_seconds: float | None = None
    response_text: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    error_type: str | None = None
    error_message: str | None = None


PROBES: dict[str, ModelProbe] = {
    "deepseek_v4_flash": ModelProbe(
        name="deepseek_v4_flash",
        model_id="deepseek-v4-flash",
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_BASE_URL",
        default_base_url="https://api.deepseek.com",
        extra_body={"thinking": {"type": "disabled"}},
    ),
    "gemini_3_1_flash_lite": ModelProbe(
        name="gemini_3_1_flash_lite",
        model_id="gemini-3.1-flash-lite",
        api_key_env="GEMINI_API_KEY",
        base_url_env="GEMINI_BASE_URL",
        default_base_url="native_google_genai",
        provider="gemini_native",
    ),
    "minimax_m2_5_free": ModelProbe(
        name="minimax_m2_5_free",
        model_id="MiniMax-M2.5",
        api_key_env="MINMAX_API_KEY",
        base_url_env="MINMAX_BASE_URL",
        default_base_url="https://api.penguinsaichat.dpdns.org/v1",
    ),
    "qwen3_6_flash": ModelProbe(
        name="qwen3_6_flash",
        model_id="qwen3.6-flash",
        api_key_env="DASHSCOPE_API_KEY",
        base_url_env="DASHSCOPE_BASE_URL",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        extra_body={"enable_thinking": False},
    ),
}


def _load_dotenv() -> None:
    env_path = Path(".env")
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


def _usage_value(usage: Any, key: str) -> int | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        value = usage.get(key)
    else:
        value = getattr(usage, key, None)
    return int(value) if isinstance(value, int) else None


def probe_model(probe: ModelProbe, timeout: float, max_tokens: int) -> ProbeResult:
    api_key = os.getenv(probe.api_key_env)
    base_url = os.getenv(probe.base_url_env) or probe.default_base_url
    result = ProbeResult(
        name=probe.name,
        model_id=probe.model_id,
        base_url=base_url,
        api_key_env=probe.api_key_env,
        status="pending",
    )
    if not api_key:
        result.status = "missing_api_key"
        result.error_message = f"Set {probe.api_key_env} to test {probe.name}."
        return result

    if probe.provider == "gemini_native":
        return _probe_gemini_native(probe, api_key=api_key, timeout=timeout, max_tokens=max_tokens)

    for index, candidate_base_url in enumerate((base_url, *probe.fallback_base_urls)):
        result = _probe_openai_like(
            probe,
            api_key=api_key,
            base_url=candidate_base_url,
            timeout=timeout,
            max_tokens=max_tokens,
        )
        if result.status == "ok":
            return result
        if index == 0 and _should_try_fallback(result):
            continue
        return result
    return result


def _probe_openai_like(
    probe: ModelProbe,
    *,
    api_key: str,
    base_url: str,
    timeout: float,
    max_tokens: int,
) -> ProbeResult:
    result = ProbeResult(
        name=probe.name,
        model_id=probe.model_id,
        base_url=base_url,
        api_key_env=probe.api_key_env,
        status="pending",
    )
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=probe.model_id,
            messages=[
                {
                    "role": "system",
                    "content": "Return only compact JSON.",
                },
                {
                    "role": "user",
                    "content": (
                        'Reply exactly as JSON: {"status":"ok","model":"'
                        + probe.name
                        + '"}'
                    ),
                },
            ],
            temperature=0,
            max_tokens=max_tokens,
            extra_body=probe.extra_body,
        )
        result.latency_seconds = round(time.perf_counter() - start, 3)
        if isinstance(response, str):
            result.response_text = response.strip()[:500]
            result.status = "nonstandard_text_response" if result.response_text else "empty_response"
            return result
        if isinstance(response, dict):
            choices = response.get("choices") or []
            message = (choices[0].get("message") or {}).get("content") if choices else ""
            usage = response.get("usage")
        else:
            choices = getattr(response, "choices", []) or []
            message = choices[0].message.content if choices else ""
            usage = getattr(response, "usage", None)
        result.response_text = (message or "").strip()[:500]
        result.prompt_tokens = _usage_value(usage, "prompt_tokens")
        result.completion_tokens = _usage_value(usage, "completion_tokens")
        result.total_tokens = _usage_value(usage, "total_tokens")
        result.status = "ok" if result.response_text else "empty_response"
    except Exception as exc:  # noqa: BLE001 - smoke script should capture provider-specific failures.
        result.latency_seconds = round(time.perf_counter() - start, 3)
        result.status = "error"
        result.error_type = type(exc).__name__
        result.error_message = str(exc)[:1000]
    return result


def _probe_gemini_native(
    probe: ModelProbe,
    *,
    api_key: str,
    timeout: float,
    max_tokens: int,
) -> ProbeResult:
    result = ProbeResult(
        name=probe.name,
        model_id=probe.model_id,
        base_url="native_google_genai",
        api_key_env=probe.api_key_env,
        status="pending",
    )
    start = time.perf_counter()
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=probe.model_id,
            contents=(
                'Return only compact JSON. Reply exactly as JSON: {"status":"ok","model":"'
                + probe.name
                + '"}'
            ),
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=int(timeout * 1000)),
            ),
        )
        result.latency_seconds = round(time.perf_counter() - start, 3)
        result.response_text = str(getattr(response, "text", "") or "").strip()[:500]
        usage = getattr(response, "usage_metadata", None)
        result.prompt_tokens = _first_int(
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "promptTokenCount", None),
        )
        result.completion_tokens = _first_int(
            getattr(usage, "candidates_token_count", None),
            getattr(usage, "candidatesTokenCount", None),
        )
        result.total_tokens = _first_int(
            getattr(usage, "total_token_count", None),
            getattr(usage, "totalTokenCount", None),
        )
        result.status = "ok" if result.response_text else "empty_response"
    except Exception as exc:  # noqa: BLE001 - smoke script should capture provider-specific failures.
        result.latency_seconds = round(time.perf_counter() - start, 3)
        result.status = "error"
        result.error_type = type(exc).__name__
        result.error_message = str(exc)[:1000]
    return result


def _first_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, int):
            return value
    return None


def _should_try_fallback(result: ProbeResult) -> bool:
    text = f"{result.error_message or ''} {result.response_text or ''}".lower()
    return "not found" in text or "404" in text or "<!doctype html" in text or "<html" in text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="*",
        default=list(PROBES),
        choices=sorted(PROBES),
        help="Subset of model probes to run.",
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--output", default=None, help="Optional JSON output path.")
    args = parser.parse_args()

    _load_dotenv()
    results = [probe_model(PROBES[name], args.timeout, args.max_tokens) for name in args.models]
    payload = {
        "ok_count": sum(1 for r in results if r.status == "ok"),
        "total_count": len(results),
        "results": [asdict(r) for r in results],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 0 if all(r.status == "ok" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
