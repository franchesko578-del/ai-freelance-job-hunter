import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _int_env(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _parse_admin_ids(raw: str) -> set[int]:
    ids = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))

AI_PROVIDER = os.getenv("AI_PROVIDER", "none").strip().lower() or "none"
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "").strip()
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "").strip()

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
TELETHON_SESSION = str(DATA_DIR / "telethon")
TELETHON_SESSION_STRING = os.getenv("TELETHON_SESSION_STRING", "").strip()

DATABASE_PATH = os.getenv("DATABASE_PATH", "").strip() or str(DATA_DIR / "jobs.db")
SCAN_INTERVAL_MINUTES = _int_env("SCAN_INTERVAL_MINUTES", 15, minimum=5)

# Qo'shimcha (ixtiyoriy) sozlamalar
MAX_MESSAGES_PER_SOURCE = _int_env("MAX_MESSAGES_PER_SOURCE", 60, minimum=5)
MAX_AGE_HOURS = _int_env("MAX_AGE_HOURS", 72, minimum=0)  # 0 = eski postlarni filtrlamaslik
AI_CONCURRENCY = _int_env("AI_CONCURRENCY", 3, minimum=1)
SCAN_ON_START = os.getenv("SCAN_ON_START", "1").strip() != "0"
NOTIFY_ON_START = os.getenv("NOTIFY_ON_START", "1").strip() != "0"
# Masalan: SEED_SOURCES="telegram @freelancer_Uzbek;rss https://site/feed.xml"
SEED_SOURCES = os.getenv("SEED_SOURCES", "").strip()

KEEPALIVE = os.getenv("KEEPALIVE", "1").strip() != "0"
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip()
ON_RENDER = os.getenv("RENDER", "").strip().lower() == "true"
