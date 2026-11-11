import os
import sys
import tempfile
import types

# Test muhiti: haqiqiy sirlar kerak emas.
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKENTESTTOKENTESTTOKENTESTTOKEN")
os.environ.setdefault("ADMIN_IDS", "111,222")
os.environ.setdefault("AI_PROVIDER", "none")
os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))


def _install_shims():
    """Kutubxonalar o'rnatilmagan muhitda (masalan sandbox) faqat testlar uchun yengil o'rinbosarlar."""
    try:
        import aiosqlite  # noqa: F401
    except ImportError:
        import sqlite3

        mod = types.ModuleType("aiosqlite")
        mod.IntegrityError = sqlite3.IntegrityError
        mod.Row = sqlite3.Row

        class _Cursor:
            def __init__(self, cur):
                self._c = cur
                self.rowcount = cur.rowcount
                self.lastrowid = cur.lastrowid

            async def fetchone(self):
                return self._c.fetchone()

            async def fetchall(self):
                return self._c.fetchall()

        class _Conn:
            def __init__(self, path, timeout=5):
                self._conn = sqlite3.connect(path, timeout=timeout)
                self.row_factory = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                self._conn.close()

            async def execute(self, sql, params=()):
                self._conn.row_factory = self.row_factory
                return _Cursor(self._conn.execute(sql, params))

            async def executescript(self, sql):
                self._conn.executescript(sql)

            async def commit(self):
                self._conn.commit()

        mod.connect = lambda path, timeout=5: _Conn(path, timeout)
        sys.modules["aiosqlite"] = mod

    try:
        import aiohttp  # noqa: F401
    except ImportError:
        mod = types.ModuleType("aiohttp")
        mod.ClientTimeout = lambda total=None: None
        mod.ClientSession = object
        sys.modules["aiohttp"] = mod

    try:
        import feedparser  # noqa: F401
    except ImportError:
        mod = types.ModuleType("feedparser")
        mod.IS_SHIM = True

        def _parse(raw):
            raise NotImplementedError("feedparser o'rnatilmagan (shim)")

        mod.parse = _parse
        sys.modules["feedparser"] = mod


_install_shims()
