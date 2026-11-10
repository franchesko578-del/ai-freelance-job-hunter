import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
AI_PROVIDER = os.getenv("AI_PROVIDER", "none").strip().lower()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "").strip()
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "").strip()
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "jobs.db"))
SCAN_INTERVAL_MINUTES = max(5, int(os.getenv("SCAN_INTERVAL_MINUTES", "15")))
TELETHON_SESSION = str(DATA_DIR / "telethon")
TELETHON_SESSION_STRING = os.getenv("TELETHON_SESSION_STRING", "").strip()
