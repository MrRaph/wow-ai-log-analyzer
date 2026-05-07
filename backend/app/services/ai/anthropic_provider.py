"""Anthropic Claude provider for structured analysis output."""
from __future__ import annotations

import json
import logging
from typing import Any

from anthropic import AsyncAnthropic

from app.config import settings
from app.core.errors import UpstreamError
from app.services.ai.base import AiResponse

logger = logging.getLogger(__name__)


class AnthropicProvider:
    def __init__(self, *, api_key: str | None = None) -> None:
        key = api_key or settings.anthropic_api_key
        if not key:
            raise UpstreamError("ANTHROPIC_API_KEY is not configured.")
        self._client = AsyncAnthropic(api_key=key)

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> AiResponse:
        chosen_model = model or settings.ai_model
        max_t = max_tokens or settings.ai_max_tokens
        try:
            message = await self._client.messages.create(
                model=chosen_model,
                max_tokens=max_t,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"Anthropic API call failed: {exc}") from exc

        text = "".join(part.text for part in message.content if getattr(part, "type", "") == "text")
        usage: Any = getattr(message, "usage", None)

        structured: dict[str, Any] = {}
        try:
            structured = _extract_json_object(text)
        except ValueError:
            logger.warning("Claude response did not contain a JSON object; returning text only.")

        return AiResponse(
            text=text,
            structured=structured,
            model=chosen_model,
            prompt_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )


def _extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first balanced JSON object from a free-form response."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                snippet = text[start : i + 1]
                return json.loads(snippet)
    raise ValueError("unterminated JSON object")
