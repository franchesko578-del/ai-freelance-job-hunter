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


class SellerAdTests(unittest.TestCase):
    def test_seller_ads_are_rejected(self):
        ads = [
            "Telegram bot yasay olaman, narxlar kelishiladi",
            "Men bot qila olaman, buyurtma bering",
            "Saytlar yasayman, python django, aloqaga chiqing",
            "Sizga Telegram bot kerakmi? Tez va sifatli qilib beraman",
            "Sizga sayt kerak bo'lsa murojaat qiling, dasturchi xizmati",
            "Делаю телеграм ботов на python, пишите в лс",
            "Могу сделать сайт под ключ, услуги разработчика",
            "Вам нужен бот? Разрабатываем боты и сайты",
            "I can build Telegram bots in Python, contact me",
            "We make websites and apps, my services: React, API",
        ]
        for text in ads:
            self.assertFalse(rule_classify(text)["relevant"], text)

    def test_real_jobs_still_accepted(self):
        jobs = [
            "Telegram bot yozadigan dasturchi kerak, to'lov kelishiladi",
            "Python backend dasturchi izlayapmiz, oylik 800$",
            "Нужен разработчик для Telegram бота, бюджет 300$",
            "Требуется программист на PHP для доработки сайта",
            "Looking for a React developer to build a web app",
            "Sayt yasab beradigan dasturchi kerak",
        ]
        for text in jobs:
            self.assertTrue(rule_classify(text)["relevant"], text)
