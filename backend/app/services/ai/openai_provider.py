"""OpenAI-compatible provider.

Works against three things, picked via the ``mode`` argument:

- OpenAI cloud (``mode="openai"``) — uses ``openai_api_key`` / ``openai_base_url``.
- A locally hosted OpenAI-compatible server (``mode="local"``) — vLLM, Ollama,
  LM Studio, and friends all expose the same chat-completions interface.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from openai import AsyncOpenAI

from app.config import settings
from app.core.errors import UpstreamError
from app.services.ai._json import extract_json_object
from app.services.ai.base import AiResponse

logger = logging.getLogger(__name__)

Mode = Literal["openai", "local"]


class OpenAiCompatibleProvider:
    def __init__(
        self,
        *,
        mode: Mode,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        """Build a provider.

        When ``api_key``/``base_url``/``model`` are passed (BYOK path: a user
        has stored their own key in their profile), those win. Otherwise we
        fall back to the app-wide settings — that's the legacy admin-managed
        path used when an analysis is triggered without ``use_own_ai=true``.
        """
        self._mode = mode
        if api_key is not None:
            # BYOK / user-config path. Trust whatever the caller hands us.
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
            self._default_model = model or (
                settings.ai_model if mode == "openai" else settings.local_ai_model
            )
        elif mode == "openai":
            if not settings.openai_api_key:
                raise UpstreamError("OPENAI_API_KEY is not configured.")
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url or None,
            )
            self._default_model = settings.ai_model
        else:
            self._client = AsyncOpenAI(
                api_key=settings.local_ai_api_key or "dummy",
                base_url=settings.local_ai_base_url,
            )
            self._default_model = settings.local_ai_model

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> AiResponse:
        chosen = model or self._default_model
        max_t = max_tokens or settings.ai_max_tokens

        # Qwen 3.5/3.6 (and other recent reasoning-capable models) split
        # output into ``content`` (final answer) and ``reasoning_content``
        # (chain-of-thought). For analytical tasks like log coaching the
        # extra reasoning lifts quality, so default on for the local
        # provider. Set LOCAL_AI_ENABLE_THINKING=false in .env if you want
        # raw speed (~10s instead of ~30-60s) at a quality cost. The flag
        # is silently ignored by models that don't support it.
        thinking_enabled = (
            settings.local_ai_enable_thinking if self._mode == "local" else False
        )
        extra_body: dict[str, Any] = {
            "chat_template_kwargs": {"enable_thinking": thinking_enabled},
        }

        try:
            resp = await self._client.chat.completions.create(
                model=chosen,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_t,
                temperature=temperature,
                extra_body=extra_body,
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"{self._mode} chat completion failed: {exc}") from exc

        choice = resp.choices[0] if resp.choices else None
        message = choice.message if choice else None
        # Some models split output into ``content`` (final answer) and
        # ``reasoning_content`` (CoT). If reasoning was actually emitted,
        # the JSON might live in there — extract_json_object walks balanced
        # braces and will find it regardless.
        primary = (getattr(message, "content", None) or "").strip() if message else ""
        reasoning = (getattr(message, "reasoning_content", None) or "").strip() if message else ""
        if primary:
            text = primary
        elif reasoning:
            text = reasoning
        else:
            text = ""
        usage: Any = getattr(resp, "usage", None)
        structured: dict[str, Any] = {}
        try:
            structured = extract_json_object(text)
        except ValueError:
            logger.warning(
                "%s response did not contain a parseable JSON object; returning text only.",
                self._mode,
            )

        return AiResponse(
            text=text,
            structured=structured,
            model=chosen,
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )
