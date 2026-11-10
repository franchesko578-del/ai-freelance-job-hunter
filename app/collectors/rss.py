import aiohttp
import feedparser
from app.db import list_sources

async def collect_rss():
    results = []
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent":"AIJobHunter/1.0"}) as session:
        for sid, kind, value, enabled in await list_sources():
            if not enabled or kind != "rss":
                continue
            try:
                async with session.get(value) as resp:
                    if resp.status != 200:
                        continue
                    raw = await resp.text()
                feed = feedparser.parse(raw)
                for entry in feed.entries[:100]:
                    title = getattr(entry, "title", "")
                    summary = getattr(entry, "summary", "")
                    body = (title + "\n" + summary).strip()
                    if body:
                        results.append({"source":value,"source_kind":"rss","external_id":getattr(entry,"id",getattr(entry,"link",body[:100])),"title":title,"text":body,"url":getattr(entry,"link",None),"published_at":getattr(entry,"published",None)})
            except Exception:
                continue
    return results
