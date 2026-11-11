import os
import tempfile
import unittest

import config
from app import db, runtime
from app.services import classifier


class DBTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.mkdtemp()
        config.DATABASE_PATH = os.path.join(self._tmp, "test.db")
        config.MAX_AGE_HOURS = 72
        runtime._alert_sent.clear()
        classifier.health.reset()
        classifier.health.last_error = None
        await db.init_db()


class FakeBot:
    def __init__(self, fail=False, fail_text_with_html=False):
        self.sent = []
        self.fail = fail

    async def send_message(self, chat_id, text, **kw):
        if self.fail:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        self.sent.append((chat_id, text, kw))
