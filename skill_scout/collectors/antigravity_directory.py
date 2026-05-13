from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from skill_scout.http import build_http_client
from skill_scout.types import DiscoveredItem


ANTIGRAVITY_MCP_DIR = "https://antigravity.codes/mcp"


def _clean(text: str) -> str:
    return re.sub(r"\\s+", " ", (text or "")).strip()


async def collect_antigravity_mcp_directory(limit_total: int = 400) -> list[DiscoveredItem]:
    # Note: This is a third-party directory (not an official registry). Treat as a discovery source only.
    async with build_http_client() as client:
        r = await client.get(ANTIGRAVITY_MCP_DIR)
        r.raise_for_status()
        html = r.text

    soup = BeautifulSoup(html, "html.parser")

    items: list[DiscoveredItem] = []

    # Heuristic extraction: cards often contain anchor + short description.
    # We scan all links under the /mcp path and build items from their surrounding text.
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        if not href:
            continue
        if not href.startswith("/mcp/"):
            continue
        title = _clean(a.get_text(" ", strip=True))
        if not title:
            continue

        url = "https://antigravity.codes" + href
        item_id = f"agdir:{href}"
        if item_id in seen:
            continue
        seen.add(item_id)

        # Pull a little nearby text as description.
        parent = a.parent
        desc = ""
        if parent:
            desc = _clean(parent.get_text(" ", strip=True))
            if title and desc.lower().startswith(title.lower()):
                desc = _clean(desc[len(title) :])

        if not desc:
            desc = "MCP server listed in Antigravity directory."

        items.append(
            DiscoveredItem(
                id=item_id,
                type="mcp_server",
                title=title,
                description=desc,
                source="antigravity_directory",
                url=url,
                tags=["mcp", "directory", "antigravity"],
                last_pushed_at=None,
                mcp_name=title,
                mcp_status="unverified",
                mcp_packages_json=None,
            )
        )

        if len(items) >= limit_total:
            break

    return items

