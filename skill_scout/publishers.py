from __future__ import annotations

import re
from urllib.parse import urlparse


COMPANY_ALIASES: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "gemini": "google",  # Gemini is a Google brand
    "deepmind": "google",
    "microsoft": "microsoft",
    "nvidia": "nvidia",
}


def normalize_company_name(text: str) -> str | None:
    if not text:
        return None
    key = re.sub(r"[^a-z0-9]+", "", text.lower())
    if not key:
        return None
    return COMPANY_ALIASES.get(key) or None


def github_owner_from_url(url: str) -> str | None:
    try:
        p = urlparse(url)
    except Exception:
        return None
    if p.netloc.lower() not in ("github.com", "www.github.com"):
        return None
    parts = [x for x in p.path.split("/") if x]
    if len(parts) < 2:
        return None
    return parts[0].lower()

