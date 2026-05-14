from __future__ import annotations

from datetime import datetime
from typing import Any

from dateutil.parser import isoparse

from skill_scout.http import build_http_client
from skill_scout.publishers import github_owner_from_url, normalize_company_name
from skill_scout.types import DiscoveredItem


NPM_SEARCH = "https://registry.npmjs.org/-/v1/search"


def _safe_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return isoparse(value)
    except Exception:
        return None


async def collect_npm_mcp(limit_total: int = 200) -> list[DiscoveredItem]:
    # Heuristics: surface likely MCP servers and related tooling.
    queries = [
        "mcp server",
        "model context protocol",
        "mcp-server",
    ]

    items: dict[str, DiscoveredItem] = {}

    async with build_http_client() as client:
        for q in queries:
            size = min(100, limit_total)
            params: dict[str, Any] = {"text": q, "size": size, "from": 0}
            r = await client.get(NPM_SEARCH, params=params)
            r.raise_for_status()
            data = r.json()
            for obj in data.get("objects") or []:
                pkg = (obj.get("package") or {}) if isinstance(obj, dict) else {}
                name = pkg.get("name")
                if not name:
                    continue
                version = pkg.get("version")
                desc = pkg.get("description") or ""
                links = pkg.get("links") or {}
                url = links.get("repository") or links.get("homepage") or links.get("npm") or f"https://www.npmjs.com/package/{name}"
                keywords = pkg.get("keywords") or []
                date = _safe_dt(pkg.get("date"))
                owner = github_owner_from_url(str(links.get("repository") or "")) or github_owner_from_url(str(url))
                publisher = normalize_company_name(owner or "") or owner

                tags = ["npm", "mcp", *[str(k) for k in keywords[:12]]]
                if owner:
                    tags.append(f"publisher:{owner}")
                if publisher and normalize_company_name(publisher):
                    tags.append(f"company:{publisher}")
                item = DiscoveredItem(
                    id=f"npm:{name}",
                    type="mcp_server" if "mcp" in " ".join([q, desc, " ".join(map(str, keywords))]).lower() else "other",
                    title=name,
                    description=desc,
                    source="npm",
                    url=url,
                    tags=list(dict.fromkeys(tags)),
                    last_pushed_at=date,
                    mcp_name=name if "mcp" in name.lower() else None,
                    mcp_version=str(version) if version else None,
                    publisher=publisher,
                    publisher_type="github_owner" if owner else None,
                )
                items[item.id] = item

    return list(items.values())[:limit_total]
