import json
import unittest
from unittest import mock

import config
from tests.helpers import DBTestCase
from app.services import classifier
from app.services.classifier import AIError, extract_json, normalize_result

GOOD = {"relevant": True, "category": "programming_job", "confidence": 0.9, "match_score": 80,
        "title": "Bot kerak", "language": "uz", "reason": "Mos", "task_summary": "Bot yozish"}


def gemini_ok(payload):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}


class AITests(DBTestCase):
    def setUp(self):
        self.old = (config.AI_PROVIDER, config.AI_API_KEY, config.ENCRYPTION_KEY)
        config.AI_PROVIDER, config.AI_API_KEY, config.ENCRYPTION_KEY = "gemini", "SECRETKEY1234567890", ""

    def tearDown(self):
        config.AI_PROVIDER, config.AI_API_KEY, config.ENCRYPTION_KEY = self.old

    async def _classify(self, responses):
        seq = iter(responses)

        async def fake_request(session, provider, key, prompt):
            return next(seq)

        class FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

        with mock.patch.object(classifier, "_request", fake_request), \
             mock.patch.object(classifier.aiohttp, "ClientSession", lambda **kw: FakeSession(), create=True), \
             mock.patch.object(classifier.asyncio, "sleep", mock.AsyncMock()):
            return await classifier.classify("Python dasturchi kerak")

    async def test_success(self):
        r = await self._classify([(200, gemini_ok(GOOD), None)])
        self.assertEqual(r["engine"], "ai")
        self.assertTrue(r["relevant"])
        self.assertIsNone(r["ai_error"])

    async def test_401_falls_back_and_hides_key(self):
        err = {"error": {"message": "API key SECRETKEY1234567890 invalid"}}
        r = await self._classify([(401, err, None)])
        self.assertEqual(r["engine"], "rules_fallback")
        self.assertIn("HTTP 401", r["ai_error"])
        self.assertNotIn("SECRETKEY1234567890", r["ai_error"])

    async def test_429_retries_then_succeeds(self):
        r = await self._classify([(429, {}, "1"), (200, gemini_ok(GOOD), None)])
        self.assertEqual(r["engine"], "ai")

    async def test_bad_json_and_block_reason(self):
        bad = {"candidates": [{"content": {"parts": [{"text": "bu JSON emas"}]}}]}
        r = await self._classify([(200, bad, None)])
        self.assertEqual(r["engine"], "rules_fallback")
        self.assertIn("JSON", r["ai_error"])
        blocked = {"promptFeedback": {"blockReason": "SAFETY"}}
        r = await self._classify([(200, blocked, None)])
        self.assertIn("SAFETY", r["ai_error"])

    async def test_circuit_breaker(self):
        for _ in range(classifier.AIHealth.FAIL_LIMIT):
            await self._classify([(500, {}, None)] * 3)
        self.assertTrue(classifier.health.paused())
        r = await classifier.classify("Python dasturchi kerak")
        self.assertEqual(r["engine"], "rules_fallback")
        self.assertIn("vaqtincha", r["ai_error"])

    async def test_provider_none_uses_rules(self):
        config.AI_PROVIDER = "none"
        r = await classifier.classify("Python dasturchi kerak")
        self.assertEqual(r["engine"], "rules")


class NormalizeTests(unittest.TestCase):
    def test_extract_json_with_fences(self):
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        with self.assertRaises(AIError):
            extract_json("hech narsa")

    def test_normalize_result_validation(self):
        r = normalize_result({"relevant": "true", "category": "programming_job", "confidence": "0.9",
                              "match_score": 500})
        self.assertTrue(r["relevant"])
        self.assertEqual(r["match_score"], 100)
        r = normalize_result({"relevant": True, "category": "resume"})
        self.assertFalse(r["relevant"])
        r = normalize_result({"relevant": True, "category": "programming_job", "confidence": 0.2})
        self.assertFalse(r["relevant"])
        self.assertEqual(r["category"], "uncertain")
        r = normalize_result({"category": "nonsense"})
        self.assertEqual(r["category"], "uncertain")


if __name__ == "__main__":
    unittest.main()
