from __future__ import annotations

import re

from bs4 import BeautifulSoup

from skill_scout.http import build_http_client
from skill_scout.types import DiscoveredItem


CLAUDSKILLS_ROOT = "https://claudskills.com"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


async def collect_claudskills_directory(limit_total: int = 250) -> list[DiscoveredItem]:
    # Community directory focused on Claude Code skills (SKILL.md-based).
    # Site doesn't expose a stable "/skills" index; we discover skill pages by crawling the home page.
    async with build_http_client() as client:
        r = await client.get(CLAUDSKILLS_ROOT)
        r.raise_for_status()
        html = r.text

    soup = BeautifulSoup(html, "html.parser")

    items: list[DiscoveredItem] = []
    seen: set[str] = set()

    # Heuristic: pages are often /skills/<slug>/ (deep links exist even if /skills index doesn't).
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        if not href.startswith("/skills/"):
            continue
        title = _clean(a.get_text(" ", strip=True))
        if not title or len(title) < 2:
            continue
        url = CLAUDSKILLS_ROOT + href
        item_id = f"claudskills:{href}"
        if item_id in seen:
            continue
        seen.add(item_id)

        desc = ""
        parent = a.parent
        if parent:
            desc = _clean(parent.get_text(" ", strip=True))
            if desc.lower().startswith(title.lower()):
                desc = _clean(desc[len(title) :])
        if not desc:
            desc = "Claude Code skill listed in claudskills.com directory."

        items.append(
            DiscoveredItem(
                id=item_id,
                type="skill",
                title=title,
                description=desc[:400],
                source="claudskills_directory",
                url=url,
                tags=["skill", "directory", "claude_code", "skill_md"],
            )
        )
        if len(items) >= limit_total:
            break

    return items
