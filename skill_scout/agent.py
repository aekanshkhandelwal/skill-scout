from __future__ import annotations

from typing import Any

from skill_scout.db import query_items
from skill_scout.llm.router import default_ranker


async def ask(db_path: str, prompt: str, types: list[str] | None, k: int = 10) -> dict[str, Any]:
    # Stage 1: local lexical search -> candidates
    candidates = await query_items(db_path=db_path, q=prompt, types=types, limit=80, offset=0)

    # Stage 2: optional model re-rank
    ranker = default_ranker()
    if ranker is not None:
        try:
            ranked = await ranker.rank(prompt=prompt, candidates=candidates, k=k)
            ranked["candidates_used"] = len(candidates)
            return ranked
        except Exception as e:
            return {"recommended": [], "notes": f"Model ranking failed: {e}", "candidates_used": len(candidates)}

    # Fallback: top-by-score
    top = candidates[:k]
    return {
        "recommended": [{"id": c["id"], "why": "Top match by local search + score"} for c in top],
        "notes": "Set `OPENAI_API_KEY` or `OLLAMA_HOST` to enable model-based reasoning and better matches.",
        "candidates_used": len(candidates),
    }
