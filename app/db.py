import json
import os
from datetime import datetime, timedelta, timezone

import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    value TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT, source_kind TEXT, external_id TEXT, title TEXT,
    text TEXT NOT NULL, url TEXT, language TEXT, category TEXT,
    confidence REAL DEFAULT 0, match_score INTEGER DEFAULT 0, reason TEXT,
    published_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    notified INTEGER DEFAULT 0,
    UNIQUE(source, external_id)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS seen_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    category TEXT,
    reason TEXT,
    engine TEXT,
    snippet TEXT,
    text_hash TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_seen_hash ON seen_items(text_hash);
CREATE INDEX IF NOT EXISTS idx_seen_created ON seen_items(created_at);
"""


def _connect():
    return aiosqlite.connect(config.DATABASE_PATH, timeout=30)


def _ensure_columns_sql():
    return ["ALTER TABLE jobs ADD COLUMN text_hash TEXT"]


async def init_db():
    parent = os.path.dirname(os.path.abspath(config.DATABASE_PATH))
    os.makedirs(parent, exist_ok=True)
    async with _connect() as db:
        await db.executescript(SCHEMA)
        cur = await db.execute("PRAGMA table_info(jobs)")
        cols = {r[1] for r in await cur.fetchall()}
        if "text_hash" not in cols:
            for sql in _ensure_columns_sql():
                await db.execute(sql)
        await db.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES('db_created_at',?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
        )
        await db.commit()


# ---------- Manbalar ----------
async def add_source(kind, value) -> bool:
    """True = yangi qo'shildi, False = allaqachon bor."""
    async with _connect() as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO sources(kind,value) VALUES(?,?)", (kind, value.strip())
        )
        await db.commit()
        return cur.rowcount > 0


async def list_sources():
    async with _connect() as db:
        cur = await db.execute("SELECT id,kind,value,enabled FROM sources ORDER BY id ASC")
        return await cur.fetchall()


async def get_source(source_id):
    async with _connect() as db:
        cur = await db.execute(
            "SELECT id,kind,value,enabled FROM sources WHERE id=?", (source_id,)
        )
        return await cur.fetchone()


async def toggle_source(source_id):
    async with _connect() as db:
        await db.execute(
            "UPDATE sources SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END WHERE id=?",
            (source_id,),
        )
        await db.commit()


async def delete_source(source_id) -> bool:
    async with _connect() as db:
        cur = await db.execute("DELETE FROM sources WHERE id=?", (source_id,))
        await db.commit()
        return cur.rowcount > 0


# ---------- Sozlamalar ----------
async def get_setting(key, default=None):
    async with _connect() as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default


async def set_setting(key, value):
    async with _connect() as db:
        await db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await db.commit()


async def get_json_setting(key, default=None):
    raw = await get_setting(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        return default


async def set_json_setting(key, value):
    await set_setting(key, json.dumps(value, ensure_ascii=False))


async def get_scan_interval() -> int:
    raw = await get_setting("scan_interval", str(config.SCAN_INTERVAL_MINUTES))
    try:
        return max(5, min(1440, int(raw)))
    except (TypeError, ValueError):
        return config.SCAN_INTERVAL_MINUTES


# ---------- Takroriylikni aniqlash ----------
async def get_known_keys():
    """Avval ko'rilgan (source, external_id) juftliklari: qabul qilinganlar ham, rad etilganlar ham."""
    async with _connect() as db:
        cur = await db.execute(
            "SELECT source, external_id FROM seen_items UNION SELECT source, external_id FROM jobs"
        )
        return {(r[0], r[1]) for r in await cur.fetchall()}


async def hash_is_known(text_hash) -> bool:
    """Xuddi shu matn boshqa manbada allaqachon qabul qilinganmi."""
    async with _connect() as db:
        cur = await db.execute(
            "SELECT 1 FROM jobs WHERE text_hash=? LIMIT 1", (text_hash,)
        )
        return (await cur.fetchone()) is not None


async def mark_seen(source, external_id, verdict, category=None, reason=None,
                    engine=None, snippet=None, text_hash=None):
    async with _connect() as db:
        await db.execute(
            "INSERT OR IGNORE INTO seen_items"
            "(source,external_id,verdict,category,reason,engine,snippet,text_hash) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (source, str(external_id), verdict, category, reason, engine,
             (snippet or "")[:160], text_hash),
        )
        await db.commit()


async def recent_rejected(limit=10):
    async with _connect() as db:
        cur = await db.execute(
            "SELECT source, category, reason, snippet, engine, created_at FROM seen_items "
            "WHERE verdict='rejected' ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return await cur.fetchall()


async def rejected_breakdown():
    async with _connect() as db:
        cur = await db.execute(
            "SELECT COALESCE(category,'noma''lum'), COUNT(*) FROM seen_items "
            "WHERE verdict='rejected' GROUP BY 1 ORDER BY 2 DESC"
        )
        return await cur.fetchall()


async def prune_seen(days=60):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    async with _connect() as db:
        await db.execute("DELETE FROM seen_items WHERE created_at < ?", (cutoff,))
        await db.commit()


# ---------- E'lonlar ----------
async def save_job(item):
    """Yangi id yoki None (takroriy bo'lsa)."""
    async with _connect() as db:
        try:
            cur = await db.execute(
                "INSERT INTO jobs(source,source_kind,external_id,title,text,url,language,"
                "category,confidence,match_score,reason,published_at,text_hash) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.get("source"), item.get("source_kind"), str(item.get("external_id")),
                 item.get("title"), item["text"], item.get("url"), item.get("language"),
                 item.get("category"), item.get("confidence", 0), item.get("match_score", 0),
                 item.get("reason"), item.get("published_at"), item.get("text_hash")),
            )
            await db.commit()
            return cur.lastrowid
        except aiosqlite.IntegrityError:
            return None


async def mark_notified(job_id):
    async with _connect() as db:
        await db.execute("UPDATE jobs SET notified=1 WHERE id=?", (job_id,))
        await db.commit()


async def unnotified_jobs(limit=20):
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM jobs WHERE notified=0 ORDER BY id ASC LIMIT ?", (limit,)
        )
        return [dict(r) for r in await cur.fetchall()]


async def stats():
    async with _connect() as db:
        cur = await db.execute("SELECT COUNT(*), COALESCE(SUM(notified),0) FROM jobs")
        total, sent = await cur.fetchone()
        cur = await db.execute("SELECT COUNT(*) FROM sources WHERE enabled=1")
        sources = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM seen_items WHERE verdict='rejected'")
        rejected = (await cur.fetchone())[0]
        return total or 0, sent or 0, sources, rejected or 0


# ---------- Profil va AI kalit ----------
DEFAULT_PROFILE = (
    "Python, Telegram bot development, Aiogram, API integration, AI integration, "
    "websites, backend, databases, automation"
)


async def get_profile():
    return await get_setting("skills_profile", DEFAULT_PROFILE)


async def set_profile(value):
    await set_setting("skills_profile", value)


async def save_encrypted_api_key(value, fernet):
    await set_setting("ai_api_key_encrypted", fernet.encrypt(value.encode()).decode())


async def load_encrypted_api_key(fernet):
    value = await get_setting("ai_api_key_encrypted")
    if not value:
        return None
    try:
        return fernet.decrypt(value.encode()).decode()
    except Exception:
        return None
