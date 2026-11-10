from app.collectors.rss import collect_rss
from app.collectors.web import collect_web
from app.collectors.telethon_collector import collect_telegram_user
from app.services.classifier import classify
from app import db
from config import ADMIN_IDS

async def run_scan(bot=None, notify=True):
    collected = []
    for collector in (collect_telegram_user, collect_rss, collect_web):
        try:
            collected.extend(await collector())
        except Exception:
            continue
    sent = 0
    for item in collected:
        result = await classify(item["text"])
        if not result.get("relevant") or result.get("category") != "programming_job":
            continue
        item.update({
            "language":result.get("language"),
            "category":"programming_job",
            "confidence":float(result.get("confidence",0) or 0),
            "match_score":int(result.get("match_score",0) or 0),
            "reason":result.get("reason",""),
            "title":result.get("title") or item.get("title")
        })
        job_id = await db.save_job(item)
        if not job_id:
            continue
        if bot and notify:
            msg = (
                "🎯 <b>YANGI MOS DASTURLASH ISHI</b>\n\n"
                f"<b>{item.get('title') or 'Dasturlash loyihasi'}</b>\n"
                f"{result.get('task_summary','')}\n\n"
                f"📌 Moslik: {item['match_score']}/100\n"
                f"🧠 AI: {item['reason']}\n"
                f"🌐 Manba: {item.get('source')}\n"
                f"🔗 {item.get('url') or 'Havola mavjud emas'}"
            )
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, msg, parse_mode="HTML", disable_web_page_preview=True)
                except Exception:
                    pass
            await db.mark_notified(job_id)
            sent += 1
    return sent
