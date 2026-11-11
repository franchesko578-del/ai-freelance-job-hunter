from dataclasses import dataclass, field


@dataclass
class SourceReport:
    kind: str
    value: str
    ok: bool = True
    fetched: int = 0          # matni bor, olingan xabarlar
    error: str | None = None  # tushunarli sabab (maxfiy ma'lumotsiz)
    note: str | None = None


@dataclass
class CollectorResult:
    name: str
    items: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    error: str | None = None  # butun collector ishlamasa (masalan: Telegram sessiya)

    @property
    def failed_sources(self):
        return [s for s in self.sources if not s.ok]

    @property
    def fetched(self):
        return len(self.items)


def short_error(exc: Exception, limit: int = 200) -> str:
    text = str(exc).strip().replace("\n", " ")
    name = type(exc).__name__
    msg = f"{name}: {text}" if text else name
    return msg[:limit]
