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

  publisher TEXT,
  publisher_type TEXT,

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
        # Lightweight migrations for existing DBs
        cols = await db.execute_fetchall("PRAGMA table_info(items)")
        col_names = {c[1] for c in cols}  # (cid, name, type, notnull, dflt_value, pk)
        if "publisher" not in col_names:
            await db.execute("ALTER TABLE items ADD COLUMN publisher TEXT")
        if "publisher_type" not in col_names:
            await db.execute("ALTER TABLE items ADD COLUMN publisher_type TEXT")
        # Ensure index exists (no-op if already there)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_items_publisher ON items(publisher)")
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
                  publisher,publisher_type,
                  stars,forks,watchers,open_issues,last_pushed_at,
                  mcp_name,mcp_version,mcp_status,mcp_packages_json,
                  score,score_breakdown_json,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  type=excluded.type,
                  title=excluded.title,
                  description=excluded.description,
                  source=excluded.source,
                  url=excluded.url,
                  tags_json=excluded.tags_json,
                  publisher=excluded.publisher,
                  publisher_type=excluded.publisher_type,
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
                    item.publisher,
                    item.publisher_type,
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
    sort: str = "score",
) -> list[dict]:
    where = []
    params: list[object] = []
    if q:
        q_norm = " ".join(str(q).strip().split())
        # If user searches a company name, prefer items published by that company.
        # This is conservative: it's an OR clause, so it won't hide non-company matches.
        from skill_scout.publishers import normalize_company_name
        company = normalize_company_name(q_norm)
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
            ors.append("(title LIKE ? OR description LIKE ? OR tags_json LIKE ? OR publisher LIKE ?)")
        where.append("(" + " OR ".join(ors) + ")")
        for v in cleaned:
            like = f"%{v}%"
            params.extend([like, like, like, like])

        if company:
            where.append("(publisher = ? OR tags_json LIKE ?)")
            params.extend([company, f"%company:{company}%"])
    if types:
        where.append("type IN (" + ",".join("?" for _ in types) + ")")
        params.extend(types)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    order_by = "score DESC, updated_at DESC"
    if sort == "stars":
        order_by = "COALESCE(stars,0) DESC, score DESC, updated_at DESC"
    elif sort == "recent":
        order_by = "COALESCE(last_pushed_at,'') DESC, score DESC, updated_at DESC"

    sql = f"""
      SELECT id,type,title,description,source,url,tags_json,publisher,publisher_type,stars,forks,watchers,open_issues,last_pushed_at,
             mcp_name,mcp_version,mcp_status,mcp_packages_json,score,score_breakdown_json,updated_at
      FROM items
      {where_sql}
      ORDER BY {order_by}
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
                    "publisher": r["publisher"],
                    "publisher_type": r["publisher_type"],
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


async def count_items(db_path: str, q: str | None, types: list[str] | None) -> int:
    where = []
    params: list[object] = []
    if q:
        q_norm = " ".join(str(q).strip().split())
        variants: list[str] = [q_norm]
        if " " in q_norm:
            variants.append(q_norm.replace(" ", ""))
            variants.append(q_norm.replace(" ", "-"))
            variants.extend(q_norm.split(" "))

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

        ors: list[str] = []
        for _ in cleaned:
            ors.append("(title LIKE ? OR description LIKE ? OR tags_json LIKE ? OR publisher LIKE ?)")
        where.append("(" + " OR ".join(ors) + ")")
        for v in cleaned:
            like = f"%{v}%"
            params.extend([like, like, like, like])
    if types:
        where.append("type IN (" + ",".join("?" for _ in types) + ")")
        params.extend(types)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(f"SELECT COUNT(1) FROM items{where_sql}", params)
        row = await cur.fetchone()
        return int(row[0]) if row else 0


async def get_item(db_path: str, item_id: str) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        row = await db.execute_fetchone(
            """
            SELECT id,type,title,description,source,url,tags_json,publisher,publisher_type,stars,forks,watchers,open_issues,last_pushed_at,
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
            "publisher": row["publisher"],
            "publisher_type": row["publisher_type"],
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
            SELECT id,type,title,description,source,url,tags_json,publisher,publisher_type,stars,forks,watchers,open_issues,last_pushed_at,
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
                    "publisher": r["publisher"],
                    "publisher_type": r["publisher_type"],
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
