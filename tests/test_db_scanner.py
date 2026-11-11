import unittest
from unittest import mock

import config
from app import db, runtime
from app.collectors.base import CollectorResult, SourceReport
from app.services import scanner
from app.services.classifier import rule_classify
from app.services.scanner import process_items, resend_pending, run_scan
from app.services.report import ScanReport
from app.services.sources import parse_source_input
from tests.helpers import DBTestCase, FakeBot
from datetime import datetime, timedelta, timezone


def item(ext, text, source="@chan", published=None):
    return {"source": source, "source_kind": "telegram", "external_id": str(ext),
            "title": text[:50], "text": text, "url": f"https://t.me/chan/{ext}",
            "published_at": published}


async def rules_classify(text):
    r = rule_classify(text)
    r.update(engine="rules", ai_error=None)
    return r


class SourcesDBTests(DBTestCase):
    async def test_add_duplicate_toggle_delete(self):
        self.assertTrue(await db.add_source("telegram", "@freelancer_Uzbek"))
        self.assertFalse(await db.add_source("telegram", "@freelancer_Uzbek"))
        rows = await db.list_sources()
        self.assertEqual(len(rows), 1)
        sid = rows[0][0]
        await db.toggle_source(sid)
        self.assertEqual((await db.get_source(sid))[3], 0)
        await db.toggle_source(sid)
        self.assertEqual((await db.get_source(sid))[3], 1)
        self.assertTrue(await db.delete_source(sid))
        self.assertFalse(await db.delete_source(sid))
        self.assertEqual(await db.list_sources(), [])

    async def test_job_unique_constraint(self):
        base = {"source": "s", "external_id": "1", "text": "x"}
        self.assertIsNotNone(await db.save_job(dict(base)))
        self.assertIsNone(await db.save_job(dict(base)))

    async def test_settings_and_interval(self):
        self.assertEqual(await db.get_scan_interval(), config.SCAN_INTERVAL_MINUTES)
        await db.set_setting("scan_interval", "30")
        self.assertEqual(await db.get_scan_interval(), 30)
        await db.set_setting("scan_interval", "abc")
        self.assertEqual(await db.get_scan_interval(), config.SCAN_INTERVAL_MINUTES)


class ProcessItemsTests(DBTestCase):
    def setUp(self):
        p = mock.patch.object(scanner, "classify", rules_classify)
        p.start()
        self.addCleanup(p.stop)

    async def test_accept_reject_duplicates_and_stats(self):
        bot = FakeBot()
        items = [
            item(1, "Python dasturchi kerak, Telegram bot yozish"),
            item(2, "Men dasturchiman, python bo'yicha ish izlayapman"),
            item(3, "Python kursiga yoziling"),
            item(4, "Bugun ob-havo yaxshi"),
        ]
        rep = await process_items([dict(i) for i in items], bot, True, ScanReport())
        self.assertEqual((rep.analysed, rep.accepted, rep.rejected, rep.notified), (4, 1, 3, 1))
        self.assertEqual(rep.rejected_by_category, {"resume": 1, "course": 1, "non_programming": 1})
        self.assertTrue(all(s["reason"] for s in rep.rejected_samples))
        self.assertEqual(len(bot.sent), 2)  # 2 admin x 1 e'lon

        # Ikkinchi marta: hammasi takroriy, qayta tasniflanmaydi, qayta yuborilmaydi
        rep2 = await process_items([dict(i) for i in items], bot, True, ScanReport())
        self.assertEqual((rep2.known_duplicates, rep2.analysed, rep2.notified), (4, 0, 0))
        self.assertEqual(len(bot.sent), 2)
        rows = await db.recent_rejected(10)
        self.assertEqual(len(rows), 3)

    async def test_same_text_in_other_source_is_duplicate(self):
        bot = FakeBot()
        text = "Python dasturchi kerak, API yozish"
        await process_items([item(1, text, "@a")], bot, True, ScanReport())
        rep = await process_items([item(9, text, "@b")], bot, True, ScanReport())
        self.assertEqual((rep.content_duplicates, rep.accepted), (1, 0))

    async def test_old_posts_skipped(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=200)).isoformat()
        rep = await process_items([item(1, "Python dasturchi kerak", published=old)], FakeBot(), True, ScanReport())
        self.assertEqual((rep.too_old, rep.analysed), (1, 0))

    async def test_notification_failure_is_not_marked_sent_and_is_retried(self):
        failing = FakeBot(fail=True)
        rep = await process_items([item(1, "Python dasturchi kerak")], failing, True, ScanReport())
        self.assertEqual((rep.accepted, rep.notified, rep.notify_failed), (1, 0, 1))
        self.assertTrue(rep.notify_errors)
        self.assertEqual(len(await db.unnotified_jobs()), 1)
        ok = FakeBot()
        rep2 = ScanReport()
        await resend_pending(ok, rep2)
        self.assertEqual(rep2.resent_pending, 1)
        self.assertEqual(await db.unnotified_jobs(), [])

    async def test_html_in_title_is_escaped(self):
        bot = FakeBot()
        await process_items([item(1, "Python dasturchi kerak <script> & <b>")], bot, True, ScanReport())
        text = bot.sent[0][1]
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("\\n", text)  # eski botapi xatosi: literal \n

    async def test_ai_failure_rejection_is_retried_later(self):
        async def failing(text):
            r = rule_classify("Bugun ob-havo")
            r.update(engine="rules_fallback", ai_error="HTTP 401")
            return r
        with mock.patch.object(scanner, "classify", failing):
            rep = await process_items([item(1, "Biror post")], FakeBot(), True, ScanReport())
        self.assertEqual((rep.retry_later, rep.rejected, rep.ai_errors), (1, 0, 1))
        self.assertEqual(await db.recent_rejected(), [])  # seen'ga yozilmadi: keyin qayta ko'riladi
        self.assertIn("HTTP 401", rep.ai_error_samples)


class RunScanTests(DBTestCase):
    def setUp(self):
        p = mock.patch.object(scanner, "classify", rules_classify)
        p.start()
        self.addCleanup(p.stop)

    def _patch_collectors(self, telegram, rss=None, web=None):
        async def t(): return telegram
        async def r(): return rss or CollectorResult("rss")
        async def w(): return web or CollectorResult("web")
        return mock.patch.object(scanner, "COLLECTORS", (("telegram", t), ("rss", r), ("web", w)))

    async def test_collector_error_is_visible_not_hidden(self):
        tg = CollectorResult("telegram", error="TELETHON_SESSION_STRING yaroqsiz")
        with self._patch_collectors(tg):
            rep = await run_scan(FakeBot(), True)
        self.assertTrue(rep.has_problems)
        text = rep.format_html()
        self.assertIn("ishlamadi", text)
        self.assertIn("TELETHON_SESSION_STRING yaroqsiz", text)
        self.assertNotIn("Xatolar yo'q", text)

    async def test_no_messages_is_not_an_error(self):
        tg = CollectorResult("telegram", sources=[SourceReport("telegram", "@x", note="Manbada xabar yo'q (xato emas).")])
        with self._patch_collectors(tg):
            rep = await run_scan(FakeBot(), True)
        self.assertFalse(rep.has_problems)
        self.assertIn("xato emas", rep.format_html())

    async def test_per_collector_counts_and_source_error(self):
        tg = CollectorResult("telegram", items=[item(1, "Python dasturchi kerak")],
                             sources=[SourceReport("telegram", "@ok", fetched=1),
                                      SourceReport("telegram", "@bad", ok=False, error="Kanal yopiq")])
        rss = CollectorResult("rss", sources=[SourceReport("rss", "https://x/feed", ok=False, error="HTTP 404")])
        with self._patch_collectors(tg, rss):
            rep = await run_scan(FakeBot(), True)
        self.assertEqual(rep.collectors["telegram"]["sources_failed"], 1)
        self.assertEqual(rep.collectors["telegram"]["fetched"], 1)
        self.assertEqual(rep.collectors["rss"]["source_errors"][0]["error"], "HTTP 404")
        self.assertEqual(rep.accepted, 1)
        saved = await db.get_json_setting("last_scan_report")
        self.assertEqual(ScanReport.from_dict(saved).accepted, 1)

    async def test_collector_crash_is_reported(self):
        async def boom(): raise RuntimeError("kutilmagan")
        async def ok(): return CollectorResult("x")
        with mock.patch.object(scanner, "COLLECTORS", (("telegram", boom), ("rss", ok))):
            rep = await run_scan(FakeBot(), True)
        self.assertIn("kutilmagan", rep.collectors["telegram"]["error"])

    async def test_scan_lock_prevents_overlap(self):
        async with runtime.scan_lock:
            rep = await run_scan(FakeBot(), True)
        self.assertTrue(rep.skipped)

    async def test_scheduled_scan_alert_is_throttled(self):
        tg = CollectorResult("telegram", error="Session yaroqsiz")
        bot = FakeBot()
        with self._patch_collectors(tg):
            await scanner.scheduled_scan(bot)
            await scanner.scheduled_scan(bot)
        self.assertEqual(len(bot.sent), 2)  # 2 admin, faqat bir marta ogohlantirish


class SourceParsingTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_source_input("telegram @freelancer_Uzbek")[0], ("telegram", "@freelancer_Uzbek"))
        self.assertEqual(parse_source_input("telegram https://t.me/freelancer_Uzbek")[0], ("telegram", "@freelancer_Uzbek"))
        self.assertEqual(parse_source_input("telegram freelancer_Uzbek")[0], ("telegram", "@freelancer_Uzbek"))
        self.assertEqual(parse_source_input("telegram -1001234567890")[0], ("telegram", "-1001234567890"))
        self.assertEqual(parse_source_input("rss https://x.com/feed")[0], ("rss", "https://x.com/feed"))
        self.assertEqual(parse_source_input("web https://x.com/jobs")[0], ("website", "https://x.com/jobs"))
        for bad in ("telegram", "rss http://x.com", "ftp x", "telegram t.me/+abcdef", "telegram @ab"):
            self.assertIsNone(parse_source_input(bad)[0], bad)


if __name__ == "__main__":
    unittest.main()
