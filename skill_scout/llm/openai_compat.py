from __future__ import annotations

import json
import os
from typing import Any

import httpx


class OpenAICompatClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com").rstrip("/")
        self.model = os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"

    def enabled(self) -> bool:
        return bool(self.api_key)

    async def rank(self, prompt: str, candidates: list[dict[str, Any]], k: int = 10) -> dict[str, Any]:
        if not self.enabled():
            raise RuntimeError("OPENAI_API_KEY is not set")

        system = (
            "You are Skill Scout, an expert at selecting developer tools. "
            "Given a user prompt and a list of candidates, return a strict JSON object with:\n"
            "{ \"recommended\": [ {\"id\": string, \"why\": string} ], \"notes\": string }\n"
            f"Pick up to {k} items. Prefer items that match the prompt, are maintained, and are safe.\n"
            "Do not include items not present in the candidates list."
        )

        user = {
            "prompt": prompt,
            "candidates": [
                {
                    "id": c.get("id"),
                    "type": c.get("type"),
                    "title": c.get("title"),
                    "description": c.get("description"),
                    "tags": c.get("tags"),
                    "url": c.get("url"),
                    "score": c.get("score"),
                    "stars": c.get("stars"),
                    "last_pushed_at": c.get("last_pushed_at"),
                }
                for c in candidates
            ],
        }

        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
        }

        headers = {"Authorization": f"Bearer {self.api_key}"}
        # OPENAI_BASE_URL may already include "/v1" (e.g. some OpenAI-compatible gateways).
        endpoint = f"{self.base_url}/chat/completions" if self.base_url.endswith("/v1") else f"{self.base_url}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            r = await client.post(endpoint, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        content = data["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except Exception as e:
            raise RuntimeError(f"Model returned non-JSON: {e}") from e
