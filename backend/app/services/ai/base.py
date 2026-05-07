"""Provider-agnostic AI interface.

The analyzer composes a prompt and asks the provider for a JSON object that
matches ``AnalysisStructured``. We deliberately keep the interface tiny so
swapping providers (OpenAI, Ollama, ...) only means writing a sibling class.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class AiResponse:
    text: str
    structured: dict[str, Any]
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class AiProvider(Protocol):
    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> AiResponse: ...
