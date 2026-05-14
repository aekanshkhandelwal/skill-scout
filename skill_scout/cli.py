from __future__ import annotations

import argparse
import asyncio
import os
import json
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from skill_scout.collectors.github_skills import collect_github_skill_repos
from skill_scout.collectors.mcp_registry import collect_mcp_registry
from skill_scout.collectors.npm_registry import collect_npm_mcp
from skill_scout.collectors.antigravity_directory import collect_antigravity_mcp_directory
from skill_scout.collectors.agentskills_directory import collect_agentskills_directory
from skill_scout.collectors.claudskills_directory import collect_claudskills_directory
from skill_scout.db import export_all, init_db, upsert_many
from skill_scout.rank import compute_scores
from skill_scout.server import create_app


async def _refresh() -> None:
    load_dotenv()
    db_path = os.getenv("SKILL_SCOUT_DB", "./skill_scout.db")
    await init_db(db_path)

    async def _try(label: str, fn):
        try:
            return await fn()
        except Exception as e:
            print(f"[warn] collector_failed {label}: {e}")
            return []

    items = []
    items.extend(await _try("mcp_registry", collect_mcp_registry))
    items.extend(await _try("antigravity_directory", collect_antigravity_mcp_directory))
    items.extend(await _try("github", collect_github_skill_repos))
    items.extend(await _try("npm", collect_npm_mcp))
    items.extend(await _try("agentskills_directory", collect_agentskills_directory))
    items.extend(await _try("claudskills_directory", collect_claudskills_directory))

    scored = compute_scores(items)
    await upsert_many(db_path, scored)


def main() -> None:
    parser = argparse.ArgumentParser(prog="skill-scout")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("refresh", help="Fetch + index latest sources")

    export = sub.add_parser("export", help="Export current index to JSON")
    export.add_argument("--out", default="skill_scout_export.json")

    serve = sub.add_parser("serve", help="Run the web UI")
    serve.add_argument("--host", default=os.getenv("SKILL_SCOUT_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.getenv("SKILL_SCOUT_PORT", "8787")))

    args = parser.parse_args()

    if args.cmd == "refresh":
        asyncio.run(_refresh())
        return

    if args.cmd == "export":
        load_dotenv()
        db_path = os.getenv("SKILL_SCOUT_DB", "./skill_scout.db")
        data = asyncio.run(export_all(db_path))
        out_path = Path(args.out)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(str(out_path.resolve()))
        return

    if args.cmd == "serve":
        load_dotenv()
        app = create_app(os.getenv("SKILL_SCOUT_DB", "./skill_scout.db"))
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return


if __name__ == "__main__":
    main()
