from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from dateutil.parser import isoparse

from skill_scout.http import build_http_client
from skill_scout.types import DiscoveredItem


GITHUB_API = "https://api.github.com"


def _safe_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return isoparse(value)
    except Exception:
        return None


def _repo_to_item(repo: dict[str, Any], reason_tag: str) -> DiscoveredItem:
    full_name = repo.get("full_name") or repo.get("name") or "unknown"
    html_url = repo.get("html_url") or ""
    desc = repo.get("description") or ""
    topics = repo.get("topics") or []
    pushed_at = _safe_dt(repo.get("pushed_at"))

    tags = list({reason_tag, "github", *topics})
    title = repo.get("name") or full_name

    topics_l = {str(t).lower() for t in topics}
    inferred_type = "skill"
    if "connector" in topics_l or "connectors" in topics_l:
        inferred_type = "connector"
    elif "plugin" in topics_l or "plugins" in topics_l:
        inferred_type = "plugin"
    elif "hook" in topics_l or "hooks" in topics_l:
        inferred_type = "hook"
    elif "api" in topics_l or "sdk" in topics_l:
        inferred_type = "api"

    return DiscoveredItem(
        id=f"gh:{full_name}",
        type=inferred_type,  # type: ignore[arg-type]
        title=title,
        description=desc,
        source="github",
        url=html_url,
        tags=tags,
        stars=repo.get("stargazers_count"),
        forks=repo.get("forks_count"),
        watchers=repo.get("watchers_count"),
        open_issues=repo.get("open_issues_count"),
        last_pushed_at=pushed_at,
    )


async def _search_repos(query: str, per_page: int = 50) -> list[dict[str, Any]]:
    async with build_http_client() as client:
        headers = {"Accept": "application/vnd.github+json"}
        r = await client.get(
            f"{GITHUB_API}/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": per_page},
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("items") or []


async def _code_search_skill_md(per_page: int = 30) -> list[dict[str, Any]]:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        # GitHub code search is heavily rate-limited unauthenticated; skip unless token present.
        return []

    async with build_http_client() as client:
        headers = {"Accept": "application/vnd.github+json"}
        r = await client.get(
            f"{GITHUB_API}/search/code",
            params={
                "q": 'filename:SKILL.md ("codex" OR "agentskills" OR "claude code" OR "openai")',
                "per_page": per_page,
            },
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("items") or []


async def collect_github_skill_repos(limit_total: int = 200) -> list[DiscoveredItem]:
    repos: list[dict[str, Any]] = []

    # 1) Strong known source: openai/skills (curated + experimental)
    async with build_http_client() as client:
        r = await client.get(f"{GITHUB_API}/repos/openai/skills", headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 200:
            repos.append(r.json())

    # 2) Common topics used by SKILL.md ecosystems (run as separate searches; GitHub query parser is picky)
    repos.extend(await _search_repos("topic:agentskills", per_page=50))
    repos.extend(await _search_repos('topic:"agent-skills"', per_page=50))
    repos.extend(await _search_repos("topic:mcp", per_page=50))
    repos.extend(await _search_repos('SKILL.md in:readme', per_page=50))

    # 3) Code search for filename:SKILL.md (token recommended)
    code_hits = await _code_search_skill_md(per_page=50)
    for hit in code_hits:
        repo = hit.get("repository")
        if repo:
            repos.append(repo)

    dedup: dict[str, dict[str, Any]] = {}
    for r in repos:
        full = r.get("full_name") or r.get("name")
        if not full:
            continue
        dedup[full] = r

    items: list[DiscoveredItem] = []
    for repo in list(dedup.values())[:limit_total]:
        reason = "skill_md"
        items.append(_repo_to_item(repo, reason_tag=reason))
    return items
