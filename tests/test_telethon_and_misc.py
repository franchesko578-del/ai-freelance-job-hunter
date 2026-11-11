import logging
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

import config
import feedparser
from app import db
from app.collectors import telethon_collector as tc
from app.collectors import web as webmod
from app.collectors import rss as rssmod
from app.log import RedactingFormatter, redact
from app.services import telethon_manager as tm
from tests.helpers import DBTestCase


class AuthKeyDuplicatedError(Exception): ...
class UsernameNotOccupiedError(Exception): ...
class FloodWaitError(Exception):
    seconds = 42


class FakeClient:
    def __init__(self, authorized=True, messages=None, resolve_error=None):
        self.authorized, self.messages, self.resolve_error = authorized, messages or [], resolve_error
        self.connected = False
        self.dialogs_called = 0

    async def connect(self): self.connected = True
    async def disconnect(self): self.connected = False
    def is_connected(self): return self.connected
    async def is_user_authorized(self): return self.authorized
    async def get_me(self): return SimpleNamespace(id=7, first_name="Ali", last_name=None, username="ali")
    async def get_dialogs(self, limit=None): self.dialogs_called += 1
    async def get_input_entity(self, v): return SimpleNamespace(title="Kanal", id=v)

    async def get_entity(self, v):
        if self.resolve_error:
            raise self.resolve_error
        return SimpleNamespace(title="Freelancer UZ")

    async def iter_messages(self, entity, limit):
        for m in self.messages[:limit]:
            yield m


def msg(i, text):
    return SimpleNamespace(id=i, message=text, date=datetime(2026, 11, 11, tzinfo=timezone.utc))


def new_manager(client):
    m = tm.TelethonManager()
    m._make_client = lambda: client
    return m


class ExplainErrorTests(unittest.TestCase):
    def test_known_errors(self):
        self.assertIn("ikki joyda", tm.explain_error(AuthKeyDuplicatedError()))
        self.assertIn("username", tm.explain_error(UsernameNotOccupiedError()).lower())
        self.assertIn("42", tm.explain_error(FloodWaitError()))
        self.assertIn("timeout", tm.explain_error(TimeoutError()))
        self.assertIn("topilmadi", tm.explain_error(ValueError("Cannot find any entity corresponding to x")))


class ManagerTests(DBTestCase):
    def setUp(self):
        self.old = (config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH, config.TELETHON_SESSION_STRING)
        config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH, config.TELETHON_SESSION_STRING = "123", "hash12345678", "SESSIONSTRING"
        self.addCleanup(lambda: setattr(config, "TELEGRAM_API_ID", self.old[0]))
        self.addCleanup(lambda: setattr(config, "TELEGRAM_API_HASH", self.old[1]))
        self.addCleanup(lambda: setattr(config, "TELETHON_SESSION_STRING", self.old[2]))

    async def test_missing_api_credentials(self):
        config.TELEGRAM_API_ID = ""
        st = await tm.TelethonManager().status()
        self.assertFalse(st["configured"])
        self.assertIn("TELEGRAM_API_ID", st["error"])

    async def test_unauthorized_string_session_message(self):
        m = new_manager(FakeClient(authorized=False))
        st = await m.status()
        self.assertFalse(st["authorized"])
        self.assertIn("TELETHON_SESSION_STRING", st["error"])
        self.assertIn("StringSession", st["session_kind"])

    async def test_unauthorized_file_session_message(self):
        config.TELETHON_SESSION_STRING = ""
        st = await new_manager(FakeClient(authorized=False)).status()
        self.assertIn("Render", st["error"])

    async def test_status_ok_and_check_source(self):
        m = new_manager(FakeClient(messages=[msg(5, "salom")]))
        st = await m.status()
        self.assertTrue(st["authorized"] and st["connected"])
        self.assertEqual(st["account"]["username"], "ali")
        res = await m.check_source("@freelancer_Uzbek")
        self.assertTrue(res["ok"])
        self.assertEqual(res["messages"], 1)

    async def test_check_source_error_is_explained(self):
        m = new_manager(FakeClient(resolve_error=UsernameNotOccupiedError()))
        res = await m.check_source("@yoq_kanal")
        self.assertFalse(res["ok"])
        self.assertIn("username", res["error"].lower())

    async def test_numeric_id_loads_dialogs_once(self):
        c = FakeClient(messages=[msg(1, "x")])
        m = new_manager(c)
        await m.fetch_messages("-1001234567890", 5)
        await m.fetch_messages("-1001234567890", 5)
        self.assertEqual(c.dialogs_called, 1)


class CollectorTests(DBTestCase):
    def setUp(self):
        self.old = (config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)
        config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH = "123", "hash12345678"
        self.addCleanup(lambda: setattr(config, "TELEGRAM_API_ID", self.old[0]))
        self.addCleanup(lambda: setattr(config, "TELEGRAM_API_HASH", self.old[1]))

    def _use(self, client):
        p = mock.patch.object(tc, "manager", new_manager(client))
        p.start()
        self.addCleanup(p.stop)

    async def test_no_telegram_sources_is_not_error(self):
        r = await tc.collect_telegram_user()
        self.assertIsNone(r.error)
        self.assertEqual(r.sources, [])

    async def test_reads_text_messages_and_skips_media(self):
        await db.add_source("telegram", "@freelancer_Uzbek")
        self._use(FakeClient(messages=[msg(3, "Python dasturchi kerak"), msg(2, ""), msg(1, None)]))
        r = await tc.collect_telegram_user()
        self.assertIsNone(r.error)
        self.assertEqual(r.fetched, 1)
        self.assertEqual(r.items[0]["url"], "https://t.me/freelancer_Uzbek/3")
        self.assertEqual(r.sources[0].fetched, 1)

    async def test_empty_source_has_note_not_error(self):
        await db.add_source("telegram", "@freelancer_Uzbek")
        self._use(FakeClient(messages=[]))
        r = await tc.collect_telegram_user()
        self.assertTrue(r.sources[0].ok)
        self.assertIn("xato emas", r.sources[0].note)

    async def test_source_error_is_reported_per_source(self):
        await db.add_source("telegram", "@yoq_kanal")
        self._use(FakeClient(resolve_error=UsernameNotOccupiedError()))
        r = await tc.collect_telegram_user()
        self.assertFalse(r.sources[0].ok)
        self.assertIn("username", r.sources[0].error.lower())

    async def test_unauthorized_session_sets_collector_error(self):
        await db.add_source("telegram", "@freelancer_Uzbek")
        config.TELETHON_SESSION_STRING = "S"
        self.addCleanup(lambda: setattr(config, "TELETHON_SESSION_STRING", ""))
        self._use(FakeClient(authorized=False))
        r = await tc.collect_telegram_user()
        self.assertIn("TELETHON_SESSION_STRING", r.error)
        self.assertEqual(r.items, [])

    async def test_disabled_source_is_skipped(self):
        await db.add_source("telegram", "@freelancer_Uzbek")
        await db.toggle_source((await db.list_sources())[0][0])
        self._use(FakeClient(messages=[msg(1, "x")]))
        r = await tc.collect_telegram_user()
        self.assertEqual(r.sources, [])


class LogRedactionTests(unittest.TestCase):
    def test_secrets_are_redacted(self):
        text = redact("url=https://api.telegram.org/bot123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw/getMe "
                      "Authorization: Bearer sk-or-v1-abcdefghijklmnop key=AIzaSyABCDEF")
        self.assertNotIn("AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw", text)
        self.assertNotIn("sk-or-v1-abcdefghijklmnop", text)
        self.assertNotIn("AIzaSyABCDEF", text)

    def test_configured_secret_values_are_redacted(self):
        with mock.patch.object(config, "TELETHON_SESSION_STRING", "SUPERSECRETSESSIONVALUE"):
            self.assertNotIn("SUPERSECRETSESSIONVALUE", redact("x SUPERSECRETSESSIONVALUE y"))

    def test_conflict_hint(self):
        rec = logging.LogRecord("aiogram", logging.ERROR, "f", 1,
                                "Failed to fetch updates - TelegramConflictError: terminated by other getUpdates", (), None)
        self.assertIn("boshqa joyda", RedactingFormatter("%(message)s").format(rec))


class ParsingTests(unittest.TestCase):
    def test_web_parse(self):
        item = webmod.parse_page("<html><title>Jobs</title><script>x=1</script><body>Python dasturchi kerak</body></html>", "https://x/jobs")
        self.assertEqual(item["title"], "Jobs")
        self.assertNotIn("x=1", item["text"])
        self.assertIsNone(webmod.parse_page("<html><script>1</script></html>", "https://x"))

    @unittest.skipIf(getattr(feedparser, "IS_SHIM", False), "feedparser o'rnatilmagan: bu test faqat haqiqiy kutubxona bilan ishlaydi")
    def test_rss_parse(self):
        raw = ('<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
               '<item><title>Bot kerak</title><link>https://x/1</link><guid>g1</guid>'
               '<description>&lt;p&gt;Python &lt;b&gt;API&lt;/b&gt;&lt;/p&gt;</description></item></channel></rss>')
        items, warning = rssmod.parse_feed(raw, "https://x/feed")
        self.assertIsNone(warning)
        self.assertEqual(items[0]["external_id"], "g1")
        self.assertNotIn("<b>", items[0]["text"])


class ConfigTests(unittest.TestCase):
    def test_admin_ids_parse(self):
        self.assertEqual(config._parse_admin_ids("1, 2;x,3,,"), {1, 2, 3})


if __name__ == "__main__":
    unittest.main()
