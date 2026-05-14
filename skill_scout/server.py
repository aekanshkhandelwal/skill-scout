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
from skill_scout.db import get_item, init_db, query_items, upsert_many
from skill_scout.rank import compute_scores
from skill_scout.agent import ask
from skill_scout.install import install_hints


def create_app(db_path: str) -> FastAPI:
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
                return await fn()
            except Exception as e:
                return {"label": label, "error": str(e), "count": 0, "items": []}

        results = []

        r1 = await _try("mcp_registry", collect_mcp_registry)
        if isinstance(r1, list):
            results.append({"label": "mcp_registry", "count": len(r1), "error": None})
            items = r1
        else:
            results.append(r1)
            items = []

        r2 = await _try("antigravity_directory", collect_antigravity_mcp_directory)
        if isinstance(r2, list):
            results.append({"label": "antigravity_directory", "count": len(r2), "error": None})
            items.extend(r2)
        else:
            results.append(r2)

        r3 = await _try("github", collect_github_skill_repos)
        if isinstance(r3, list):
            results.append({"label": "github", "count": len(r3), "error": None})
            items.extend(r3)
        else:
            results.append(r3)

        r4 = await _try("npm", collect_npm_mcp)
        if isinstance(r4, list):
            results.append({"label": "npm", "count": len(r4), "error": None})
            items.extend(r4)
        else:
            results.append(r4)

        r5 = await _try("agentskills_directory", collect_agentskills_directory)
        if isinstance(r5, list):
            results.append({"label": "agentskills_directory", "count": len(r5), "error": None})
            items.extend(r5)
        else:
            results.append(r5)

        r6 = await _try("claudskills_directory", collect_claudskills_directory)
        if isinstance(r6, list):
            results.append({"label": "claudskills_directory", "count": len(r6), "error": None})
            items.extend(r6)
        else:
            results.append(r6)

        scored = compute_scores(items)
        await upsert_many(db_path, scored)
        return {"ok": True, "total_indexed": len(scored), "collectors": results}

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
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> JSONResponse:
        rows = await query_items(db_path=db_path, q=q, types=types, limit=limit, offset=offset)
        return JSONResponse({"items": rows, "limit": limit, "offset": offset})

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
