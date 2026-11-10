import json
import re
import aiohttp
from config import AI_PROVIDER, AI_API_KEY, AI_MODEL, ENCRYPTION_KEY
from app.db import get_profile, load_encrypted_api_key

PROGRAMMING_TERMS = [
    "python","javascript","typescript","java","php","laravel","django","flask","fastapi",
    "aiogram","telegram bot","telegram mini app","mini app","бот","программист","разработчик",
    "программирован","код yoz","dasturchi","dasturlash","веб-сайт","website","web app",
    "mobile app","android","ios","react","vue","node.js","api integration","api integrats",
    "database","postgresql","mysql","sql","backend","frontend","full stack","automation",
    "автоматизац","искусственный интеллект","artificial intelligence","sun'iy intellekt",
    "нейросет","bug fixing","debugging","software development","приложение","код"
]
RESUME_TERMS = ["ish joyi kerak","ish qidir","работу ищу","ищу работу","резюме","rezyume","ищу заказы как разработчик"]
COURSE_TERMS = ["dasturlash kursi","kursga yozil","курс программирования","обучение программированию"]
HIRING_TERMS = ["kerak","нужен","нужна","требуется","ищем","заказ","buyurtma","создать","разработать","сделать","build","develop","looking for","need a","vacancy","вакансия","ishchi kerak"]

def rule_classify(text):
    low = text.lower()
    hits = [x for x in PROGRAMMING_TERMS if x in low]
    if not hits:
        return {"relevant": False, "category": "non_programming", "confidence": .95, "match_score": 0, "reason": "Dasturlash vazifasi topilmadi."}
    if any(x in low for x in RESUME_TERMS):
        return {"relevant": False, "category": "resume", "confidence": .96, "match_score": 0, "reason": "Bu ish qidirayotgan mutaxassis rezyumesi."}
    if any(x in low for x in COURSE_TERMS):
        return {"relevant": False, "category": "course", "confidence": .95, "match_score": 0, "reason": "Bu ta'lim/kurs e'loni."}
    if any(x in low for x in HIRING_TERMS):
        return {"relevant": True, "category": "programming_job", "confidence": .80, "match_score": 60, "reason": "Dasturlash bo'yicha ish yoki buyurtma aniqlandi."}
    return {"relevant": False, "category": "uncertain", "confidence": .50, "match_score": 0, "reason": "Buyurtma ekanligi aniq emas."}

async def classify(text):
    key = AI_API_KEY
    if not key and ENCRYPTION_KEY:
        try:
            from cryptography.fernet import Fernet
            key = await load_encrypted_api_key(Fernet(ENCRYPTION_KEY.encode()))
        except Exception:
            key = None
    if not key or AI_PROVIDER == "none":
        return rule_classify(text)
    profile = await get_profile()
    prompt = (
        "You classify job posts for a freelance software developer. Analyze the original language. "
        "Return only JSON keys relevant(boolean), category(programming_job|resume|non_programming|course|uncertain), "
        "confidence(0..1), match_score(0..100), title, language, reason (short Uzbek), task_summary (short Uzbek). "
        "Only relevant=true if a client/employer requests software development or code work. "
        "Exclude resumes/self-advertisements, job seekers, courses and unrelated work. "
        "Missing budget/deadline or DM/negotiable wording must NOT disqualify a real programming job. "
        "Include all languages/stacks, AI, bots, websites, apps, APIs, automation, debugging and databases. "
        "Ambiguous posts must be irrelevant and category uncertain. Developer skills: " + profile +
        "\nPOST:\n" + text[:6500]
    )
    try:
        timeout = aiohttp.ClientTimeout(total=35)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if AI_PROVIDER == "gemini":
                model = AI_MODEL or "gemini-2.0-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                payload = {"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.1}}
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    raw = data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                model = AI_MODEL or "openai/gpt-4o-mini"
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {"Authorization":f"Bearer {key}","Content-Type":"application/json"}
                payload = {"model":model,"messages":[{"role":"user","content":prompt}],"temperature":0.1}
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    raw = data["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", raw, re.S)
        result = json.loads(match.group(0) if match else raw)
        return result
    except Exception as exc:
        result = rule_classify(text)
        result["reason"] += f" AI xatosi ({type(exc).__name__}); qoida filtri ishlatildi."
        return result
