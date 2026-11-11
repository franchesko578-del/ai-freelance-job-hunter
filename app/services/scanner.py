import asyncio
import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import config
from app import db, runtime
from app.collectors.base import CollectorResult, short_error
from app.collectors.rss import collect_rss
from app.collectors.telethon_collector import collect_telegram_user
from app.collectors.web import collect_web
from app.services.classifier import classify, normalize
from app.services.notify import format_job_message, send_to_admins
from app.services.report import ScanReport, now_str

log = logging.getLogger(__name__)

COLLECTORS = (
    ("telegram", collect_telegram_user),
    ("rss", collect_rss),
    ("web", collect_web),
)


def text_hash(text: str) -> str:
    norm = re.sub(r"\s+", " ", normalize(text)).strip()[:1000]
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def parse_published(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_too_old(item) -> bool:
    if config.MAX_AGE_HOURS <= 0:
        return False
    dt = parse_published(item.get("published_at"))
    if dt is None:
        return False
    return datetime.now(timezone.utc) - dt > timedelta(hours=config.MAX_AGE_HOURS)


def summarize_collector(result: CollectorResult) -> dict:
    return {
        "sources_total": len(result.sources),
        "sources_ok": sum(1 for s in result.sources if s.ok),
        "sources_failed": sum(1 for s in result.sources if not s.ok),
        "fetched": result.fetched,
        "error": result.error,
        "source_errors": [{"value": s.value, "error": s.error} for s in result.sources if not s.ok],
        "source_notes": [{"value": s.value, "note": s.note} for s in result.sources if s.note and s.ok],
    }


async def collect_all(report: ScanReport):
    items = []
    for name, collector in COLLECTORS:
        try:
            result = await collector()
        except Exception as exc:  # collector butunlay qulasa ham sabab ko'rinadi
            log.exception("%s collector qulab tushdi", name)
            result = CollectorResult(name=name, error="Collector xatosi: " + short_error(exc))
        report.collectors[name] = summarize_collector(result)
        items.extend(result.items)
    report.read_total = len(items)
    return items


async def _notify_job(bot, job_id, message, report: ScanReport):
    delivered, errors = await send_to_admins(bot, message)
    if delivered:
        await db.mark_notified(job_id)
        report.notified += 1
    else:
        report.notify_failed += 1
    for err in errors:
        if err not in report.notify_errors:
            report.notify_errors.append(err)
    return delivered


async def process_items(items, bot=None, notify=True, report: ScanReport | None = None) -> ScanReport:
    """Dedup -> eski filtr -> tasniflash -> saqlash -> xabar yuborish. Har bosqich hisoblanadi."""
    report = report or ScanReport()
    known = await db.get_known_keys()
    batch_hashes = set()
    fresh = []
    for item in items:
        key = (item.get("source"), str(item.get("external_id")))
        if key in known:
            report.known_duplicates += 1
            continue
        known.add(key)
        if is_too_old(item):
            report.too_old += 1
            await db.mark_seen(key[0], key[1], "old", "old", "Eski post", "filter", item.get("title"))
            continue
        item["text_hash"] = text_hash(item["text"])
        if item["text_hash"] in batch_hashes or await db.hash_is_known(item["text_hash"]):
            report.content_duplicates += 1
            await db.mark_seen(key[0], key[1], "duplicate", "duplicate", "Matni bir xil",
                               "filter", item.get("title"), item["text_hash"])
            continue
        batch_hashes.add(item["text_hash"])
        fresh.append(item)

    results = await asyncio.gather(*(classify(i["text"]) for i in fresh), return_exceptions=True)
    for item, res in zip(fresh, results):
        report.analysed += 1
        if isinstance(res, Exception):
            report.ai_errors += 1
            report.retry_later += 1
            report.errors.append("Tasniflashda kutilmagan xato: " + short_error(res))
            continue
        engine = res.get("engine")
        if engine == "ai":
            report.ai_ok += 1
        else:
            report.rules_used += 1
        if engine == "rules_fallback":
            report.ai_errors += 1
            err = res.get("ai_error") or "noma'lum"
            if err not in report.ai_error_samples:
                report.ai_error_samples.append(err)

        key = (item.get("source"), str(item.get("external_id")))
        if res.get("relevant") and res.get("category") == "programming_job":
            reason = res.get("reason", "")
            if engine == "rules_fallback":
                reason += " (AI ishlamadi, qoida filtri qo'llandi)"
            item.update(
                language=res.get("language"), category="programming_job",
                confidence=float(res.get("confidence", 0) or 0),
                match_score=int(res.get("match_score", 0) or 0), reason=reason,
                title=res.get("title") or item.get("title"),
            )
            job_id = await db.save_job(item)
            if not job_id:
                report.known_duplicates += 1
                continue
            report.accepted += 1
            if bot and notify:
                await _notify_job(bot, job_id, format_job_message(item, res.get("task_summary", "")), report)
        else:
            if engine == "rules_fallback":
                report.retry_later += 1  # AI tiklangach qayta tekshiriladi
                continue
            category = res.get("category", "uncertain")
            report.rejected += 1
            report.rejected_by_category[category] = report.rejected_by_category.get(category, 0) + 1
            if len(report.rejected_samples) < 8:
                report.rejected_samples.append({
                    "category": category, "reason": res.get("reason", ""),
                    "snippet": (item.get("title") or item["text"])[:80].replace("\n", " ")})
            await db.mark_seen(key[0], key[1], "rejected", category, res.get("reason", ""),
                               engine, item.get("title") or item["text"], item.get("text_hash"))
    return report


async def resend_pending(bot, report: ScanReport):
    """Oldin yuborilmay qolgan (notified=0) e'lonlarni qayta yuboradi."""
    for job in await db.unnotified_jobs():
        delivered, errors = await send_to_admins(bot, format_job_message(job))
        if delivered:
            await db.mark_notified(job["id"])
            report.resent_pending += 1
        else:
            report.notify_failed += 1
            for err in errors:
                if err not in report.notify_errors:
                    report.notify_errors.append(err)
            break  # yetkazib bo'lmayapti: har birini urinishning foydasi yo'q


async def run_scan(bot=None, notify=True) -> ScanReport:
    if runtime.scan_lock.locked():
        return ScanReport(skipped=True)
    async with runtime.scan_lock:
        started = time.monotonic()
        report = ScanReport(started_at=now_str())
        try:
            items = await collect_all(report)
            await process_items(items, bot, notify, report)
            if bot and notify:
                await resend_pending(bot, report)
            await db.prune_seen()
        except Exception as exc:
            log.exception("Skaner xatosi")
            report.errors.append("Skaner xatosi: " + short_error(exc))
        report.duration = time.monotonic() - started
        try:
            await db.set_json_setting("last_scan_report", report.to_dict())
        except Exception:
            log.exception("Hisobotni saqlab bo'lmadi")
        log.info(
            "Scan: o'qildi=%s takroriy=%s yangi=%s mos=%s rad=%s xato=%s (%.1fs)",
            report.read_total, report.known_duplicates, report.analysed, report.accepted,
            report.rejected, len(report.problem_lines()), report.duration)
        return report


async def scheduled_scan(bot):
    """Scheduler chaqiradi. Muammo bo'lsa admin'ga (takrorlanmasdan) ogohlantirish yuboradi."""
    try:
        report = await run_scan(bot, True)
    except Exception as exc:
        log.exception("Rejalashtirilgan scan qulab tushdi")
        if runtime.should_alert("scan-crash"):
            await send_to_admins(bot, f"⚠️ Skaner qulab tushdi: {short_error(exc)}")
        return
    if report.skipped or not report.has_problems:
        return
    problems = report.problem_lines()
    key = "scan:" + hashlib.sha1("|".join(problems).encode()).hexdigest()
    if runtime.should_alert(key):
        text = "⚠️ <b>Avtomatik tekshiruvda muammo</b>\n" + "\n".join(
            "• " + p for p in map(lambda x: x.replace("<", "‹").replace(">", "›"), problems[:6]))
        await send_to_admins(bot, text[:3900])
