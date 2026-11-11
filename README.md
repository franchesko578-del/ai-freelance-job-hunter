# AI Freelance Job Hunter

Dasturlash bo'yicha freelance buyurtmalarni (Telegram, RSS, veb-sayt) topib, faqat adminlarga yuboradigan Telegram bot.

## Imkoniyatlar
- Aiogram 3 admin panel; faqat `ADMIN_IDS` ishlata oladi
- Telethon (shaxsiy akkaunt) orqali kanal/guruhlarni o'qish; `TELETHON_SESSION_STRING` bo'lsa StringSession
- RSS va ochiq HTML sahifalar
- AI (OpenRouter/Gemini) + qoida filtri (fallback). Rezyume, kurs va aloqasiz postlar rad etiladi
- Takroriy postlar: `UNIQUE(source, external_id)` + ko'rilgan (rad etilgan) postlar jadvali + bir xil matn tekshiruvi
- **Har tekshiruvdan keyin to'liq hisobot**: nechta xabar o'qildi, nechtasi takroriy, nechtasi rad etildi (sabab bilan), AI/collector xatolari
- Xatolar yashirilmaydi: Telegram sessiya, manba, RSS, web va AI xatolari admin'ga tushunarli ko'rsatiladi

## Bot buyruqlari
`/start` `/admin` — panel · `/scan` — hozir tekshirish · `/report` — oxirgi hisobot · `/account` — Telegram akkaunt, manbalar, AI va baza holati · `/sources` · `/rejected` — rad etilganlar va sabablari · `/cancel`

Manba formatlari: `telegram @kanal` (yoki `https://t.me/kanal`, `-100...` ID) · `rss https://...` · `website https://...`

## Termux
```bash
pkg update -y && pkg upgrade -y && pkg install python git nano -y
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env
python connect_telegram.py      # akkauntni bir marta ulash
python -m unittest discover -s tests -t . -v
```
**Muhim:** Render'dagi bot ishlab turganda Termux'da `python main.py` ni ishga tushirmang — bir xil `BOT_TOKEN` bilan ikkita polling `TelegramConflictError` beradi. Bir xil Telethon sessiyasini ham ikki joyda bir vaqtda ishlatmang (`AuthKeyDuplicatedError`): Render uchun alohida session yarating.

## Render
- Start command: `python main.py`; faqat **1 ta instance**.
- Env: `.env.example` dagi o'zgaruvchilar. `PYTHONUNBUFFERED=1` qo'shsangiz yaxshi.
- **Free** web service: 15 daqiqa trafiksiz qolsa uxlaydi va lokal fayllar (SQLite) restart/deployda o'chadi. Persistent disk faqat pullik rejada.
- Pullik rejada: Disks → Add Disk (mount `/var/data`) → `DATABASE_PATH=/var/data/jobs.db`.
- Free rejada: `SEED_SOURCES` bilan manbalarni qayta tiklang, AI kalitni `AI_API_KEY` env'da saqlang, uxlab qolmasligi uchun tashqi ping (masalan UptimeRobot) ishlating.

## Testlar
`python -m unittest discover -s tests -t . -v`
