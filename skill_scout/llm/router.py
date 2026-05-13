from __future__ import annotations

from typing import Any, Protocol

from skill_scout.llm.ollama import OllamaClient
from skill_scout.llm.openai_compat import OpenAICompatClient


class Ranker(Protocol):
    def enabled(self) -> bool: ...

    async def rank(self, prompt: str, candidates: list[dict[str, Any]], k: int = 10) -> dict[str, Any]: ...


def default_ranker() -> Ranker | None:
    openai = OpenAICompatClient()
    if openai.enabled():
        return openai

    ollama = OllamaClient()
    if ollama.enabled():
        return ollama

    return None

