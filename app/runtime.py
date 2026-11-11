"""Jarayon bo'yicha umumiy holat: scheduler, scan lock, ogohlantirish throttling."""
import asyncio
import time

scheduler = None
scan_lock = asyncio.Lock()
_alert_sent: dict[str, float] = {}


def reschedule(minutes: int) -> bool:
    if scheduler is None:
        return False
    scheduler.reschedule_job("scan", trigger="interval", minutes=minutes)
    return True


def should_alert(key: str, cooldown_seconds: int = 6 * 3600) -> bool:
    now = time.monotonic()
    last = _alert_sent.get(key)
    if last is not None and now - last < cooldown_seconds:
        return False
    _alert_sent[key] = now
    return True
