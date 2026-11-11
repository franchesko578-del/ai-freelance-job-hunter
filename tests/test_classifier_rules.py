import unittest

from tests import helpers  # noqa: F401
from app.services.classifier import rule_classify


def verdict(text):
    r = rule_classify(text)
    return r["relevant"], r["category"]


class RuleClassifierTests(unittest.TestCase):
    def test_uzbek_job(self):
        self.assertEqual(verdict("Telegram bot yozadigan dasturchi kerak. Budjet kelishiladi"),
                         (True, "programming_job"))
        self.assertEqual(verdict("Sayt yasab beradigan python dasturchi kerak"), (True, "programming_job"))

    def test_russian_job(self):
        self.assertEqual(verdict("Нужен разработчик для создания Telegram бота на Python"),
                         (True, "programming_job"))
        self.assertEqual(verdict("Требуется программист, сделать парсер сайта"), (True, "programming_job"))

    def test_english_job(self):
        self.assertEqual(verdict("Looking for a Python developer to build a REST API"),
                         (True, "programming_job"))

    def test_rabota_is_not_bot(self):
        # Eski kodda "бот" so'zi "работа" ichidan topilar edi
        self.assertFalse(verdict("Нужна работа курьером, оплата почасовая")[0])
        self.assertEqual(verdict("Требуется менеджер, хорошая работа")[1], "non_programming")

    def test_ios_inside_word(self):
        self.assertEqual(verdict("Curious about stations, we need a cook")[1], "non_programming")

    def test_resume_and_self_ad(self):
        self.assertEqual(verdict("Men dasturchiman, python bo'yicha ish izlayapman"), (False, "resume"))
        self.assertEqual(verdict("Ищу работу: python разработчик, портфолио в личке"), (False, "resume"))
        self.assertEqual(verdict("Saytlar yasab beraman, python django"), (False, "resume"))
        self.assertEqual(verdict("I am a developer, available for hire. Python, React"), (False, "resume"))

    def test_course(self):
        self.assertEqual(verdict("Python dasturlash kursiga yoziling! Yangi guruh"), (False, "course"))
        self.assertEqual(verdict("Курс программирования на Python, обучение с нуля"), (False, "course"))

    def test_uncertain_and_unrelated(self):
        self.assertEqual(verdict("Python haqida qiziqarli fakt")[1], "uncertain")
        self.assertEqual(verdict("Bugun ob-havo yaxshi")[1], "non_programming")

    def test_apostrophe_variants(self):
        self.assertEqual(verdict("Sun’iy intellekt bo‘yicha loyiha uchun dasturchi kerak"),
                         (True, "programming_job"))


if __name__ == "__main__":
    unittest.main()
