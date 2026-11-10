import aiohttp
import hashlib
from bs4 import BeautifulSoup
from app.db import list_sources

async def collect_web():
    results = []
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"User-Agent":"Mozilla/5.0 (compatible; AIJobHunter/1.0)"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for sid, kind, value, enabled in await list_sources():
            if not enabled or kind != "website":
                continue
            try:
                async with session.get(value, allow_redirects=True) as resp:
                    if resp.status != 200 or "text/html" not in resp.headers.get("Content-Type",""):
                        continue
                    html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script","style","noscript"]):
                    tag.decompose()
                title = soup.title.get_text(" ",strip=True) if soup.title else value
                body = soup.get_text(" ",strip=True)[:7000]
                if body:
                    results.append({"source":value,"source_kind":"website","external_id":value+":"+hashlib.sha256(body[:500].encode("utf-8")).hexdigest(),"title":title,"text":body,"url":value})
            except Exception:
                continue
    return results
