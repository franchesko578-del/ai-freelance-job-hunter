from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from app.services.notify import esc

CATEGORY_UZ = {
    "resume": "rezyume/o'z xizmatini reklama",
    "course": "kurs/ta'lim",
    "non_programming": "dasturlashga aloqasiz",
    "uncertain": "noaniq",
}
COLLECTOR_TITLE = {"telegram": "📱 Telegram", "rss": "📰 RSS", "web": "🌐 Veb-saytlar"}


@dataclass
class ScanReport:
    started_at: str = ""
    duration: float = 0.0
    skipped: bool = False
    collectors: dict = field(default_factory=dict)
    read_total: int = 0
    known_duplicates: int = 0
    content_duplicates: int = 0
    too_old: int = 0
    analysed: int = 0
    accepted: int = 0
    rejected: int = 0
    rejected_by_category: dict = field(default_factory=dict)
    rejected_samples: list = field(default_factory=list)
    retry_later: int = 0
    ai_ok: int = 0
    ai_errors: int = 0
    ai_error_samples: list = field(default_factory=list)
    rules_used: int = 0
    notified: int = 0
    notify_failed: int = 0
    notify_errors: list = field(default_factory=list)
    resent_pending: int = 0
    errors: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known)

    @property
    def sources_total(self):
        return sum(c.get("sources_total", 0) for c in self.collectors.values())

    @property
    def has_problems(self):
        return bool(self.errors or self.ai_errors or self.notify_failed
                    or any(c.get("error") or c.get("source_errors") for c in self.collectors.values()))

    def problem_lines(self):
        lines = list(self.errors)
        for name, c in self.collectors.items():
            if c.get("error"):
                lines.append(f"{COLLECTOR_TITLE.get(name, name)}: {c['error']}")
            for se in c.get("source_errors", []):
                if se["error"] == c.get("error"):
                    continue
                lines.append(f"{COLLECTOR_TITLE.get(name, name)} · {se['value']}: {se['error']}")
        if self.ai_errors:
            sample = self.ai_error_samples[0] if self.ai_error_samples else "noma'lum"
            lines.append(f"AI xatosi ({self.ai_errors} ta post qoida filtri bilan tekshirildi): {sample}")
        for err in self.notify_errors[:3]:
            lines.append(f"Xabar yuborilmadi: {err}")
        return lines

    def format_html(self) -> str:
        if self.skipped:
            return "⏳ Tekshiruv allaqachon ketmoqda. Tugashini kuting."
        out = [f"📋 <b>Tekshiruv hisoboti</b> ({self.duration:.1f} s)", f"🕒 {esc(self.started_at)}", ""]
        out.append("<b>Manbalar</b>")
        no_sources = all(c.get("sources_total", 0) == 0 and not c.get("error")
                         for c in self.collectors.values())
        if not self.collectors or no_sources:
            out.append("• Faol manba yo'q. «➕ Manba qo'shish» orqali qo'shing.")
        for name, c in self.collectors.items():
            title = COLLECTOR_TITLE.get(name, name)
            if c.get("error") and c.get("sources_ok", 0) == 0:
                out.append(f"{title}: ❌ ishlamadi")
                continue
            if c.get("sources_total", 0) == 0:
                continue
            out.append(
                f"{title}: manba {c['sources_total']} (✅{c['sources_ok']} ❌{c['sources_failed']}), "
                f"o'qilgan xabar: {c['fetched']}"
            )
            for note in c.get("source_notes", [])[:3]:
                out.append(f"   ℹ️ {esc(note['value'])}: {esc(note['note'])}")
        out += ["", "<b>Tahlil</b>", f"• Jami o'qildi: {self.read_total}",
                f"• Takroriy (oldin ko'rilgan): {self.known_duplicates}"]
        if self.content_duplicates:
            out.append(f"• Matni bir xil (boshqa manbada bor): {self.content_duplicates}")
        if self.too_old:
            out.append(f"• Eski postlar (o'tkazib yuborildi): {self.too_old}")
        out.append(f"• Yangi tahlil qilindi: {self.analysed}")
        out.append(f"• ✅ Mos buyurtma: {self.accepted} (yuborildi: {self.notified})")
        if self.resent_pending:
            out.append(f"• Oldin yuborilmagan, endi yuborildi: {self.resent_pending}")
        cat = ", ".join(f"{CATEGORY_UZ.get(k, k)} {v}" for k, v in
                        sorted(self.rejected_by_category.items(), key=lambda kv: -kv[1]))
        out.append(f"• 🚫 Rad etildi: {self.rejected}" + (f" ({esc(cat)})" if cat else ""))
        if self.retry_later:
            out.append(f"• ⏳ AI ishlamagani uchun keyingi safarga qoldi: {self.retry_later}")
        out.append(f"• AI so'rovlari: {self.ai_ok} muvaffaqiyatli, {self.ai_errors} xato; "
                   f"qoida filtri: {self.rules_used}")
        if self.rejected_samples:
            out += ["", "<b>Rad etilganlardan namunalar</b>"]
            for s in self.rejected_samples[:5]:
                out.append(f"• {esc(CATEGORY_UZ.get(s['category'], s['category']))}: "
                           f"«{esc(s['snippet'][:60])}» — {esc(s['reason'][:100])}")
        problems = self.problem_lines()
        out.append("")
        if problems:
            out.append("<b>⚠️ Muammolar</b>")
            out += [f"• {esc(p)}" for p in problems[:8]]
        else:
            out.append("✅ Xatolar yo'q.")
            if self.read_total == 0:
                out.append("ℹ️ Manbalardan yangi xabar kelmadi (bu xato emas).")
            elif self.accepted == 0:
                out.append("ℹ️ Xabarlar o'qildi, lekin mos buyurtma topilmadi (bu xato emas).")
        text = "\n".join(out)
        return text[:3900]


def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
