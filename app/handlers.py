from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from cryptography.fernet import Fernet
from config import ADMIN_IDS, ENCRYPTION_KEY
from app import db
from app.services.scanner import run_scan

router = Router()

class Flow(StatesGroup):
    source = State()
    api_key = State()
    profile = State()
    interval = State()

def admin_ok(uid):
    return uid in ADMIN_IDS

def menu():
    kb = InlineKeyboardBuilder()
    buttons = [("🔎 Hozir tekshirish","scan"),("📡 Manbalar","sources"),("➕ Manba qo‘shish","add"),
               ("🤖 AI API key","key"),("👨‍💻 Ko‘nikmalarim","profile"),("⏱ Interval","interval"),("📊 Statistika","stats")]
    for label, data in buttons:
        kb.button(text=label, callback_data=data)
    kb.adjust(2,2,2,1)
    return kb.as_markup()

@router.message(CommandStart())
async def start(message: Message):
    if not admin_ok(message.from_user.id):
        await message.answer("Bu bot shaxsiy foydalanish uchun.")
        return
    await message.answer("🚀 <b>AI Freelance Job Hunter</b>\nAdmin panel", reply_markup=menu(), parse_mode="HTML")

@router.message(Command("admin"))
async def admin(message: Message):
    if admin_ok(message.from_user.id):
        await message.answer("Admin panel", reply_markup=menu())

@router.callback_query(F.data == "scan")
async def scan_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer("Ruxsat yo‘q", show_alert=True)
    await call.answer()
    await call.message.answer("🔎 Manbalar tekshirilmoqda...")
    count = await run_scan(call.bot, True)
    await call.message.answer(f"✅ Tekshiruv tugadi. Yangi mos e’lonlar: {count}", reply_markup=menu())

@router.callback_query(F.data == "sources")
async def sources_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    rows = await db.list_sources()
    if not rows:
        return await call.message.answer("Manbalar hali qo‘shilmagan.")
    lines = ["📡 <b>Manbalar</b>"]
    kb = InlineKeyboardBuilder()
    for sid, kind, value, enabled in rows:
        lines.append(f"{'🟢' if enabled else '⚪'} #{sid} {kind}: {value}")
        kb.button(text=f"{'O‘chirish' if enabled else 'Yoqish'} #{sid}", callback_data=f"toggle:{sid}")
    kb.adjust(2)
    await call.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("toggle:"))
async def toggle_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await db.toggle_source(int(call.data.split(":")[1]))
    await call.answer("Manba holati o‘zgardi")
    await sources_cb(call)

@router.callback_query(F.data == "add")
async def add_cb(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await state.set_state(Flow.source)
    await call.message.answer("Manba formatlari:\n<code>telegram @kanal</code>\n<code>rss https://site/feed.xml</code>\n<code>website https://site/jobs</code>", parse_mode="HTML")

@router.message(Flow.source)
async def add_source_msg(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        return
    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() not in {"telegram","rss","website"}:
        return await message.answer("Format noto‘g‘ri. Qayta yuboring.")
    kind, value = parts[0].lower(), parts[1].strip()
    if kind == "telegram" and not (value.startswith("@") or value.startswith("-100")):
        return await message.answer("Kanal username'i @ bilan boshlansin.")
    if kind in {"rss","website"} and not value.startswith("https://"):
        return await message.answer("Faqat https:// manzil qabul qilinadi.")
    await db.add_source(kind, value)
    await state.clear()
    await message.answer("✅ Manba saqlandi.", reply_markup=menu())

@router.callback_query(F.data == "key")
async def key_cb(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    if not ENCRYPTION_KEY:
        return await call.message.answer("ENCRYPTION_KEY .env faylida yo‘q. Avval Fernet kalitini yarating.")
    await state.set_state(Flow.api_key)
    await call.message.answer("AI API keyni yuboring. U shifrlanib saqlanadi; xabar o‘chirib tashlanadi.")

@router.message(Flow.api_key)
async def key_msg(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        return
    try:
        fernet = Fernet(ENCRYPTION_KEY.encode())
        await db.save_encrypted_api_key((message.text or "").strip(), fernet)
        await message.delete()
        await message.answer("🔐 API key shifrlangan holda saqlandi.")
    except Exception:
        await message.answer("Saqlashda xato. ENCRYPTION_KEY ni tekshiring.")
    await state.clear()

@router.callback_query(F.data == "profile")
async def profile_cb(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await state.set_state(Flow.profile)
    await call.message.answer("Ko‘nikmalaringizni vergul bilan ajratib yuboring. Masalan: Python, Aiogram, API, React, PostgreSQL.")

@router.message(Flow.profile)
async def profile_msg(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        return
    await db.set_profile((message.text or "").strip())
    await state.clear()
    await message.answer("✅ Profil yangilandi.", reply_markup=menu())

@router.callback_query(F.data == "interval")
async def interval_cb(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await state.set_state(Flow.interval)
    await call.message.answer("Tekshirish intervalini daqiqada yuboring (5–1440).")

@router.message(Flow.interval)
async def interval_msg(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        return
    try:
        value = max(5, min(1440, int((message.text or "").strip())))
    except ValueError:
        return await message.answer("Faqat raqam yuboring.")
    await db.set_setting("scan_interval", str(value))
    await state.clear()
    await message.answer(f"Interval {value} daqiqaga saqlandi. O‘zgarish bot qayta ishga tushganda kuchga kiradi.", reply_markup=menu())

@router.callback_query(F.data == "stats")
async def stats_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    total, sent, sources = await db.stats()
    await call.message.answer(f"📊 Statistika\nManbalar: {sources}\nTopilgan mos e’lonlar: {total}\nYuborilgan: {sent}")


@router.channel_post()
async def channel_post_ingest(message: Message):
    # Bot API only delivers posts from channels where this bot has been added
    # with the required permissions. It cannot read arbitrary channels.
    if not message.text and not message.caption:
        return
    from app.services.classifier import classify
    body = (message.text or message.caption or "").strip()
    result = await classify(body)
    if not result.get("relevant") or result.get("category") != "programming_job":
        return
    source_name = message.chat.username or str(message.chat.id)
    source = "botapi:" + source_name
    external_id = f"{message.chat.id}:{message.message_id}"
    item = {
        "source": source,
        "source_kind": "botapi",
        "external_id": external_id,
        "title": result.get("title") or body[:120].replace("\\n", " "),
        "text": body,
        "url": f"https://t.me/{message.chat.username}/{message.message_id}" if message.chat.username else None,
        "language": result.get("language"),
        "category": "programming_job",
        "confidence": float(result.get("confidence", 0) or 0),
        "match_score": int(result.get("match_score", 0) or 0),
        "reason": result.get("reason", ""),
        "published_at": message.date.isoformat() if message.date else None,
    }
    job_id = await db.save_job(item)
    if not job_id:
        return
    notification = (
        "🎯 <b>YANGI MOS DASTURLASH ISHI</b>\\n\\n"
        f"<b>{item['title']}</b>\\n"
        f"{result.get('task_summary','')}\\n\\n"
        f"📌 Moslik: {item['match_score']}/100\\n"
        f"🧠 AI: {item['reason']}\\n"
        f"🌐 Manba: {source}\\n"
        f"🔗 {item.get('url') or 'Havola mavjud emas'}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(admin_id, notification, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass
    await db.mark_notified(job_id)
