# AI Freelance Job Hunter — audit va tuzatishlar hisoboti

## 0. Nima tekshirilmadi (avval o'qing)
Sandboxda tarmoq va `aiogram`, `telethon`, `APScheduler`, `aiohttp`, `aiosqlite`, `feedparser` yo'q edi. Shuning uchun:
- **Tekshirildi:** sintaksis (26 fayl), ichki importlar, qoida filtri, AI mantig'i (soxta HTTP javoblar), baza, scanner/dedup/hisobot, Telethon manager va collector mantig'i (soxta klient), log maxfiylashtirish, manba formatlari — **52 test: 51 o'tdi, 1 o'tkazib yuborildi**.
- **Tekshirilmadi (haqiqiy muhitda sinab ko'rish kerak):** aiogram handlerlari/`main.py` ishga tushishi, haqiqiy Telethon sessiyasi, haqiqiy Telegram/AI/RSS so'rovlari, Render deploy. RSS parse testi (`feedparser`) o'tkazib yuborildi — Termux'da o'zi ishlaydi.
- **"Hozir tekshirish → 0" ning aniq sababi aniqlanmadi.** Chunki sizning Render loglaringiz va haqiqiy sessiyangiz menda yo'q. Quyida mumkin bo'lgan sabablar va ularni bot ichida **aniq ko'rsatadigan** diagnostika qo'shildi.

## 1. ZIP audit
Kutilgan 12 fayl (main.py, config.py, requirements.txt, .env.example, connect_telegram.py, app/db.py, app/handlers.py, app/services/{classifier,scanner}.py, app/collectors/{rss,web,telethon_collector}.py) hammasi mavjud. `bot_full_source.txt` ZIP bilan aynan bir xil. Qo'shimcha: README.md, .gitignore, `__init__.py`, `bot_api_note.md`. `export_session.py` ZIP'da yo'q (shunday bo'lishi kerak); endi `.gitignore`da.

## 2. Topilgan xatolar va sabablari
| # | Xato | Oqibat |
|---|------|--------|
| 1 | `print()` buferlanadi, `logging` sozlanmagan | Render'da faqat `Running 'python main.py'` ko'rinishi mumkin (ehtimoliy sabab; aiogram INFO loglari ham chiqmagan) |
| 2 | Scanner va 3 collector `except: continue` / `return []` | Sessiya yaroqsiz, kanal topilmadi, HTTP 404 — hammasi "0" bo'lib ko'rinardi |
| 3 | Rad etilgan postlar saqlanmasdi | Har 15 daqiqada 60 ta post AI'dan qayta o'tardi (limit/xarajat); statistika yo'q |
| 4 | Xabar yuborilmasa ham `mark_notified` va `sent+=1`; HTML escape yo'q | `<`/`&` bor sarlavhada Telegram yuborishni rad etadi, e'lon "yuborildi" bo'lib qolib ketardi |
| 5 | `handlers.py` channel_post'da `\\n` | Bot API xabarlarida literal `\n` ko'rinardi |
| 6 | `rule_classify`: "бот" ⊂ "работа", "ios" ⊂ "curious" | Fallback rejimda ko'p aloqasiz post o'tardi |
| 7 | AI: HTTP status tekshirilmagan, JSON validatsiya yo'q, retry yo'q, Gemini kaliti URL'da | Sababsiz fallback; xato matnida kalit oqishi xavfi |
| 8 | Env'dagi AI kalit panel kalitidan ustun | Paneldan kiritilgan kalit e'tiborsiz qolardi |
| 9 | `-100...` ID satr sifatida uzatilgan | Telethon uni raqamli ID deb o'qimasligi mumkin (ishonchsiz) |
| 10 | Polling xatosi `gather` orqali butun jarayonni yiqitishi mumkin; SIGTERM'da toza to'xtash yo'q | Restart tsikli, deploy paytida to'qnashuv |
| 11 | Interval o'zgarishi restartni talab qilardi; scheduler `max_instances` yo'q | Qo'lda va avtomatik skan ustma-ust tushishi mumkin |
| 12 | `DATABASE_PATH` papkasi yaratilmasdi; `SCAN_INTERVAL_MINUTES=abc` bilan crash | Ishga tushmaslik |
| 13 | Manba duplikat qo'shilsa ham "saqlandi"; o'chirish yo'q | Chalkashlik |

**"0 yangi e'lon" ning mumkin bo'lgan sabablari** (endi hisobotda ajratib ko'rsatiladi): (a) Telethon sessiya yaroqsiz — hisobotda `❌ ishlamadi` + sabab; (b) username topilmadi/kanal yopiq — manba bo'yicha xato; (c) xabarlar o'qildi, lekin hammasi rad etildi — rad etish sabablari bilan; (d) hammasi takroriy; (e) post 72 soatdan eski; (f) manbada xabar yo'q — "xato emas" belgisi bilan.

## 3. Qilingan o'zgarishlar
- **Yangi:** `app/log.py` (darhol chiqadigan, sirlarni yashiradigan log), `app/runtime.py`, `app/services/{telethon_manager,notify,report,sources}.py`, `app/collectors/base.py`, `tests/`.
- **main.py:** bitta polling + supervisor (xatoda qulamaydi), `getMe` bilan token tekshiruvi, `delete_webhook`, SIGTERM/SIGINT'da toza to'xtash, interval jonli o'zgaradi, ishga tushganda 45 s dan keyin skan, ishga tushish xabari (`NOTIFY_ON_START=0` bilan o'chadi).
- **Telethon:** bitta umumiy klient (`receive_updates=False`), StringSession/fayl sessiya, tushunarli xato matnlari (AuthKeyDuplicated, FloodWait, yopiq kanal va h.k.), raqamli ID qo'llab-quvvatlash.
- **Scanner:** har collector bo'yicha alohida hisob, xatolar yashirilmaydi, ko'rilgan postlar (rad etilganlar ham) saqlanadi, bir xil matn boshqa manbada takrorlansa o'tkazib yuboriladi, `MAX_AGE_HOURS` filtri, yuborilmagan e'lonlar keyingi skanda qayta yuboriladi, rejalashtirilgan skan muammo topsa admin'ga (6 soatda bir marta) ogohlantirish.
- **Classifier:** so'z chegarali regexlar (uz/ru/en), HTTP status/JSON validatsiya, 429/5xx'da qayta urinish, 3 ketma-ket xatodan keyin AI 3 daqiqaga to'xtatiladi, AI ishlamaganda rad etilgan post keyinroq qayta ko'riladi (seen'ga yozilmaydi), kalit xato matnidan olib tashlanadi, Gemini kaliti sarlavhada.
- **Bot:** `/account` va «📱 Akkaunt holati», «📋 Oxirgi hisobot», «🚫 Rad etilganlar», manbani o'chirish (tasdiq bilan), t.me havolasi/`@`siz username qabul qilish, `/cancel`, barcha matnlar o'zbekcha, handler xatosi admin'ga ko'rinadi.
- **Baza:** `seen_items` jadvali, `jobs.text_hash` (avtomatik migratsiya), `db_created_at`, eski ma'lumotlar saqlanadi.
- **requirements.txt:** o'zgarmadi (yangi paket kerak bo'lmadi). **.env.example:** ixtiyoriy o'zgaruvchilar qo'shildi.

## 4. Render bo'yicha cheklovlar (Render hujjatlari bilan tekshirildi)
- Free web service 15 daqiqa kiruvchi trafiksiz qolsa uxlaydi; lokal fayllar (SQLite) restart, deploy va uxlashda yo'qoladi; persistent disk faqat pullik rejada. Disk ulansa zero-downtime deploy o'chadi (bu bitta polling uchun foydali).
- Yechimlar: (1) pullik reja + disk (`/var/data`, `DATABASE_PATH=/var/data/jobs.db`); (2) tashqi DB (masalan Render Postgres) — buning uchun `db.py` ni qayta yozish kerak, **bu amalga oshirilmadi**; (3) Free'da vaqtinchalik: `SEED_SOURCES`, `AI_API_KEY` env, tashqi ping.
- Bot ishga tushganda yuboriladigan xabardagi «Baza yaratilgan» sanasi har safar yangi bo'lsa — baza saqlanmayapti.

## 5. Termux (bitta blok)
```bash
cd ~/ai-freelance-job-hunter                 # yo'lni moslang
cp -r . ../ai-freelance-job-hunter.backup    # zaxira
termux-setup-storage                         # bir marta
unzip -o ~/storage/downloads/ai-freelance-job-hunter-fixed.zip -d .
source .venv/bin/activate 2>/dev/null || { python -m venv .venv && source .venv/bin/activate; }
pip install -r requirements.txt
python -m compileall -q . && echo SINTAKSIS_OK
python -m unittest discover -s tests -t . -v
git ls-files | grep -E '\.env$|\.session|export_session' && echo "XAVF: maxfiy fayl kuzatilmoqda!" || echo "Maxfiy fayl yo'q: OK"
git add -A && git status --short             # .env, *.session, export_session.py ko'rinmasligi kerak
git commit -m "Diagnostika, collector xatolari, /account, bitta polling"
git push origin main
```

## 6. Render'da qayta deploy
1. Termux'da `python main.py` ishlamayotganini tekshiring (`pkill -f "python main.py"`); Render'da bir xil `BOT_TOKEN` bilan boshqa service yo'qligiga ishoning.
2. Push'dan keyin Render avtomatik deploy qiladi (bo'lmasa: Manual Deploy → Deploy latest commit).
3. (Ixtiyoriy) Environment: `PYTHONUNBUFFERED=1`; pullik rejada disk va `DATABASE_PATH`.
4. Loglarda ketma-ket: `Bot: @...`, `HTTP server port`, `Bot ishga tushdi`. Telegramga «🟢 Bot ishga tushdi» keladi.
5. Botda `/account` → sessiya va manba holati; keyin «🔎 Hozir tekshirish» → to'liq hisobot. Menga `/account` va hisobot matnini (sirlarsiz) yuborsangiz, aniq sababni topamiz.
6. Telethon uchun Render'ga **alohida** session string yarating; Termux va Render bir xil sessiyani bir vaqtda ishlatmasin.

## 7. Test natijalari (sandbox)
```
Ran 52 tests — OK (skipped=1)
```
O'tkazib yuborilgan: RSS parse (feedparser yo'q). Shim'lar faqat testlarda (`tests/__init__.py`), kutubxona o'rnatilgan bo'lsa haqiqiysi ishlatiladi.
