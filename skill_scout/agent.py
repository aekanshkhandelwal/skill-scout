from __future__ import annotations

from typing import Any

from skill_scout.db import query_items
from skill_scout.llm.router import default_ranker


def _tokenize(text: str) -> list[str]:
    parts = []
    for raw in (text or "").lower().replace("-", " ").replace("_", " ").split():
        raw = raw.strip()
        if len(raw) < 2:
            continue
        parts.append(raw)
    return parts


def _relevance(prompt: str, item: dict[str, Any]) -> float:
    # Small heuristic: favor title/tag hits; then description.
    q = set(_tokenize(prompt))
    if not q:
        return 0.0
    title = set(_tokenize(item.get("title") or ""))
    tags = set(_tokenize(" ".join(item.get("tags") or [])))
    desc = set(_tokenize(item.get("description") or ""))
    return (
        len(q & title) * 3.0
        + len(q & tags) * 2.0
        + len(q & desc) * 1.0
    )


async def ask(db_path: str, prompt: str, types: list[str] | None, k: int = 10) -> dict[str, Any]:
    # Stage 1: local lexical search -> candidates
    candidates = await query_items(db_path=db_path, q=prompt, types=types, limit=80, offset=0)

    if not candidates:
        # Fallback: broaden search and rank by relevance+score.
        broader = await query_items(db_path=db_path, q=None, types=types, limit=200, offset=0)
        broader.sort(key=lambda it: (_relevance(prompt, it), it.get("score") or 0.0), reverse=True)
        candidates = broader[:80]

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
    candidates.sort(key=lambda it: (_relevance(prompt, it), it.get("score") or 0.0), reverse=True)
    top = candidates[:k]
    return {
        "recommended": [{"id": c["id"], "why": "Top match by local search + score"} for c in top],
        "notes": "Set `OPENAI_API_KEY` or `OLLAMA_HOST` to enable model-based reasoning and better matches.",
        "candidates_used": len(candidates),
    }
