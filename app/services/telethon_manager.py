"""Telethon klientini bitta joyda boshqaradi: ulanish, holat, manbani tekshirish.

Muhim: bir xil session (fayl yoki StringSession) bir vaqtda ikki joyda (Termux + Render)
ishlatilsa Telegram AuthKeyDuplicatedError beradi va sessiyani bekor qilishi mumkin.
"""
import asyncio
import logging

import config

log = logging.getLogger(__name__)


class TelegramUnavailable(Exception):
    """Telethon ishlamaydi. Matn admin uchun tushunarli (o'zbekcha)."""


def explain_error(exc: Exception) -> str:
    name = type(exc).__name__
    text = str(exc)
    table = {
        "AuthKeyDuplicatedError": (
            "Session bir vaqtda ikki joyda ishlatilgan (masalan Termux va Render). "
            "Telegram sessiyani bekor qilgan: sessiyani qayta yarating va faqat bitta joyda ishlating."),
        "AuthKeyUnregisteredError": "Session yaroqsiz yoki Telegram tomonidan o'chirilgan. Qayta yarating.",
        "SessionRevokedError": "Session bekor qilingan (akkauntdan chiqarilgan). Qayta yarating.",
        "SessionExpiredError": "Session muddati tugagan. Qayta yarating.",
        "UserDeactivatedError": "Telegram akkaunt o'chirilgan/bloklangan.",
        "UserDeactivatedBanError": "Telegram akkaunt bloklangan (ban).",
        "UsernameNotOccupiedError": "Bunday username mavjud emas. Yozilishini tekshiring.",
        "UsernameInvalidError": "Username formati noto'g'ri.",
        "ChannelPrivateError": "Kanal yopiq yoki akkaunt unga a'zo emas. Avval akkaunt bilan a'zo bo'ling.",
        "ChannelBannedError": "Akkaunt bu kanaldan bloklangan.",
        "ChatAdminRequiredError": "Bu chatni o'qish uchun admin huquqi kerak.",
        "InviteHashExpiredError": "Taklif havolasi eskirgan.",
    }
    if name in table:
        return table[name]
    if name == "FloodWaitError":
        secs = getattr(exc, "seconds", "?")
        return f"Telegram cheklovi (FloodWait): {secs} soniya kutish kerak."
    if name in ("ValueError",) and ("Cannot find any entity" in text or "No user has" in text):
        return "Manba topilmadi (username xato yoki akkaunt ko'ra olmaydi)."
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "Telegram serveriga ulanishda vaqt tugadi (timeout)."
    if isinstance(exc, (ConnectionError, OSError)):
        return f"Tarmoq xatosi: {name}."
    return f"{name}: {text[:150]}"


def config_problem() -> str | None:
    if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH:
        return "TELEGRAM_API_ID yoki TELEGRAM_API_HASH o'rnatilmagan."
    try:
        int(config.TELEGRAM_API_ID)
    except ValueError:
        return "TELEGRAM_API_ID raqam bo'lishi kerak."
    return None


def session_kind() -> str:
    if config.TELETHON_SESSION_STRING:
        return "StringSession (TELETHON_SESSION_STRING)"
    return "Session fayli (data/telethon.session)"


class TelethonManager:
    def __init__(self):
        self._client = None
        self._lock = asyncio.Lock()
        self._dialogs_loaded = False
        self.last_error: str | None = None
        self.last_ok_at: str | None = None

    def _make_client(self):
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        session = (StringSession(config.TELETHON_SESSION_STRING)
                   if config.TELETHON_SESSION_STRING else config.TELETHON_SESSION)
        return TelegramClient(
            session, int(config.TELEGRAM_API_ID), config.TELEGRAM_API_HASH,
            connection_retries=3, retry_delay=2, receive_updates=False,
        )

    async def ensure(self):
        """Ulangan va avtorizatsiyadan o'tgan klientni qaytaradi yoki TelegramUnavailable."""
        problem = config_problem()
        if problem:
            self.last_error = problem
            raise TelegramUnavailable(problem)
        async with self._lock:
            try:
                if self._client is None:
                    self._client = self._make_client()
                if not self._client.is_connected():
                    await asyncio.wait_for(self._client.connect(), timeout=30)
                if not await self._client.is_user_authorized():
                    if config.TELETHON_SESSION_STRING:
                        msg = ("TELETHON_SESSION_STRING yaroqsiz yoki avtorizatsiyadan o'tmagan. "
                               "Sessiyani qayta eksport qiling.")
                    else:
                        msg = ("Session fayli topilmadi/avtorizatsiya yo'q. Render'da fayl saqlanmaydi: "
                               "TELETHON_SESSION_STRING o'rnating.")
                    self.last_error = msg
                    raise TelegramUnavailable(msg)
            except TelegramUnavailable:
                raise
            except Exception as exc:
                self.last_error = explain_error(exc)
                log.warning("Telethon ulanish xatosi: %s", type(exc).__name__)
                await self._reset()
                raise TelegramUnavailable(self.last_error) from exc
            self.last_error = None
            return self._client

    async def _reset(self):
        client, self._client = self._client, None
        self._dialogs_loaded = False
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def close(self):
        async with self._lock:
            await self._reset()

    async def _resolve(self, client, value: str):
        value = value.strip()
        if value.lstrip("-").isdigit():
            if not self._dialogs_loaded:
                await client.get_dialogs(limit=None)
                self._dialogs_loaded = True
            return await client.get_input_entity(int(value))
        return await client.get_entity(value)

    async def fetch_messages(self, value: str, limit: int):
        """(entity, [xabarlar]) qaytaradi. Xatolar yuqoriga chiqadi (yashirilmaydi)."""
        client = await self.ensure()
        entity = await self._resolve(client, value)
        messages = []
        async for msg in client.iter_messages(entity, limit=limit):
            messages.append(msg)
        self.last_ok_at = _now()
        return entity, messages

    async def status(self) -> dict:
        info = {
            "configured": config_problem() is None,
            "config_problem": config_problem(),
            "session_kind": session_kind(),
            "connected": False,
            "authorized": False,
            "account": None,
            "error": None,
        }
        if info["config_problem"]:
            info["error"] = info["config_problem"]
            return info
        try:
            client = await self.ensure()
            info["connected"] = client.is_connected()
            info["authorized"] = True
            me = await asyncio.wait_for(client.get_me(), timeout=20)
            info["account"] = {
                "id": getattr(me, "id", None),
                "name": " ".join(x for x in (getattr(me, "first_name", None),
                                             getattr(me, "last_name", None)) if x) or "-",
                "username": getattr(me, "username", None),
            }
        except TelegramUnavailable as exc:
            info["error"] = str(exc)
            info["connected"] = bool(self._client and self._client.is_connected())
        except Exception as exc:
            info["error"] = explain_error(exc)
        return info

    async def check_source(self, value: str) -> dict:
        """Bitta Telegram manbani sinash: topiladimi, o'qiladimi."""
        out = {"value": value, "ok": False, "title": None, "kind": None,
               "messages": 0, "last_date": None, "error": None}
        try:
            entity, msgs = await self.fetch_messages(value, limit=5)
            out["ok"] = True
            out["title"] = getattr(entity, "title", None) or getattr(entity, "first_name", None)
            out["kind"] = type(entity).__name__
            out["messages"] = len(msgs)
            if msgs and msgs[0].date:
                out["last_date"] = msgs[0].date.strftime("%Y-%m-%d %H:%M UTC")
        except TelegramUnavailable as exc:
            out["error"] = str(exc)
        except Exception as exc:
            out["error"] = explain_error(exc)
        return out


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


manager = TelethonManager()
