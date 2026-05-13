from __future__ import annotations

import os

import httpx


def build_http_client() -> httpx.AsyncClient:
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
    headers = {"User-Agent": "skill-scout/0.1"}

    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    return httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True)
