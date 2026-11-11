import hashlib
import logging

import aiohttp
from bs4 import BeautifulSoup

from app.collectors.base import CollectorResult, SourceReport, short_error
from app.db import list_sources

log = logging.getLogger(__name__)


def parse_page(html: str, source_value: str):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else source_value
    body = soup.get_text(" ", strip=True)[:7000]
    if not body:
        return None
    digest = hashlib.sha256(body[:500].encode("utf-8")).hexdigest()
    return {
        "source": source_value, "source_kind": "website",
        "external_id": source_value + ":" + digest,
        "title": title, "text": body, "url": source_value,
    }


async def collect_web() -> CollectorResult:
    result = CollectorResult(name="web")
    sources = [s for s in await list_sources() if s[1] == "website" and s[3]]
    if not sources:
        return result
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AIJobHunter/1.0)"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for sid, kind, value, enabled in sources:
            report = SourceReport(kind="website", value=value)
            try:
                async with session.get(value, allow_redirects=True) as resp:
                    ctype = resp.headers.get("Content-Type", "")
                    if resp.status != 200:
                        report.ok, report.error = False, f"HTTP {resp.status}"
                    elif "text/html" not in ctype:
                        report.ok, report.error = False, f"HTML emas (Content-Type: {ctype or 'yo‘q'})"
                    else:
                        html = await resp.text()
                        item = parse_page(html, value)
                        if item:
                            result.items.append(item)
                            report.fetched = 1
                        else:
                            report.note = "Sahifada matn topilmadi."
            except Exception as exc:
                report.ok, report.error = False, short_error(exc)
                log.warning("Web xatosi %s: %s", value, type(exc).__name__)
            result.sources.append(report)
    return result
