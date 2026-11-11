"""Logging: Render'da darhol ko'rinadi (buferlanmaydi) va maxfiy qiymatlar yashiriladi."""
import logging
import re
import sys

import config

_PATTERNS = [
    re.compile(r"(?<!\d)\d{6,}:[A-Za-z0-9_-]{25,}"),                 # bot token
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{10,}"),          # Authorization
    re.compile(r"(?i)((?:api[_-]?key|key|token|hash)=)[^&\s'\"]+"),
    re.compile(r"\b1[A-Za-z0-9_\-]{200,}={0,2}"),                # Telethon StringSession
]
CONFLICT_HINT = (
    " | MASLAHAT: shu BOT_TOKEN bilan boshqa joyda ham polling ishlayapti "
    "(Termux'da `python main.py`, eski Render instance yoki boshqa server). "
    "Faqat bittasi qolsin."
)


def _secret_values():
    vals = [config.BOT_TOKEN, config.AI_API_KEY, config.ENCRYPTION_KEY,
            config.TELETHON_SESSION_STRING, config.TELEGRAM_API_HASH]
    return [v for v in vals if v and len(v) >= 8]


def redact(text: str) -> str:
    for v in _secret_values():
        text = text.replace(v, "***")
    for p in _PATTERNS:
        if p.groups:
            text = p.sub(lambda m: m.group(1) + "***", text)
        else:
            text = p.sub("***", text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        text = redact(super().format(record))
        if "TelegramConflictError" in text and CONFLICT_HINT not in text:
            text += CONFLICT_HINT
        return text


def setup_logging(level=logging.INFO):
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
