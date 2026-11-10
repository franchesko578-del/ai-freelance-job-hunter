# AI Freelance Job Hunter

Telegram bot project for collecting programming job posts and notifying only the configured admin.

## Features
- Aiogram admin panel
- Telethon personal-account collector for configured Telegram channels
- Bot API channel_post ingestion when the bot is an administrator in the source channel
- RSS and public HTML page collectors
- AI classification through OpenRouter or Gemini, with rule-based fallback
- Excludes resumes, courses, unrelated roles and uncertain posts
- Missing budget/deadline does not disqualify a programming job
- Duplicate prevention
- Personal developer skills profile
- 15-minute scheduled scanning (configurable)
- Encrypted AI API key storage from the admin panel

## Important limitations
This cannot monitor literally every website or Telegram channel. Add sources that you are authorized to access. Telethon can read only channels/groups your account can access. Bot API only receives channel posts when the bot is added with appropriate rights. Some sites prohibit scraping or require APIs; use their official API/RSS and terms. Bot API channel_post ingestion works only for channels where the bot is added with appropriate administrator permissions. Do not treat this as a finished production service until tested with your real sources.

## Termux setup
```bash
pkg update -y && pkg upgrade -y
pkg install python git nano -y
unzip ai-freelance-job-hunter.zip
cd ai-freelance-job-hunter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

Set BOT_TOKEN, ADMIN_IDS (numeric Telegram ID), TELEGRAM_API_ID and TELEGRAM_API_HASH. Generate ENCRYPTION_KEY:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Put its output into `.env`. AI_PROVIDER can be `openrouter`, `gemini`, or `none`. Set AI_API_KEY and optional AI_MODEL. Never commit `.env` or `*.session`.

## Connect personal Telegram account
Run `python connect_telegram.py` in Termux. Enter login code/2FA in the terminal. The session file is sensitive and must never be shared or pushed to GitHub.

## Run
```bash
python main.py
```
Open the bot and use `/start`. Add sources in the admin menu using:
- `telegram @channelusername`
- `rss https://example.com/feed.xml`
- `website https://example.com/jobs`

## GitHub
```bash
git init
git add .
git status
git commit -m "Initial project"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ai-freelance-job-hunter.git
git push -u origin main
```
Check `git status` and ensure `.env` and session files are not staged before pushing.

## Hosting
Termux is for development/testing. Android can suspend background processes. For reliable 24/7 operation use a VPS/always-on host with persistent storage for `data/jobs.db` and `data/telethon.session`.
