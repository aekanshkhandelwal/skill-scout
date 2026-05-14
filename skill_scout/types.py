from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


ItemType = Literal["skill", "mcp_server", "plugin", "connector", "api", "hook", "other"]


@dataclass(frozen=True)
class DiscoveredItem:
    id: str
    type: ItemType
    title: str
    description: str
    source: str
    url: str
    tags: list[str] = field(default_factory=list)

    # Publisher attribution (best-effort)
    publisher: str | None = None  # e.g. "openai", "anthropic"
    publisher_type: str | None = None  # e.g. "github_owner", "inferred"

    # Optional metrics (used for “trending” scoring)
    stars: int | None = None
    forks: int | None = None
    watchers: int | None = None
    open_issues: int | None = None
    last_pushed_at: datetime | None = None

    # MCP-specific fields
    mcp_name: str | None = None
    mcp_version: str | None = None
    mcp_status: str | None = None
    mcp_packages_json: dict[str, Any] | None = None

    # Computed
    score: float | None = None
    score_breakdown_json: dict[str, Any] | None = None
