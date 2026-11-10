import aiosqlite
from config import DATABASE_PATH

SCHEMA = (
"CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, value TEXT NOT NULL UNIQUE, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP);"
"CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, source_kind TEXT, external_id TEXT, title TEXT, text TEXT NOT NULL, url TEXT, language TEXT, category TEXT, confidence REAL DEFAULT 0, match_score INTEGER DEFAULT 0, reason TEXT, published_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, notified INTEGER DEFAULT 0, UNIQUE(source, external_id));"
"CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
)

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def add_source(kind, value):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO sources(kind,value) VALUES(?,?)", (kind, value.strip()))
        await db.commit()

async def list_sources():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT id,kind,value,enabled FROM sources ORDER BY id DESC")
        return await cur.fetchall()

async def toggle_source(source_id):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE sources SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (source_id,))
        await db.commit()

async def get_setting(key, default=None):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default

async def set_setting(key, value):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        await db.commit()

async def save_job(item):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            cur = await db.execute(
                "INSERT INTO jobs(source,source_kind,external_id,title,text,url,language,category,confidence,match_score,reason,published_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.get("source"), item.get("source_kind"), item.get("external_id"), item.get("title"),
                 item["text"], item.get("url"), item.get("language"), item.get("category"),
                 item.get("confidence", 0), item.get("match_score", 0), item.get("reason"), item.get("published_at"))
            )
            await db.commit()
            return cur.lastrowid
        except aiosqlite.IntegrityError:
            return None

async def mark_notified(job_id):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE jobs SET notified=1 WHERE id=?", (job_id,))
        await db.commit()

async def stats():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT COUNT(*), COALESCE(SUM(notified),0) FROM jobs")
        total, sent = await cur.fetchone()
        cur = await db.execute("SELECT COUNT(*) FROM sources WHERE enabled=1")
        sources = (await cur.fetchone())[0]
        return total or 0, sent or 0, sources

async def get_profile():
    return await get_setting("skills_profile", "Python, Telegram bot development, Aiogram, API integration, AI integration, websites, backend, databases, automation")

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
