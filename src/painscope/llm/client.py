"""OpenRouter-backed LLM client. Any model, one interface.

We use the OpenAI SDK pointed at OpenRouter's OpenAI-compatible endpoint.
This gives us access to ~75 models (Claude, Gemini, GPT, Qwen, Llama, etc.)
without vendor lock-in. Model is a runtime parameter.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

from painscope.config import get_settings

logger = logging.getLogger(__name__)


def _client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
        default_headers={
            # OpenRouter recommends these for ranking/analytics
            "HTTP-Referer": "https://github.com/hbozkurt/painscope",
            "X-Title": "painscope",
        },
    )


def complete_json(
    prompt: str,
    *,
    model: str | None = None,
    language: str = "tr",
    schema_hint: str = "",
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Send a prompt and get structured JSON back.

    We request JSON in the prompt itself rather than relying on provider-
    specific response_format features, since OpenRouter spans many models
    with varying structured-output support.
    """
    settings = get_settings()

    if model is None:
        model = settings.llm_model_tr if language == "tr" else settings.llm_model_en

    system = (
        "You respond ONLY with a single valid JSON object. "
        "No preamble, no explanation, no markdown fences. "
        "If a schema is provided, match it exactly."
    )
    if schema_hint:
        system += f"\n\nExpected JSON schema hint:\n{schema_hint}"

    try:
        response = _client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
        )
    except Exception as e:
        logger.warning(f"Primary model {model} failed: {e}. Trying fallback.")
        response = _client().chat.completions.create(
            model=settings.llm_model_fallback,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
        )

    text = response.choices[0].message.content or "{}"
    text = text.strip()
    # Strip accidental markdown fences some models still emit
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from model response: {text[:500]}")
        raise ValueError(f"Model did not return valid JSON: {e}") from e


def complete_structured(
    prompt: str,
    schema: type[T],
    *,
    model: str | None = None,
    language: str = "tr",
    temperature: float = 0.2,
) -> T:
    """Send a prompt and parse response into a Pydantic model."""
    schema_hint = json.dumps(schema.model_json_schema(), indent=2)
    raw = complete_json(
        prompt,
        model=model,
        language=language,
        schema_hint=schema_hint,
        temperature=temperature,
    )
    return schema.model_validate(raw)
