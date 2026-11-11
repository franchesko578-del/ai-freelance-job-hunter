import logging

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from app.collectors.base import CollectorResult, SourceReport, short_error
from app.db import list_sources

log = logging.getLogger(__name__)


def clean_html(text: str) -> str:
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)


def parse_feed(raw: str, source_value: str):
    """Matndan e'lonlar ro'yxati va ogohlantirish (bo'lsa) qaytaradi."""
    feed = feedparser.parse(raw)
    items = []
    for entry in feed.entries[:100]:
        title = clean_html(getattr(entry, "title", ""))
        summary = clean_html(getattr(entry, "summary", ""))
        body = (title + "\n" + summary).strip()
        if not body:
            continue
        link = getattr(entry, "link", None)
        ext_id = getattr(entry, "id", None) or link or body[:100]
        items.append({
            "source": source_value, "source_kind": "rss", "external_id": str(ext_id),
            "title": title, "text": body, "url": link,
            "published_at": getattr(entry, "published", None),
        })
    warning = None
    if not feed.entries and getattr(feed, "bozo", False):
        warning = "RSS formati o'qilmadi: " + short_error(getattr(feed, "bozo_exception", Exception("noma'lum")))
    return items, warning


async def collect_rss() -> CollectorResult:
    result = CollectorResult(name="rss")
    sources = [s for s in await list_sources() if s[1] == "rss" and s[3]]
    if not sources:
        return result
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "AIJobHunter/1.0"}) as session:
        for sid, kind, value, enabled in sources:
            report = SourceReport(kind="rss", value=value)
            try:
                async with session.get(value) as resp:
                    if resp.status != 200:
                        report.ok, report.error = False, f"HTTP {resp.status}"
                        result.sources.append(report)
                        continue
                    raw = await resp.text()
                items, warning = parse_feed(raw, value)
                if warning:
                    report.ok, report.error = False, warning
                else:
                    result.items.extend(items)
                    report.fetched = len(items)
                    if not items:
                        report.note = "Lenta bo'sh (xato emas)."
            except Exception as exc:
                report.ok, report.error = False, short_error(exc)
                log.warning("RSS xatosi %s: %s", value, type(exc).__name__)
            result.sources.append(report)
    return result
