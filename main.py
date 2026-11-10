import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import BOT_TOKEN, ADMIN_IDS, SCAN_INTERVAL_MINUTES
from app.db import init_db, get_setting
from app.handlers import router
from app.services.scanner import run_scan

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN .env faylida kiritilmagan.")
    if not ADMIN_IDS:
        raise RuntimeError("ADMIN_IDS .env faylida kiritilmagan.")
    await init_db()
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    interval = int(await get_setting("scan_interval", str(SCAN_INTERVAL_MINUTES)))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_scan, "interval", minutes=interval, args=[bot, True], id="scan", replace_existing=True)
    scheduler.start()
    print(f"Bot ishga tushdi. Tekshirish intervali: {interval} daqiqa")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
