from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import aiosqlite

from skill_scout.types import DiscoveredItem


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  source TEXT NOT NULL,
  url TEXT NOT NULL,
  tags_json TEXT NOT NULL,

  stars INTEGER,
  forks INTEGER,
  watchers INTEGER,
  open_issues INTEGER,
  last_pushed_at TEXT,

  mcp_name TEXT,
  mcp_version TEXT,
  mcp_status TEXT,
  mcp_packages_json TEXT,

  score REAL,
  score_breakdown_json TEXT,

  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_score ON items(score DESC);
CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_title ON items(title);
"""


async def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


def _dt_to_str(dt: datetime | None) -> str | None:
    return None if dt is None else dt.isoformat()


async def upsert_many(db_path: str, items: list[DiscoveredItem]) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN")
        for item in items:
            await db.execute(
                """
                INSERT INTO items (
                  id,type,title,description,source,url,tags_json,
                  stars,forks,watchers,open_issues,last_pushed_at,
                  mcp_name,mcp_version,mcp_status,mcp_packages_json,
                  score,score_breakdown_json,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  type=excluded.type,
                  title=excluded.title,
                  description=excluded.description,
                  source=excluded.source,
                  url=excluded.url,
                  tags_json=excluded.tags_json,
                  stars=excluded.stars,
                  forks=excluded.forks,
                  watchers=excluded.watchers,
                  open_issues=excluded.open_issues,
                  last_pushed_at=excluded.last_pushed_at,
                  mcp_name=excluded.mcp_name,
                  mcp_version=excluded.mcp_version,
                  mcp_status=excluded.mcp_status,
                  mcp_packages_json=excluded.mcp_packages_json,
                  score=excluded.score,
                  score_breakdown_json=excluded.score_breakdown_json,
                  updated_at=excluded.updated_at
                """,
                (
                    item.id,
                    item.type,
                    item.title,
                    item.description,
                    item.source,
                    item.url,
                    json.dumps(item.tags, ensure_ascii=False),
                    item.stars,
                    item.forks,
                    item.watchers,
                    item.open_issues,
                    _dt_to_str(item.last_pushed_at),
                    item.mcp_name,
                    item.mcp_version,
                    item.mcp_status,
                    None if item.mcp_packages_json is None else json.dumps(item.mcp_packages_json, ensure_ascii=False),
                    item.score,
                    None if item.score_breakdown_json is None else json.dumps(item.score_breakdown_json, ensure_ascii=False),
                    now,
                ),
            )
        await db.commit()


async def query_items(
    db_path: str,
    q: str | None,
    types: list[str] | None,
    limit: int,
    offset: int,
) -> list[dict]:
    where = []
    params: list[object] = []
    if q:
        q_norm = " ".join(str(q).strip().split())
        variants: list[str] = [q_norm]
        if " " in q_norm:
            variants.append(q_norm.replace(" ", ""))
            variants.append(q_norm.replace(" ", "-"))
            variants.extend(q_norm.split(" "))

        # De-dup, keep order, remove tiny tokens
        seen = set()
        cleaned: list[str] = []
        for v in variants:
            v = v.strip()
            if len(v) < 2:
                continue
            if v.lower() in seen:
                continue
            seen.add(v.lower())
            cleaned.append(v)

        # Match any variant in any text field (broad but user-friendly).
        ors: list[str] = []
        for _ in cleaned:
            ors.append("(title LIKE ? OR description LIKE ? OR tags_json LIKE ?)")
        where.append("(" + " OR ".join(ors) + ")")
        for v in cleaned:
            like = f"%{v}%"
            params.extend([like, like, like])
    if types:
        where.append("type IN (" + ",".join("?" for _ in types) + ")")
        params.extend(types)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
      SELECT id,type,title,description,source,url,tags_json,stars,forks,watchers,open_issues,last_pushed_at,
             mcp_name,mcp_version,mcp_status,mcp_packages_json,score,score_breakdown_json,updated_at
      FROM items
      {where_sql}
      ORDER BY score DESC, updated_at DESC
      LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(sql, params)
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "type": r["type"],
                    "title": r["title"],
                    "description": r["description"],
                    "source": r["source"],
                    "url": r["url"],
                    "tags": json.loads(r["tags_json"] or "[]"),
                    "stars": r["stars"],
                    "forks": r["forks"],
                    "watchers": r["watchers"],
                    "open_issues": r["open_issues"],
                    "last_pushed_at": r["last_pushed_at"],
                    "mcp_name": r["mcp_name"],
                    "mcp_version": r["mcp_version"],
                    "mcp_status": r["mcp_status"],
                    "mcp_packages": json.loads(r["mcp_packages_json"] or "null"),
                    "score": r["score"],
                    "score_breakdown": json.loads(r["score_breakdown_json"] or "null"),
                    "updated_at": r["updated_at"],
                }
            )
        return out


async def get_item(db_path: str, item_id: str) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        row = await db.execute_fetchone(
            """
            SELECT id,type,title,description,source,url,tags_json,stars,forks,watchers,open_issues,last_pushed_at,
                   mcp_name,mcp_version,mcp_status,mcp_packages_json,score,score_breakdown_json,updated_at
            FROM items WHERE id = ?
            """,
            (item_id,),
        )
        if row is None:
            return None
        return {
            "id": row["id"],
            "type": row["type"],
            "title": row["title"],
            "description": row["description"],
            "source": row["source"],
            "url": row["url"],
            "tags": json.loads(row["tags_json"] or "[]"),
            "stars": row["stars"],
            "forks": row["forks"],
            "watchers": row["watchers"],
            "open_issues": row["open_issues"],
            "last_pushed_at": row["last_pushed_at"],
            "mcp_name": row["mcp_name"],
            "mcp_version": row["mcp_version"],
            "mcp_status": row["mcp_status"],
            "mcp_packages": json.loads(row["mcp_packages_json"] or "null"),
            "score": row["score"],
            "score_breakdown": json.loads(row["score_breakdown_json"] or "null"),
            "updated_at": row["updated_at"],
        }


async def export_all(db_path: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """
            SELECT id,type,title,description,source,url,tags_json,stars,forks,watchers,open_issues,last_pushed_at,
                   mcp_name,mcp_version,mcp_status,mcp_packages_json,score,score_breakdown_json,updated_at
            FROM items
            ORDER BY score DESC, updated_at DESC
            """
        )
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "type": r["type"],
                    "title": r["title"],
                    "description": r["description"],
                    "source": r["source"],
                    "url": r["url"],
                    "tags": json.loads(r["tags_json"] or "[]"),
                    "stars": r["stars"],
                    "forks": r["forks"],
                    "watchers": r["watchers"],
                    "open_issues": r["open_issues"],
                    "last_pushed_at": r["last_pushed_at"],
                    "mcp_name": r["mcp_name"],
                    "mcp_version": r["mcp_version"],
                    "mcp_status": r["mcp_status"],
                    "mcp_packages": json.loads(r["mcp_packages_json"] or "null"),
                    "score": r["score"],
                    "score_breakdown": json.loads(r["score_breakdown_json"] or "null"),
                    "updated_at": r["updated_at"],
                }
            )
        return out
