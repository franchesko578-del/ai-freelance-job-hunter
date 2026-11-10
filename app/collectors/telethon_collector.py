from telethon import TelegramClient
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELETHON_SESSION
from app.db import list_sources

async def collect_telegram_user():
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        return []
    try:
        api_id = int(TELEGRAM_API_ID)
    except ValueError:
        return []
    client = TelegramClient(TELETHON_SESSION, api_id, TELEGRAM_API_HASH)
    results = []
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return []
        for sid, kind, value, enabled in await list_sources():
            if not enabled or kind != "telegram":
                continue
            try:
                async for msg in client.iter_messages(value, limit=60):
                    body = msg.message or ""
                    if not body.strip():
                        continue
                    username = value.lstrip("@")
                    link = f"https://t.me/{username}/{msg.id}" if value.startswith("@") else None
                    results.append({"source":value,"source_kind":"telegram","external_id":str(msg.id),"title":body[:120].replace("\n"," "),"text":body,"url":link,"published_at":msg.date.isoformat() if msg.date else None})
            except Exception:
                continue
    finally:
        await client.disconnect()
    return results
