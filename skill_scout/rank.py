from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timezone

from skill_scout.types import DiscoveredItem


def _days_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    return max(delta.total_seconds() / 86400.0, 0.0)


def compute_scores(items: list[DiscoveredItem]) -> list[DiscoveredItem]:
    scored: list[DiscoveredItem] = []

    for item in items:
        stars = item.stars or 0
        forks = item.forks or 0
        days = _days_since(item.last_pushed_at)

        # Simple “trending-ish” heuristic:
        # - popularity (log stars + forks)
        # - recency boost for recent updates
        pop = math.log10(stars + 1) * 2.0 + math.log10(forks + 1) * 1.0
        rec = 0.0
        if days is not None:
            # 0..1 where 0 days => 1, 30 days => ~0.37, 90 days => ~0.05
            rec = math.exp(-days / 30.0)

        base = 0.0
        if item.type == "mcp_server":
            base = 1.0
        elif item.type == "skill":
            base = 0.8
        else:
            base = 0.5

        score = base + pop + rec * 2.0

        breakdown = {"base": base, "popularity": pop, "recency_boost": rec * 2.0, "stars": stars, "forks": forks, "days_since_push": days}

        scored.append(replace(item, score=float(score), score_breakdown_json=breakdown))

    return scored
