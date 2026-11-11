import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cryptography.fernet import Fernet

import config
from app import db, runtime
from app.services import classifier
from app.services.notify import esc
from app.services.report import CATEGORY_UZ, ScanReport
from app.services.scanner import process_items, run_scan
from app.services.sources import parse_source_input
from app.services.telethon_manager import manager

log = logging.getLogger(__name__)
router = Router()


class Flow(StatesGroup):
    source = State()
    api_key = State()
    profile = State()
    interval = State()


def admin_ok(uid) -> bool:
    return uid in config.ADMIN_IDS


def menu():
    kb = InlineKeyboardBuilder()
    buttons = [
        ("🔎 Hozir tekshirish", "scan"), ("📋 Oxirgi hisobot", "report"),
        ("📡 Manbalar", "sources"), ("➕ Manba qo‘shish", "add"),
        ("📱 Akkaunt holati", "account"), ("🚫 Rad etilganlar", "rejected"),
        ("🤖 AI API key", "key"), ("👨‍💻 Ko‘nikmalarim", "profile"),
        ("⏱ Interval", "interval"), ("📊 Statistika", "stats"),
    ]
    for label, data in buttons:
        kb.button(text=label, callback_data=data)
    kb.adjust(2)
    return kb.as_markup()


async def send_long(message: Message, text: str, **kwargs):
    for i in range(0, len(text), 3900):
        await message.answer(text[i:i + 3900], **kwargs)


# ---------- Asosiy buyruqlar ----------
@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        await message.answer("Bu bot shaxsiy foydalanish uchun.")
        return
    await state.clear()
    await message.answer("🚀 <b>AI Freelance Job Hunter</b>\nAdmin panel", reply_markup=menu(), parse_mode="HTML")


@router.message(Command("admin"))
async def admin(message: Message, state: FSMContext):
    if admin_ok(message.from_user.id):
        await state.clear()
        await message.answer("Admin panel", reply_markup=menu())


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    if admin_ok(message.from_user.id):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=menu())


# ---------- Tekshirish va hisobot ----------
async def do_scan(message: Message, bot):
    await message.answer("🔎 Manbalar tekshirilmoqda...")
    report = await run_scan(bot, True)
    await send_long(message, report.format_html(), parse_mode="HTML", reply_markup=menu())


@router.callback_query(F.data == "scan")
async def scan_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer("Ruxsat yo‘q", show_alert=True)
    await call.answer()
    await do_scan(call.message, call.bot)


@router.message(Command("scan"))
async def scan_cmd(message: Message):
    if admin_ok(message.from_user.id):
        await do_scan(message, message.bot)


async def last_report_text() -> str:
    data = await db.get_json_setting("last_scan_report")
    if not data:
        return "Hali tekshiruv bo‘lmagan. «🔎 Hozir tekshirish» ni bosing."
    return ScanReport.from_dict(data).format_html()


@router.callback_query(F.data == "report")
async def report_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await call.answer()
    await call.message.answer(await last_report_text(), parse_mode="HTML", reply_markup=menu())


@router.message(Command("report"))
async def report_cmd(message: Message):
    if admin_ok(message.from_user.id):
        await message.answer(await last_report_text(), parse_mode="HTML", reply_markup=menu())


# ---------- Manbalar ----------
async def render_sources():
    rows = await db.list_sources()
    if not rows:
        return "Manbalar hali qo‘shilmagan.", None
    lines = ["📡 <b>Manbalar</b>"]
    kb = InlineKeyboardBuilder()
    for sid, kind, value, enabled in rows:
        lines.append(f"{'🟢' if enabled else '⚪'} #{sid} {esc(kind)}: {esc(value)}")
        kb.button(text=f"{'⏸ O‘chirib qo‘yish' if enabled else '▶️ Yoqish'} #{sid}", callback_data=f"toggle:{sid}")
        kb.button(text=f"🗑 O‘chirish #{sid}", callback_data=f"del:{sid}")
    kb.adjust(2)
    return "\n".join(lines), kb.as_markup()


async def show_sources(call: CallbackQuery, edit: bool):
    text, markup = await render_sources()
    if edit:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass
    await call.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "sources")
async def sources_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await call.answer()
    await show_sources(call, edit=False)


@router.message(Command("sources"))
async def sources_cmd(message: Message):
    if admin_ok(message.from_user.id):
        text, markup = await render_sources()
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("toggle:"))
async def toggle_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await db.toggle_source(int(call.data.split(":")[1]))
    await call.answer("Manba holati o‘zgardi")
    await show_sources(call, edit=True)


@router.callback_query(F.data.startswith("del:"))
async def delete_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    sid = int(call.data.split(":")[1])
    src = await db.get_source(sid)
    if not src:
        await call.answer("Manba topilmadi", show_alert=True)
        return await show_sources(call, edit=True)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, o‘chirish", callback_data=f"delok:{sid}")
    kb.button(text="↩️ Yo‘q", callback_data="sources")
    kb.adjust(2)
    await call.answer()
    await call.message.answer(f"#{sid} {esc(src[1])}: {esc(src[2])}\nShu manba o‘chirilsinmi?",
                              parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("delok:"))
async def delete_ok_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    done = await db.delete_source(int(call.data.split(":")[1]))
    await call.answer("O‘chirildi" if done else "Manba topilmadi")
    await show_sources(call, edit=False)


@router.callback_query(F.data == "add")
async def add_cb(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await call.answer()
    await state.set_state(Flow.source)
    await call.message.answer(
        "Manba formatlari:\n<code>telegram @kanal</code>\n<code>rss https://site/feed.xml</code>\n"
        "<code>website https://site/jobs</code>\n\nBekor qilish: /cancel", parse_mode="HTML")


@router.message(Flow.source)
async def add_source_msg(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        return
    parsed, error = parse_source_input(message.text)
    if error:
        return await message.answer(error + "\nQayta yuboring yoki /cancel.", parse_mode="HTML")
    kind, value = parsed
    added = await db.add_source(kind, value)
    await state.clear()
    if added:
        await message.answer(f"✅ Manba saqlandi: {esc(kind)} {esc(value)}", parse_mode="HTML", reply_markup=menu())
    else:
        await message.answer("ℹ️ Bu manba allaqachon qo‘shilgan.", reply_markup=menu())


# ---------- Akkaunt va tizim holati ----------
async def account_text() -> str:
    info = await manager.status()
    lines = ["📱 <b>Telegram akkaunt (Telethon)</b>"]
    lines.append(f"• API ma’lumotlari: {'✅' if info['configured'] else '❌ ' + esc(info['config_problem'])}")
    lines.append(f"• Sessiya turi: {esc(info['session_kind'])}")
    lines.append(f"• Ulanish: {'✅ ulangan' if info['connected'] else '❌ ulanmagan'}")
    lines.append(f"• Avtorizatsiya: {'✅' if info['authorized'] else '❌'}")
    if info["account"]:
        acc = info["account"]
        uname = f" (@{acc['username']})" if acc.get("username") else ""
        lines.append(f"• Akkaunt: {esc(acc['name'])}{esc(uname)} · ID {acc['id']}")
    if info["error"]:
        lines.append(f"⚠️ <b>Sabab:</b> {esc(info['error'])}")

    tg_sources = [s for s in await db.list_sources() if s[1] == "telegram"]
    lines.append("")
    lines.append("<b>Telegram manbalari</b>")
    if not tg_sources:
        lines.append("• Telegram manba qo‘shilmagan.")
    elif not info["authorized"]:
        lines.append("• Sessiya ishlamagani uchun manbalar tekshirilmadi.")
    else:
        for sid, _k, value, enabled in tg_sources:
            res = await manager.check_source(value)
            flag = "🟢" if enabled else "⚪"
            if res["ok"]:
                extra = f"o‘qildi, oxirgi xabar: {res['last_date'] or 'yo‘q'}" if res["messages"] else "o‘qildi, lekin xabar yo‘q"
                title = f" «{esc(res['title'])}»" if res["title"] else ""
                lines.append(f"{flag} #{sid} {esc(value)}{title} — ✅ {extra}")
            else:
                lines.append(f"{flag} #{sid} {esc(value)} — ❌ {esc(res['error'])}")

    lines += ["", "🤖 <b>AI</b>"]
    problem = classifier.ai_provider_problem()
    key, src = await classifier.resolve_ai_key()
    if problem:
        lines.append(f"• ❌ {esc(problem)}")
    elif config.AI_PROVIDER == "none" or not key:
        lines.append("• AI o‘chiq: faqat qoida filtri ishlaydi (aniqligi past).")
    else:
        lines.append(f"• Provayder: {esc(config.AI_PROVIDER)}, model: {esc(config.AI_MODEL or 'standart')}")
        lines.append(f"• Kalit manbai: {esc(src)}")
        h = classifier.health
        if h.last_error:
            lines.append(f"• ⚠️ Oxirgi xato: {esc(h.last_error)}")
        elif h.last_ok_at:
            lines.append(f"• ✅ Oxirgi muvaffaqiyatli so‘rov: {esc(h.last_ok_at)}")
        else:
            lines.append("• Hali so‘rov yuborilmagan.")

    created = await db.get_setting("db_created_at", "?")
    interval = await db.get_scan_interval()
    lines += ["", "🗄 <b>Baza</b>",
              f"• Yo‘l: {esc(config.DATABASE_PATH)}", f"• Yaratilgan: {esc(created)}",
              f"• Tekshirish oralig‘i: {interval} daqiqa"]
    if config.ON_RENDER and str(config.DATABASE_PATH).startswith(str(config.BASE_DIR)):
        lines.append("⚠️ Render'da baza loyiha papkasida: har deploy/restartda o‘chib ketishi mumkin. "
                     "Persistent disk ulang (README).")
    return "\n".join(lines)


async def send_account(message: Message):
    await message.answer("⏳ Telegram akkaunt tekshirilmoqda...")
    await send_long(message, await account_text(), parse_mode="HTML", reply_markup=menu())


@router.callback_query(F.data == "account")
async def account_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await call.answer()
    await send_account(call.message)


@router.message(Command("account"))
async def account_cmd(message: Message):
    if admin_ok(message.from_user.id):
        await send_account(message)


# ---------- Rad etilganlar ----------
async def rejected_text() -> str:
    rows = await db.recent_rejected(10)
    if not rows:
        return "Hali rad etilgan post yo‘q."
    breakdown = ", ".join(f"{CATEGORY_UZ.get(c, c)}: {n}" for c, n in await db.rejected_breakdown())
    lines = [f"🚫 <b>Oxirgi rad etilganlar</b>\nJami: {esc(breakdown)}\n"]
    for source, category, reason, snippet, engine, created in rows:
        lines.append(f"• [{esc(CATEGORY_UZ.get(category, category))}] {esc(source)}\n"
                     f"  «{esc((snippet or '')[:80])}»\n  Sabab: {esc((reason or '')[:140])} ({esc(engine)})")
    return "\n".join(lines)


@router.callback_query(F.data == "rejected")
async def rejected_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await call.answer()
    await send_long(call.message, await rejected_text(), parse_mode="HTML", reply_markup=menu())


@router.message(Command("rejected"))
async def rejected_cmd(message: Message):
    if admin_ok(message.from_user.id):
        await send_long(message, await rejected_text(), parse_mode="HTML", reply_markup=menu())


# ---------- AI kalit ----------
@router.callback_query(F.data == "key")
async def key_cb(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await call.answer()
    if not config.ENCRYPTION_KEY:
        return await call.message.answer("ENCRYPTION_KEY o‘rnatilmagan. Avval Fernet kalitini yarating (README).")
    await state.set_state(Flow.api_key)
    await call.message.answer("AI API keyni yuboring. U shifrlanib saqlanadi; xabar o‘chirib tashlanadi.\n"
                              "Bekor qilish: /cancel")


@router.message(Flow.api_key)
async def key_msg(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        return
    value = (message.text or "").strip()
    if len(value) < 10 or " " in value:
        return await message.answer("Bu API key ga o‘xshamaydi. Qayta yuboring yoki /cancel.")
    try:
        await db.save_encrypted_api_key(value, Fernet(config.ENCRYPTION_KEY.encode()))
        classifier.health.reset()
        try:
            await message.delete()
        except Exception:
            await message.answer("⚠️ Xabarni o‘chira olmadim, o‘zingiz o‘chirib yuboring.")
        await message.answer("🔐 API key shifrlangan holda saqlandi. Tekshirish uchun «📱 Akkaunt holati» ni oching.",
                             reply_markup=menu())
    except Exception:
        log.exception("API kalitni saqlab bo‘lmadi")
        await message.answer("Saqlashda xato. ENCRYPTION_KEY to‘g‘ri Fernet kalitimi?")
    await state.clear()


# ---------- Profil va interval ----------
@router.callback_query(F.data == "profile")
async def profile_cb(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await call.answer()
    await state.set_state(Flow.profile)
    await call.message.answer("Ko‘nikmalaringizni vergul bilan ajratib yuboring. "
                              "Masalan: Python, Aiogram, API, React, PostgreSQL.\nBekor qilish: /cancel")


@router.message(Flow.profile)
async def profile_msg(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        return
    value = (message.text or "").strip()
    if not value:
        return await message.answer("Matn yuboring yoki /cancel.")
    await db.set_profile(value[:1000])
    await state.clear()
    await message.answer("✅ Profil yangilandi.", reply_markup=menu())


@router.callback_query(F.data == "interval")
async def interval_cb(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await call.answer()
    await state.set_state(Flow.interval)
    await call.message.answer("Tekshirish intervalini daqiqada yuboring (5–1440).\nBekor qilish: /cancel")


@router.message(Flow.interval)
async def interval_msg(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        return
    try:
        value = max(5, min(1440, int((message.text or "").strip())))
    except ValueError:
        return await message.answer("Faqat raqam yuboring yoki /cancel.")
    await db.set_setting("scan_interval", str(value))
    applied = runtime.reschedule(value)
    await state.clear()
    note = "Darhol kuchga kirdi." if applied else "Bot qayta ishga tushganda kuchga kiradi."
    await message.answer(f"✅ Interval {value} daqiqaga saqlandi. {note}", reply_markup=menu())


@router.callback_query(F.data == "stats")
async def stats_cb(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer()
    await call.answer()
    total, sent, sources, rejected = await db.stats()
    last = await db.get_json_setting("last_scan_report")
    when = last.get("started_at") if last else "hali bo‘lmagan"
    await call.message.answer(
        f"📊 <b>Statistika</b>\nFaol manbalar: {sources}\nTopilgan mos e’lonlar: {total}\n"
        f"Yuborilgan: {sent}\nRad etilgan postlar: {rejected}\nOxirgi tekshiruv: {esc(when)}",
        parse_mode="HTML", reply_markup=menu())


# ---------- Bot API orqali kanal postlari ----------
@router.channel_post()
async def channel_post_ingest(message: Message):
    # Bot API faqat bot admin bo'lgan kanallardagi postlarni yetkazadi.
    body = (message.text or message.caption or "").strip()
    if not body:
        return
    source_name = message.chat.username or str(message.chat.id)
    item = {
        "source": "botapi:" + source_name,
        "source_kind": "botapi",
        "external_id": f"{message.chat.id}:{message.message_id}",
        "title": body[:120].replace("\n", " "),
        "text": body,
        "url": f"https://t.me/{message.chat.username}/{message.message_id}" if message.chat.username else None,
        "published_at": message.date.isoformat() if message.date else None,
    }
    try:
        await process_items([item], message.bot, True)
    except Exception:
        log.exception("channel_post qayta ishlashda xato")


@router.errors()
async def on_error(event):
    log.error("Handler xatosi: %s", type(event.exception).__name__, exc_info=event.exception)
    update = event.update
    try:
        target = update.callback_query.message if update.callback_query else update.message
        user = update.callback_query.from_user if update.callback_query else update.message.from_user
        if target and admin_ok(user.id):
            await target.answer(f"⚠️ Ichki xato: {esc(type(event.exception).__name__)}. Loglarni tekshiring.")
    except Exception:
        pass
    return True
