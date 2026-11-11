import re

TG_USERNAME = r"[A-Za-z][A-Za-z0-9_]{3,31}"


def parse_source_input(text: str):
    """('telegram', '@kanal') | ('rss', url) | ('website', url) yoki (None, xato_matni)."""
    parts = (text or "").strip().split(maxsplit=1)
    if len(parts) != 2:
        return None, "Format noto‘g‘ri. Masalan: <code>telegram @kanal</code>"
    kind, value = parts[0].lower(), parts[1].strip()
    if kind in ("web", "sayt"):
        kind = "website"
    if kind not in {"telegram", "rss", "website"}:
        return None, "Tur noto‘g‘ri. Faqat: telegram, rss yoki website."
    if kind == "telegram":
        m = re.match(rf"^(?:https?://)?(?:t\.me|telegram\.me)/({TG_USERNAME})/?$", value)
        if m:
            value = "@" + m.group(1)
        elif re.fullmatch(TG_USERNAME, value):
            value = "@" + value
        if not (re.fullmatch("@" + TG_USERNAME, value) or re.fullmatch(r"-100\d{5,}", value)):
            return None, ("Telegram manba <code>@username</code>, <code>https://t.me/username</code> "
                          "yoki <code>-100...</code> ID ko‘rinishida bo‘lsin. "
                          "Yopiq taklif havolalari (t.me/+...) qo‘llab-quvvatlanmaydi.")
    elif not value.startswith("https://"):
        return None, "Faqat https:// manzil qabul qilinadi."
    return (kind, value), None
