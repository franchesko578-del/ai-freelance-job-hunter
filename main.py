import asyncio
import logging
import os
import signal
from datetime import datetime, timedelta, timezone

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from app import db, runtime
from app.handlers import router
from app.log import setup_logging
from app.services.notify import send_to_admins
from app.services.scanner import scheduled_scan
from app.services.telethon_manager import manager

log = logging.getLogger("main")


async def health_handler(reader, writer):
    try:
        await asyncio.wait_for(reader.readline(), timeout=5)
        while True:
            header = await asyncio.wait_for(reader.readline(), timeout=5)
            if header in (b"\r\n", b"\n", b""):
                break
        body = b"AI Freelance Job Hunter is running"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"Connection: close\r\n\r\n" + body
        )
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def seed_sources():
    """SEED_SOURCES="telegram @kanal;rss https://..." — bazasi o'chib ketadigan hostinglar uchun."""
    if not config.SEED_SOURCES:
        return
    from app.services.sources import parse_source_input
    for chunk in config.SEED_SOURCES.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parsed, error = parse_source_input(chunk)
        if error:
            log.warning("SEED_SOURCES elementi o'tkazib yuborildi: %r", chunk[:60])
            continue
        if await db.add_source(*parsed):
            log.info("SEED manba qo'shildi: %s %s", *parsed)


async def run_polling(dp: Dispatcher, bot: Bot, stop: asyncio.Event):
    """Faqat bitta polling sikli. Xato bo'lsa jarayon qulamaydi, kutib qayta urinadi."""
    delay = 5
    while not stop.is_set():
        try:
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                handle_signals=False,
                close_bot_session=False,
            )
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("Polling to'xtadi: %s: %s. %s soniyadan keyin qayta uriniladi.",
                      type(exc).__name__, exc, delay)
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            delay = min(delay * 2, 60)


async def keepalive_loop(stop: asyncio.Event):
    """Render Free 15 daqiqa trafiksiz qolsa uxlaydi va skaner to'xtaydi.
    O'z jamoat URL'imizga har 10 daqiqada so'rov yuborib, uyg'oq turishga urinadi."""
    url = config.RENDER_EXTERNAL_URL
    if not (config.KEEPALIVE and url):
        return
    log.info("Keepalive yoqildi: %s", url)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        while not stop.is_set():
            try:
                async with session.get(url) as resp:
                    await resp.read()
            except Exception as exc:
                log.warning("Keepalive xatosi: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=600)
            except asyncio.TimeoutError:
                pass


async def main():
    setup_logging()
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN kiritilmagan")
    if not config.ADMIN_IDS:
        raise SystemExit("ADMIN_IDS kiritilmagan")

    await db.init_db()
    await seed_sources()

    bot = Bot(config.BOT_TOKEN)
    try:
        me = await bot.get_me()
    except Exception as exc:
        await bot.session.close()
        raise SystemExit(f"BOT_TOKEN yaroqsiz yoki Telegram'ga ulanib bo'lmadi: {type(exc).__name__}")
    log.info("Bot: @%s", me.username)
    # Webhook o'rnatilgan bo'lsa polling ishlamaydi
    await bot.delete_webhook(drop_pending_updates=False)

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    interval = await db.get_scan_interval()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_scan, "interval", minutes=interval, args=[bot], id="scan",
        replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=120,
        next_run_time=(datetime.now(timezone.utc) + timedelta(seconds=45)) if config.SCAN_ON_START else None,
    )
    scheduler.start()
    runtime.scheduler = scheduler

    port = int(os.getenv("PORT", "10000"))
    server = await asyncio.start_server(health_handler, "0.0.0.0", port)
    log.info("HTTP server port: %s", port)
    log.info("Bot ishga tushdi. Scan interval: %s daqiqa", interval)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass

    if config.NOTIFY_ON_START:
        created = await db.get_setting("db_created_at", "?")
        sources = len([s for s in await db.list_sources() if s[3]])
        await send_to_admins(
            bot,
            f"🟢 Bot ishga tushdi.\nFaol manbalar: {sources}\nBaza yaratilgan: {created}\n"
            "Agar bu sana har safar yangi bo‘lsa, baza saqlanmayapti (README’dagi persistent disk bo‘limiga qarang).\n"
            "/account — holat, /report — oxirgi hisobot.",
        )

    polling_task = asyncio.create_task(run_polling(dp, bot, stop), name="polling")
    stop_task = asyncio.create_task(stop.wait(), name="stop")
    keepalive_task = asyncio.create_task(keepalive_loop(stop), name="keepalive")
    try:
        async with server:
            done, _pending = await asyncio.wait({polling_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            if polling_task in done and not stop.is_set():
                exc = polling_task.exception()
                log.error("Polling kutilmaganda tugadi: %r", exc)
    finally:
        log.info("To'xtatilmoqda...")
        stop.set()
        try:
            await dp.stop_polling()
        except Exception:
            pass
        polling_task.cancel()
        stop_task.cancel()
        keepalive_task.cancel()
        scheduler.shutdown(wait=False)
        await manager.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
