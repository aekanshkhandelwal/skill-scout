from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from skill_scout.http import build_http_client
from skill_scout.types import DiscoveredItem


AGENTSKILLS_DIR = "https://agentskills.to/skills"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


async def collect_agentskills_directory(limit_total: int = 250) -> list[DiscoveredItem]:
    # Community directory of SKILL.md-compatible skills.
    async with build_http_client() as client:
        r = await client.get(AGENTSKILLS_DIR)
        r.raise_for_status()
        html = r.text

    soup = BeautifulSoup(html, "html.parser")

    items: list[DiscoveredItem] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        if not href.startswith("/skills/"):
            continue
        title = _clean(a.get_text(" ", strip=True))
        if not title or len(title) < 2:
            continue
        url = "https://agentskills.to" + href
        item_id = f"agentskills_to:{href}"
        if item_id in seen:
            continue
        seen.add(item_id)

        desc = ""
        parent = a.parent
        if parent:
            desc = _clean(parent.get_text(" ", strip=True))
            # Remove title if it dominates the snippet
            if desc.lower().startswith(title.lower()):
                desc = _clean(desc[len(title) :])
        if not desc:
            desc = "Agent Skill listed in agentskills.to directory."

        items.append(
            DiscoveredItem(
                id=item_id,
                type="skill",
                title=title,
                description=desc[:400],
                source="agentskills_directory",
                url=url,
                tags=["skill", "directory", "agentskills", "skill_md"],
                stars=None,
                forks=None,
                last_pushed_at=None,
            )
        )
        if len(items) >= limit_total:
            break

    return items

