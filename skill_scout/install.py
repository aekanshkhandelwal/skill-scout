from __future__ import annotations

from typing import Any


def install_hints(item: dict[str, Any]) -> list[str]:
    t = item.get("type")
    source = item.get("source")

    hints: list[str] = []

    if t == "mcp_server":
        packages = item.get("mcp_packages") or item.get("mcp_packages_json") or item.get("mcp_packages")  # defensive
        if isinstance(packages, list) and packages:
            p0 = packages[0]
            registry = p0.get("registryType") or p0.get("registry_type")
            ident = p0.get("identifier")
            ver = p0.get("version")
            if registry == "npm" and ident:
                suffix = f"@{ver}" if ver else ""
                hints.append(f"npx -y {ident}{suffix}")
            if registry == "pypi" and ident:
                suffix = f"=={ver}" if ver else ""
                hints.append(f"pip install {ident}{suffix}")
        if not hints:
            hints.append("Open the server URL and follow its install instructions.")
        return hints

    if t == "skill" and source == "github":
        url = item.get("url") or ""
        # Best-effort: point at Codex’s skill installer.
        hints.append(f"$skill-installer install {url}")
        hints.append(f"git clone {url} (then copy SKILL.md skill folder into your Codex skills directory)")
        return hints

    hints.append("Open the item URL and follow its install instructions.")
    return hints

