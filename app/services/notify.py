import html
import logging

import config

log = logging.getLogger(__name__)


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def format_job_message(job: dict, summary: str = "") -> str:
    title = job.get("title") or "Dasturlash loyihasi"
    lines = ["🎯 <b>YANGI MOS DASTURLASH ISHI</b>", "", f"<b>{esc(title)}</b>"]
    if summary:
        lines.append(esc(summary))
    lines += [
        "",
        f"📌 Moslik: {int(job.get('match_score') or 0)}/100",
        f"🧠 {esc(job.get('reason') or '')}",
        f"🌐 Manba: {esc(job.get('source'))}",
        f"🔗 {esc(job.get('url') or 'Havola mavjud emas')}",
    ]
    return "\n".join(lines)


async def send_to_admins(bot, text: str):
    """(yetkazilganlar_soni, xatolar_ro'yxati). Xatolar yutilmaydi — qaytariladi."""
    delivered, errors = 0, []
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML", disable_web_page_preview=True)
            delivered += 1
        except Exception as exc:
            name = type(exc).__name__
            detail = str(exc).replace("\n", " ")[:120]
            errors.append(f"{admin_id}: {name}: {detail}")
            log.warning("Admin %s ga xabar yuborilmadi: %s", admin_id, name)
    return delivered, errors
