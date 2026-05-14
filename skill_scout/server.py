from __future__ import annotations

import os
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from skill_scout.collectors.antigravity_directory import collect_antigravity_mcp_directory
from skill_scout.collectors.agentskills_directory import collect_agentskills_directory
from skill_scout.collectors.claudskills_directory import collect_claudskills_directory
from skill_scout.collectors.github_skills import collect_github_skill_repos
from skill_scout.collectors.mcp_registry import collect_mcp_registry
from skill_scout.collectors.npm_registry import collect_npm_mcp
from skill_scout.db import count_items, get_item, init_db, query_items, upsert_many
from skill_scout.rank import compute_scores
from skill_scout.agent import ask
from skill_scout.install import install_hints


from dotenv import load_dotenv
import asyncio

def create_app(db_path: str) -> FastAPI:
    load_dotenv()
    app = FastAPI(title="Skill Scout", version="0.1.0")

    base_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(base_dir / "templates"))
    static_dir = base_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.on_event("startup")
    async def _startup() -> None:
        await init_db(db_path)

    async def _refresh_index() -> dict:
        async def _try(label: str, fn):
            try:
                res = await fn()
                return {"label": label, "count": len(res) if isinstance(res, list) else 0, "items": res if isinstance(res, list) else [], "error": None}
            except Exception as e:
                return {"label": label, "error": str(e), "count": 0, "items": []}

        # Run all collectors in parallel to avoid Vercel timeouts (10s limit)
        tasks = [
            _try("mcp_registry", collect_mcp_registry),
            _try("antigravity_directory", collect_antigravity_mcp_directory),
            _try("github", collect_github_skill_repos),
            _try("npm", collect_npm_mcp),
            _try("agentskills_directory", collect_agentskills_directory),
            _try("claudskills_directory", collect_claudskills_directory),
        ]
        
        collector_results = await asyncio.gather(*tasks)
        
        all_items = []
        status_report = []
        for r in collector_results:
            all_items.extend(r["items"])
            status_report.append({"label": r["label"], "count": r["count"], "error": r["error"]})

        scored = compute_scores(all_items)
        await upsert_many(db_path, scored)
        
        # Check for missing keys to warn user
        warnings = []
        if not os.getenv("GITHUB_TOKEN"):
            warnings.append("GITHUB_TOKEN missing: GitHub search may be rate-limited.")
        if not os.getenv("OPENAI_API_KEY"):
            warnings.append("OPENAI_API_KEY missing: Semantic ranking disabled.")

        return {
            "ok": True, 
            "total_indexed": len(scored), 
            "collectors": status_report,
            "warnings": warnings
        }

    @app.get("/", response_class=HTMLResponse)
    async def landing(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("landing.html", {"request": request})

    @app.get("/app", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "default_query": "",
                "default_types": ["mcp_server", "skill", "plugin", "connector", "api", "hook", "other"],
            },
        )

    @app.get("/api/items", response_class=JSONResponse)
    async def api_items(
        q: str | None = Query(default=None),
        types: list[str] | None = Query(default=None),
        sort: str = Query(default="score"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> JSONResponse:
        if sort not in ("score", "stars", "recent"):
            sort = "score"
        total = await count_items(db_path=db_path, q=q, types=types)
        rows = await query_items(db_path=db_path, q=q, types=types, limit=limit, offset=offset, sort=sort)
        return JSONResponse({"items": rows, "limit": limit, "offset": offset, "total": total, "sort": sort})

    @app.get("/api/items/{item_id}", response_class=JSONResponse)
    async def api_item(item_id: str) -> JSONResponse:
        row = await get_item(db_path=db_path, item_id=item_id)
        if not row:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(row)

    @app.get("/api/items/{item_id}/install", response_class=JSONResponse)
    async def api_install(item_id: str) -> JSONResponse:
        row = await get_item(db_path=db_path, item_id=item_id)
        if not row:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse({"id": item_id, "hints": install_hints(row)})

    @app.post("/api/ask", response_class=JSONResponse)
    async def api_ask(payload: dict) -> JSONResponse:
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            return JSONResponse({"error": "missing_prompt"}, status_code=400)
        types = payload.get("types")
        if types is not None and not isinstance(types, list):
            return JSONResponse({"error": "types_must_be_list"}, status_code=400)
        k = payload.get("k") or 10
        try:
            k_int = int(k)
        except Exception:
            return JSONResponse({"error": "k_must_be_int"}, status_code=400)
        k_int = max(1, min(20, k_int))
        return JSONResponse(await ask(db_path=db_path, prompt=prompt, types=types, k=k_int))

    @app.get("/healthz", response_class=JSONResponse)
    async def healthz() -> JSONResponse:
        return JSONResponse({"ok": True, "db": os.path.abspath(db_path)})

    @app.post("/api/refresh", response_class=JSONResponse)
    async def api_refresh(bg: BackgroundTasks) -> JSONResponse:
        # For serverless: do it inline so results are immediately available.
        # For long-running environments: could be switched to background.
        data = await _refresh_index()
        return JSONResponse(data)

    return app
