import logging

import config
from app.collectors.base import CollectorResult, SourceReport
from app.db import list_sources
from app.services.telethon_manager import (
    TelegramUnavailable, config_problem, explain_error, manager,
)

log = logging.getLogger(__name__)


def build_link(value: str, message_id: int):
    if value.startswith("@"):
        return f"https://t.me/{value[1:]}/{message_id}"
    return None


async def collect_telegram_user() -> CollectorResult:
    result = CollectorResult(name="telegram")
    sources = [s for s in await list_sources() if s[1] == "telegram" and s[3]]
    if not sources:
        return result  # faol Telegram manba yo'q: xato emas
    problem = config_problem()
    if problem:
        result.error = problem
        return result
    try:
        await manager.ensure()
    except TelegramUnavailable as exc:
        result.error = str(exc)
        log.warning("Telegram collector ishlamadi: %s", exc)
        return result

    for sid, kind, value, enabled in sources:
        report = SourceReport(kind="telegram", value=value)
        try:
            _entity, messages = await manager.fetch_messages(value, config.MAX_MESSAGES_PER_SOURCE)
            for msg in messages:
                body = (getattr(msg, "message", None) or "").strip()
                if not body:
                    continue
                result.items.append({
                    "source": value,
                    "source_kind": "telegram",
                    "external_id": str(msg.id),
                    "title": body[:120].replace("\n", " "),
                    "text": body,
                    "url": build_link(value, msg.id),
                    "published_at": msg.date.isoformat() if msg.date else None,
                })
                report.fetched += 1
            if not messages:
                report.note = "Manbada xabar yo'q (xato emas)."
            elif report.fetched == 0:
                report.note = f"{len(messages)} ta xabar bor, lekin matnsiz (rasm/video)."
        except TelegramUnavailable as exc:
            report.ok, report.error = False, str(exc)
            result.error = str(exc)
            result.sources.append(report)
            break  # sessiya ishlamasa qolgan manbalarni urinib ko'rishning foydasi yo'q
        except Exception as exc:
            report.ok, report.error = False, explain_error(exc)
            log.warning("Telegram manba xatosi %s: %s", value, type(exc).__name__)
        result.sources.append(report)
    return result
