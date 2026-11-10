import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_IDS, SCAN_INTERVAL_MINUTES
from app.db import init_db, get_setting
from app.handlers import router
from app.services.scanner import run_scan


async def health_handler(reader, writer):
    try:
        await reader.readline()

        while True:
            header = await reader.readline()
            if header in (b"\r\n", b"\n", b""):
                break

        body = b"AI Freelance Job Hunter is running"
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"Connection: close\r\n\r\n"
            + body
        )

        writer.write(response)
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()
        await writer.wait_closed()


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN kiritilmagan")

    if not ADMIN_IDS:
        raise RuntimeError("ADMIN_IDS kiritilmagan")

    await init_db()

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    interval = int(
        await get_setting("scan_interval", str(SCAN_INTERVAL_MINUTES))
    )

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_scan,
        "interval",
        minutes=interval,
        args=[bot, True],
        id="scan",
        replace_existing=True,
    )
    scheduler.start()

    port = int(os.getenv("PORT", "10000"))

    server = await asyncio.start_server(
        health_handler,
        "0.0.0.0",
        port,
    )

    print(f"HTTP server port: {port}")
    print(f"Bot ishga tushdi. Scan interval: {interval} daqiqa")

    polling_task = asyncio.create_task(
        dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    )

    try:
        async with server:
            await asyncio.gather(
                server.serve_forever(),
                polling_task,
            )
    finally:
        polling_task.cancel()
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
