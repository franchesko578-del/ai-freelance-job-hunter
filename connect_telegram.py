from telethon.sync import TelegramClient
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELETHON_SESSION

def main():
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        print("Avval .env ichiga TELEGRAM_API_ID va TELEGRAM_API_HASH kiriting.")
        return
    with TelegramClient(TELETHON_SESSION, int(TELEGRAM_API_ID), TELEGRAM_API_HASH) as client:
        me = client.get_me()
        print(f"Telegram akkaunt ulandi: {me.first_name} | ID: {me.id}")
        print("Session data/telethon.session ichida saqlandi. Uni hech kimga bermang.")

if __name__ == "__main__":
    main()
