from __future__ import annotations

from datetime import datetime
from typing import Any

from dateutil.parser import isoparse

from skill_scout.http import build_http_client
from skill_scout.publishers import github_owner_from_url, normalize_company_name
from skill_scout.types import DiscoveredItem


MCP_BASE = "https://registry.modelcontextprotocol.io"


def _safe_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return isoparse(value)
    except Exception:
        return None


async def collect_mcp_registry(limit_total: int = 500) -> list[DiscoveredItem]:
    items: list[DiscoveredItem] = []

    async with build_http_client() as client:
        cursor: str | None = None
        while len(items) < limit_total:
            limit = min(100, limit_total - len(items))
            params: dict[str, Any] = {"limit": limit}
            if cursor:
                params["cursor"] = cursor

            r = await client.get(f"{MCP_BASE}/v0.1/servers", params=params)
            r.raise_for_status()
            data = r.json()

            servers = data.get("servers") or []
            meta = data.get("metadata") or {}
            cursor = meta.get("nextCursor")

            for s in servers:
                # server.json-like shape
                name = s.get("name") or ""
                title = s.get("title") or name
                desc = s.get("description") or ""
                version = s.get("version") or s.get("latestVersion") or None
                status = s.get("status") or None
                packages = s.get("packages") or None
                updated_at = _safe_dt(s.get("updatedAt") or s.get("updated_at"))

                url = s.get("homepage") or s.get("repository") or f"{MCP_BASE}/v0.1/servers/{name}"
                owner = github_owner_from_url(str(s.get("repository") or "")) or github_owner_from_url(str(url))
                publisher = normalize_company_name(owner or "") or owner

                items.append(
                    DiscoveredItem(
                        id=f"mcp:{name}",
                        type="mcp_server",
                        title=title,
                        description=desc,
                        source="mcp_registry",
                        url=url,
                        tags=["mcp"] + ([f"publisher:{owner}"] if owner else []) + ([f"company:{publisher}"] if publisher and normalize_company_name(publisher) else []),
                        publisher=publisher,
                        publisher_type="github_owner" if owner else None,
                        last_pushed_at=updated_at,
                        mcp_name=name or None,
                        mcp_version=str(version) if version else None,
                        mcp_status=str(status) if status else None,
                        mcp_packages_json=packages if isinstance(packages, (list, dict)) else None,
                    )
                )

            if not cursor or not servers:
                break

    return items
