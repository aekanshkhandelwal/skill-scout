from __future__ import annotations

import json
import os
from typing import Any

import httpx


class OllamaClient:
    def __init__(self) -> None:
        self.host = (os.getenv("OLLAMA_HOST") or "").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL") or "llama3.1"

    def enabled(self) -> bool:
        return bool(self.host)

    async def rank(self, prompt: str, candidates: list[dict[str, Any]], k: int = 10) -> dict[str, Any]:
        if not self.enabled():
            raise RuntimeError("OLLAMA_HOST is not set")

        system = (
            "You are Skill Scout. Return strict JSON only:\n"
            '{ "recommended": [ {"id": string, "why": string} ], "notes": string }\n'
            f"Pick up to {k} items, only from the provided candidates."
        )
        user = {"prompt": prompt, "candidates": candidates}
        payload = {
            "model": self.model,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            r = await client.post(f"{self.host}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()

        content = data.get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except Exception as e:
            raise RuntimeError(f"Ollama returned non-JSON: {e}") from e

