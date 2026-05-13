from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from skill_scout.db import get_item, init_db, query_items
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

    @app.get("/", response_class=HTMLResponse)
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

    return app
