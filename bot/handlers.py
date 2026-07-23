"""Бот: расклады в чате + полный доступ (звёзды). Приложение — опционально."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, CommandStart
from pathlib import Path

from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from bot import db as store
from bot.admin import admin_ids, format_stats, is_admin
from bot.cards import DECK, draw
from bot.i18n import normalize_lang, system_prompt, t
from bot.keyboards import (
    after_spread,
    cancel_support_kb,
    language_inline,
    main_menu,
    open_app_inline,
    premium_inline,
    support_inline,
    thanks_inline,
)
from bot.llm import build_asc_day_prompt, build_spread_prompt, chat, fallback_spread_text
from bot.premium import FREE_AI_READINGS_PER_DAY, PLANS, feature_allowed, plan_by_payload
from bot.spreads import SPREADS
from bot.tarot import TAROT_SPREADS, draw_tarot, tarot_to_dict

ROOT = Path(__file__).resolve().parent.parent
WELCOME_IMAGE = ROOT / "assets" / "welcome.jpg"
if not WELCOME_IMAGE.exists():
    WELCOME_IMAGE = ROOT / "miniapp" / "assets" / "hero.jpg"
if not WELCOME_IMAGE.exists():
    WELCOME_IMAGE = ROOT / "assets" / "bot_avatar.jpg"


class IsAdminFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.from_user and is_admin(message.from_user.id))


logger = logging.getLogger(__name__)
router = Router()

# user_id -> waiting for birth data
_waiting_birth: set[int] = set()
# user_id -> last free-text question
_last_question: dict[int, str] = {}
# user_id -> waiting support message for owner
_waiting_support: set[int] = set()
# user_id -> waiting custom tip stars amount
_waiting_tip: set[int] = set()

BUTTON_TO_SPREAD = {
    "☀️ Карта дня": "day",
    "✨ Три карты": "three",
    "💗 Любовь": "love",
    "🌿 Ситуация": "situation",
    "🌻 Дело": "work",
    "🔮 Да / Нет": "yesno",
    "🌈 Путь": "path",
    "📅 Неделя": "week",
    "🗓️ Месяц": "month",
    "🃏 Таро: карта дня": "t_day",
    "🃏 Таро: три карты": "t_three",
    "🃏 Таро: любовь": "t_love",
    "🃏 Таро: путь": "t_path",
}


def _lang(user_id: int | None, telegram_code: str | None = None) -> str:
    if user_id:
        saved = store.get_user_lang(user_id)
        if saved:
            return normalize_lang(saved)
    return normalize_lang(telegram_code)


def _name(user) -> str:
    if not user:
        return t("fallback_name", "ru")
    return (user.first_name or user.username or t("fallback_name", "ru")).strip()


async def _send_welcome(message: Message, lang: str) -> None:
    """Красивое фото + приветствие с именем + кнопка приложения."""
    name = _name(message.from_user)
    caption = t("welcome", lang, name=name)
    kb = open_app_inline(lang)
    try:
        if WELCOME_IMAGE.exists():
            photo = FSInputFile(str(WELCOME_IMAGE))
            # caption limit ~1024
            short = caption if len(caption) <= 1000 else t("welcome_caption", lang, name=name)
            await message.answer_photo(
                photo,
                caption=short,
                parse_mode="Markdown",
                reply_markup=kb or main_menu(),
            )
            if short != caption:
                await message.answer(caption, parse_mode="Markdown", reply_markup=kb or main_menu())
            return
    except Exception as e:
        logger.warning("welcome photo: %s", e)
    await message.answer(caption, parse_mode="Markdown", reply_markup=kb or main_menu())


def _chunk(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, buf, size = [], [], 0
    for line in text.split("\n"):
        add = len(line) + 1
        if size + add > limit and buf:
            parts.append("\n".join(buf))
            buf, size = [line], add
        else:
            buf.append(line)
            size += add
    if buf:
        parts.append("\n".join(buf))
    return parts


async def _send_long(message: Message, text: str, **kwargs) -> None:
    chunks = _chunk(text)
    for i, c in enumerate(chunks):
        kw = kwargs if i == len(chunks) - 1 else {k: v for k, v in kwargs.items() if k != "reply_markup"}
        await message.answer(c, **kw)


def _cards_to_dicts(cards) -> list[dict]:
    return [
        {
            "number": c.number,
            "name": c.name,
            "emoji": c.emoji,
            "keywords": c.keywords,
            "general": c.general,
            "love": c.love,
            "work": c.work,
            "advice": c.advice,
        }
        for c in cards
    ]


async def _run_spread(message: Message, spread_id: str, question: str | None = None) -> None:
    user = message.from_user
    if not user:
        return
    uid = user.id
    store.upsert_user(uid, user.username, user.first_name)

    is_tarot = spread_id.startswith("t_")
    if is_tarot:
        if spread_id not in TAROT_SPREADS:
            await message.answer("Расклад не найден.", reply_markup=main_menu())
            return
        meta = TAROT_SPREADS[spread_id]
        spread_title = meta["title"]
        spread_emoji = meta["emoji"]
        spread_blurb = meta["blurb"]
        n_cards = meta["n"]
        positions = list(meta["positions"])
    else:
        if spread_id not in SPREADS:
            await message.answer("Расклад не найден.", reply_markup=main_menu())
            return
        spread = SPREADS[spread_id]
        spread_title = spread.title
        spread_emoji = spread.emoji
        spread_blurb = spread.blurb
        n_cards = spread.n_cards
        positions = list(spread.positions)

    prem = store.is_premium(uid)
    gate = feature_allowed(spread_id, is_premium=prem, free_ai_left=1)
    if not gate["ok"]:
        await message.answer(gate["message"], reply_markup=premium_inline())
        return

    # day once (lenormand)
    if spread_id == "day":
        existing = store.get_day_reading(uid, "day")
        if existing and existing.get("ai_text"):
            await _send_long(
                message,
                f"☀️ **Карта дня** (уже на сегодня)\n\n{existing['ai_text']}",
                parse_mode="Markdown",
                reply_markup=after_spread("day"),
            )
            return
    if spread_id == "t_day":
        existing = store.get_day_reading(uid, "t_day")
        if existing and existing.get("ai_text"):
            await _send_long(
                message,
                f"🃏 **Карта дня (Таро)** (уже на сегодня)\n\n{existing['ai_text']}",
                parse_mode="Markdown",
                reply_markup=after_spread("t_day"),
            )
            return

    await message.answer("🕊️ Тасую карты и готовлю прогноз…")

    if is_tarot:
        cards_d = [tarot_to_dict(c) for c in draw_tarot(n_cards)]
    else:
        cards_d = _cards_to_dicts(draw(n_cards))

    lines = [f"{spread_emoji} **{spread_title}**\n_{spread_blurb}_\n"]
    if question:
        lines.append(f"Вопрос: _{question}_\n")
    for i, c in enumerate(cards_d):
        pos = positions[i] if i < len(positions) else f"Карта {i+1}"
        body = c.get("upright") or c.get("general") or ""
        lines.append(
            f"**{pos}**\n{c['emoji']} **{c['name']}**\n_{c['keywords']}_\n{body}\n"
        )

    left = 999 if prem else store.free_ai_left(uid, free_limit=FREE_AI_READINGS_PER_DAY)
    agate = feature_allowed("ai", is_premium=prem, free_ai_left=left)

    lang = _lang(uid, getattr(message.from_user, "language_code", None) if message.from_user else None)
    ai_text = None
    if agate["ok"]:
        prompt = build_spread_prompt(
            spread_title=spread_title,
            spread_blurb=spread_blurb + (
                " System: Rider–Waite Tarot." if is_tarot and lang == "en"
                else " Система: Таро Райдера–Уэйта." if is_tarot
                else " System: Lenormand." if lang == "en"
                else " Система: Ленорман."
            ),
            cards=cards_d,
            positions=positions,
            question=question,
            extra=t("llm_lang_note", lang),
        )
        try:
            ai_text, provider, model = chat(prompt, system=system_prompt(lang))
            if not prem:
                store.consume_ai_quota(uid, free_limit=FREE_AI_READINGS_PER_DAY)
            lines.append(f"\n✨ **Живой прогноз**\n{ai_text}" if lang == "ru" else f"\n✨ **Live reading**\n{ai_text}")
        except Exception as e:
            ai_text = fallback_spread_text(cards_d, spread_title)
            lines.append(f"\n✨ **Прогноз**\n{ai_text}\n\n_({e})_")
    else:
        lines.append(f"\n_{agate['message']}_")
        ai_text = "\n".join(lines)

    text = "\n".join(lines)
    if spread_id in ("day", "t_day"):
        store.touch_day_streak(uid)
    store.save_reading(
        uid,
        spread_id,
        spread_title,
        question,
        cards_d,
        ai_text or text,
        {"system": "tarot" if is_tarot else "lenormand", "lang": lang},
        day_key=store.today_key() if spread_id in ("day", "t_day") else store.today_key(),
    )
    await _send_long(message, text, parse_mode="Markdown", reply_markup=after_spread(spread_id, lang))
    # soft CTA: thank + invite
    try:
        from bot.keyboards import thanks_inline
        await message.answer(
            "💛 " + ("Понравилось? Можно сказать спасибо звёздами или пригласить друга /invite"
                     if lang == "ru" else
                     "Liked it? Say thanks with Stars or invite a friend /invite"),
            reply_markup=thanks_inline(lang),
        )
    except Exception:
        pass


def _parse_birth(text: str) -> tuple[str, str, str] | None:
    """
    Accept: 15.06.1990 14:30 Москва
            1990-06-15 14:30 Москва
    Returns (YYYY-MM-DD, HH:MM, place)
    """
    t = " ".join(text.strip().split())
    m = re.match(
        r"^(\d{1,2})[./](\d{1,2})[./](\d{4})\s+(\d{1,2}):(\d{2})(?:\s*:\d{2})?\s+(.+)$",
        t,
    )
    if m:
        d, mo, y, h, mi, place = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}", f"{int(h):02d}:{int(mi):02d}", place.strip()
    m = re.match(
        r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})(?:\s*:\d{2})?\s+(.+)$",
        t,
    )
    if m:
        y, mo, d, h, mi, place = m.groups()
        return f"{y}-{mo}-{d}", f"{int(h):02d}:{int(mi):02d}", place.strip()
    return None


async def _run_asc_day(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    uid = user.id
    prof = store.get_default_profile(uid)
    if not prof or not prof.get("sign"):
        _waiting_birth.add(uid)
        lang = _lang(uid, getattr(message.from_user, "language_code", None) if message.from_user else None)
        await message.answer(t("ask_birth", lang), parse_mode="Markdown", reply_markup=main_menu())
        return

    lang = _lang(uid, getattr(message.from_user, "language_code", None) if message.from_user else None)
    existing = store.get_day_reading(uid, "asc_day")
    if existing and existing.get("ai_text"):
        await _send_long(
            message,
            f"🌅 **День по восходящему знаку** (уже на сегодня)\n\n{existing['ai_text']}"
            if lang == "ru"
            else f"🌅 **Day by rising sign** (already today)\n\n{existing['ai_text']}",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        return

    await message.answer(
        "🕊️ Считаю день по восходящему знаку…" if lang == "ru" else "🕊️ Calculating your day by rising sign…"
    )
    day_key = store.today_key()
    seed = f"{day_key}-{prof['sign']}-{prof.get('absolute_degree', 0)}"
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    card = DECK[h % len(DECK)]
    cards_d = _cards_to_dicts([card])

    prompt = build_asc_day_prompt(
        sign=prof["sign"],
        emoji=prof.get("emoji") or "✦",
        degree=float(prof.get("degree_in_sign") or 0),
        place=prof.get("place") or "",
        card=cards_d[0],
    )
    prem = store.is_premium(uid)
    left = 999 if prem else store.free_ai_left(uid, free_limit=FREE_AI_READINGS_PER_DAY)
    agate = feature_allowed("ai", is_premium=prem, free_ai_left=left)

    header = (
        f"🌅 **День по восходящему знаку · {prof.get('emoji', '')} {prof['sign']}**\n"
        f"_{prof.get('degree_in_sign', '')}° · {prof.get('place', '')}_\n\n"
        f"Карта: {card.emoji} **{card.number}. {card.name}**\n_{card.keywords}_\n{card.general}\n"
    )
    if agate["ok"]:
        try:
            ai_text, _, _ = chat(prompt, system=system_prompt(lang))
            if not prem:
                store.consume_ai_quota(uid, free_limit=FREE_AI_READINGS_PER_DAY)
            text = header + (f"\n✨ **Живой прогноз**\n{ai_text}" if lang == "ru" else f"\n✨ **Live reading**\n{ai_text}")
        except Exception as e:
            text = header + f"\n✨\n{fallback_spread_text(cards_d, 'Day')}\n\n_({e})_"
    else:
        text = header + f"\n_{agate['message']}_"

    store.touch_day_streak(uid)
    store.save_reading(uid, "asc_day", f"День · {prof['sign']}", None, cards_d, text, {"profile": prof["sign"], "lang": lang})
    await _send_long(message, text, parse_mode="Markdown", reply_markup=main_menu())


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    tg_lang = getattr(user, "language_code", None) if user else None
    if user:
        store.upsert_user(user.id, user.username, user.first_name)

    saved = store.get_user_lang(user.id) if user else None
    args = (message.text or "").split(maxsplit=1)
    payload = args[1].strip().lower() if len(args) > 1 else ""

    # referral: ref_XXXX or refXXXX
    ref_code = None
    if payload.startswith("ref_"):
        ref_code = payload[4:]
    elif payload.startswith("ref") and len(payload) > 3:
        ref_code = payload[3:]

    # deep-link language
    if payload in ("en", "lang_en", "english"):
        if user:
            store.set_user_lang(user.id, "en")
        lang = "en"
    elif payload in ("ru", "lang_ru", "russian", "рус"):
        if user:
            store.set_user_lang(user.id, "ru")
        lang = "ru"
    elif not saved:
        guess = normalize_lang(tg_lang)
        await message.answer(
            t("choose_lang", guess),
            reply_markup=language_inline(),
        )
        if user and not saved:
            store.set_user_lang(user.id, guess)
        lang = guess
    else:
        lang = normalize_lang(saved)

    if user and ref_code:
        res = store.apply_referral(user.id, ref_code)
        if res.get("ok"):
            await message.answer(
                "🎁 " + ("Бонус: +1 живой прогноз вам и другу!" if lang == "ru"
                         else "🎁 Bonus: +1 live reading for you and your friend!")
            )
            inv = res.get("inviter_id")
            if inv:
                try:
                    await message.bot.send_message(
                        inv,
                        "🎁 " + ("По вашей ссылке пришёл друг — вам +1 живой прогноз!"
                                 if lang == "ru" else
                                 "A friend joined via your link — you get +1 live reading!"),
                    )
                except Exception:
                    pass

    # сброс старой нижней клавиатуры + welcome с фото
    await message.answer("\u200b", reply_markup=main_menu())
    await _send_welcome(message, lang)

    # deep-link actions / spreads → open app with startapp-like hint
    SPREAD_PAYLOADS = {
        "day": "day", "card": "day", "карта": "day",
        "t_day": "t_day", "tarot": "t_day", "таро": "t_day",
        "three": "three", "три": "three",
        "love": "love", "любовь": "love",
        "yesno": "yesno", "данет": "yesno",
        "situation": "situation", "ситуация": "situation",
        "work": "work", "дело": "work",
        "path": "path", "путь": "path",
        "asc": "asc_day", "asc_day": "asc_day", "восходящий": "asc_day",
    }
    if payload in ("premium", "pay", "stars", "dostup", "доступ"):
        await cmd_premium(message)
    elif payload in ("podderzhka", "support", "help", "помощь", "поддержка"):
        await cmd_support(message)
    elif payload in ("lang", "language", "язык"):
        await cmd_lang(message)
    elif payload in ("spasibo", "thanks", "tip", "donate", "спасибо"):
        await cmd_thanks(message)
    elif payload in ("invite", "ref", "реферал", "друг"):
        await cmd_invite(message)
    elif payload in ("notify", "утро", "morning"):
        await cmd_notify(message)
    elif payload in SPREAD_PAYLOADS:
        sid = SPREAD_PAYLOADS[payload]
        from bot.keyboards import miniapp_url
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
        url = miniapp_url()
        if url:
            sep = "&" if "?" in url else "?"
            app = f"{url}{sep}lang={lang}&spread={sid}"
            await message.answer(
                "✨ " + ("Откройте расклад в приложении:" if lang == "ru" else "Open the spread in the app:"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=t("open_app", lang),
                        web_app=WebAppInfo(url=app),
                    )
                ]]),
            )


@router.message(Command("invite", "ref", "друг", "реферал"))
async def cmd_invite(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    lang = _lang(uid, getattr(message.from_user, "language_code", None))
    code = store.get_or_create_ref_code(uid)
    link = f"https://t.me/AstoManiabot?start=ref_{code}"
    bonus = store.get_bonus_ai(uid)
    if lang == "en":
        text = (
            f"🎁 **Invite a friend**\n\n"
            f"Share this link. When they start the bot, you both get **+1 live reading**.\n\n"
            f"`{link}`\n\n"
            f"Your bonus readings left: **{bonus}**"
        )
    else:
        text = (
            f"🎁 **Пригласить друга**\n\n"
            f"Отправьте ссылку. Когда друг нажмёт /start — вам обоим **+1 живой прогноз**.\n\n"
            f"`{link}`\n\n"
            f"Ваши бонусные прогнозы: **{bonus}**"
        )
    await message.answer(text, parse_mode="Markdown", disable_web_page_preview=True)


@router.message(Command("notify", "утро", "morning", "напоминание"))
async def cmd_notify(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    lang = _lang(uid, getattr(message.from_user, "language_code", None))
    # toggle
    with store.db() as conn:
        row = conn.execute("SELECT notify FROM users WHERE user_id=?", (uid,)).fetchone()
        cur = int((row["notify"] if row else 0) or 0)
    new = 0 if cur else 1
    store.set_notify(uid, enabled=bool(new), hour=9, tz="Europe/Moscow")
    if new:
        msg = "🔔 Утренние напоминания включены (около 9:00 МСК)." if lang == "ru" else "🔔 Morning reminders on (~9:00 MSK)."
    else:
        msg = "🔕 Напоминания выключены." if lang == "ru" else "🔕 Reminders off."
    await message.answer(msg)


@router.message(Command("lang", "language", "язык", "language_code"))
async def cmd_lang(message: Message) -> None:
    lang = _lang(
        message.from_user.id if message.from_user else None,
        getattr(message.from_user, "language_code", None) if message.from_user else None,
    )
    await message.answer(t("choose_lang", lang), reply_markup=language_inline())


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(query: CallbackQuery) -> None:
    code = (query.data or "lang:ru").split(":", 1)[1]
    lang = normalize_lang(code)
    if query.from_user:
        store.upsert_user(query.from_user.id, query.from_user.username, query.from_user.first_name)
        store.set_user_lang(query.from_user.id, lang)
    await query.answer(t("lang_set", lang))
    if query.message:
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        # fake message context for welcome
        class _M:
            pass

        # use real message
        await query.message.answer(t("lang_set", lang), reply_markup=main_menu())
        await _send_welcome(query.message, lang)


@router.message(Command("app", "open", "menu", "приложение"))
async def cmd_app(message: Message) -> None:
    lang = _lang(
        message.from_user.id if message.from_user else None,
        getattr(message.from_user, "language_code", None) if message.from_user else None,
    )
    kb = open_app_inline(lang)
    if kb:
        await message.answer(t("open_app_msg", lang), reply_markup=kb)
    else:
        await message.answer(t("no_app", lang), reply_markup=main_menu())


@router.message(Command("help", "помощь"))
async def cmd_help(message: Message) -> None:
    lang = _lang(
        message.from_user.id if message.from_user else None,
        getattr(message.from_user, "language_code", None) if message.from_user else None,
    )
    await message.answer(
        t("help", lang),
        parse_mode="Markdown",
        reply_markup=open_app_inline(lang) or main_menu(),
    )


@router.message(Command("premium", "stars", "pay", "dostup", "доступ"))
async def cmd_premium(message: Message) -> None:
    lang = "ru"
    if message.from_user:
        store.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
        lang = _lang(message.from_user.id, getattr(message.from_user, "language_code", None))
        info = store.premium_info(message.from_user.id)
        status = (
            t("premium_active", lang, until=info["until"][:10])
            if info["active"]
            else t("premium_free", lang)
        )
    else:
        status = ""
    await message.answer(
        t("premium", lang) + status,
        parse_mode="Markdown",
        reply_markup=premium_inline(lang),
    )


@router.message(Command("money", "withdraw", "вывод"))
async def cmd_money(message: Message) -> None:
    from bot.texts import HOW_MONEY

    await message.answer(HOW_MONEY, parse_mode="Markdown")


@router.message(Command("status", "статус"))
async def cmd_status(message: Message) -> None:
    if not message.from_user:
        return
    lang = _lang(message.from_user.id, getattr(message.from_user, "language_code", None))
    info = store.premium_info(message.from_user.id)
    used = store.count_ai_today(message.from_user.id)
    left = store.free_ai_left(message.from_user.id, free_limit=FREE_AI_READINGS_PER_DAY)
    streak = store.get_streak(message.from_user.id)
    if info["active"]:
        await message.answer(
            t("status_prem", lang, until=info["until"][:10])
            + (f"\n🔥 streak: {streak}" if streak else ""),
            reply_markup=open_app_inline(lang),
        )
    else:
        extra = f"\n🔥 {streak} " + ("дн. подряд" if lang == "ru" else "day streak") if streak else ""
        extra += f"\n🎁 bonus: {store.get_bonus_ai(message.from_user.id)}"
        await message.answer(
            t("status_free", lang, used=used) + f"\n" + (f"Осталось сегодня (с бонусом): {left}" if lang == "ru" else f"Left today (with bonus): {left}")
            + extra,
            reply_markup=open_app_inline(lang),
        )


@router.message(F.text.in_({"✖️ Отмена", "✖️ Cancel"}))
async def btn_cancel(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    lang = _lang(uid, getattr(message.from_user, "language_code", None))
    _waiting_birth.discard(uid)
    _waiting_support.discard(uid)
    _waiting_tip.discard(uid)
    await message.answer(t("cancelled", lang), reply_markup=main_menu())
    kb = open_app_inline(lang)
    if kb:
        await message.answer(t("app_below", lang), reply_markup=kb)


@router.message(Command("myid", "мойid", "id", "ктоя"))
async def cmd_myid(message: Message) -> None:
    """Полезно владельцу: узнать свой Telegram id для ADMIN_IDS."""
    if not message.from_user:
        return
    u = message.from_user
    admin_ok = is_admin(u.id)
    admins_set = bool(admin_ids())
    lines = [
        f"Ваш id: {u.id}",
        f"Юзернейм: @{u.username or '—'}",
        f"Имя: {u.first_name or '—'}",
        "",
        f"Доступ владельца: {'да ✅' if admin_ok else 'нет ❌'}",
        f"ADMIN_IDS на сервере: {'задан (' + str(len(admin_ids())) + ')' if admins_set else 'не задан'}",
    ]
    if admin_ok:
        lines.append("\nКоманды: /stats · /dostup · /podderzhka")
        lines.append("В приложении: «Статистика (владелец)» внизу меню")
    else:
        lines.append("\nДобавьте этот id в ADMIN_IDS на Railway и перезапустите сервис.")
    await message.answer("\n".join(lines))


@router.message(Command("stats", "stat", "статистика", "admin"))
async def cmd_stats(message: Message) -> None:
    if not message.from_user:
        return
    if not is_admin(message.from_user.id):
        await message.answer(
            "📊 Статистика только для владельца.\n\n"
            f"Ваш id: {message.from_user.id}\n"
            "Напишите /myid — статус доступа.\n"
            f"ADMIN_IDS на сервере: {'задан' if admin_ids() else 'НЕ задан'}",
        )
        return
    stats = store.get_usage_stats()
    text = format_stats(stats)
    recent = stats.get("recent_users") or []
    if recent:
        lines = ["\n👤 Последние пользователи:"]
        for r in recent:
            un = f"@{r['username']}" if r.get("username") else r.get("first_name") or "—"
            lines.append(f"  · {r['user_id']} {un}")
        text += "\n" + "\n".join(lines)
    # без Markdown — иначе Telegram режет из‑за * _ `
    plain = text.replace("**", "").replace("__", "").replace("`", "")
    await _send_long(message, plain)


@router.message(Command("podderzhka", "support", "helpme", "поддержка"))
async def cmd_support(message: Message) -> None:
    lang = "ru"
    if message.from_user:
        store.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
        lang = _lang(message.from_user.id, getattr(message.from_user, "language_code", None))
    await message.answer(t("support", lang), parse_mode="Markdown", reply_markup=support_inline(lang))
    # всегда принимаем текст в боте (если есть ADMIN_IDS — уйдёт владельцу)
    if message.from_user:
        _waiting_support.add(message.from_user.id)
        await message.answer(
            t("support_write", lang),
            reply_markup=cancel_support_kb(lang),
        )
    if message.from_user and not admin_ids():
        logger.warning("support: ADMIN_IDS empty — messages cannot be forwarded")


@router.callback_query(F.data == "support:menu")
async def cb_support_menu(query: CallbackQuery) -> None:
    await query.answer()
    lang = _lang(
        query.from_user.id if query.from_user else None,
        getattr(query.from_user, "language_code", None) if query.from_user else None,
    )
    if query.message:
        await query.message.answer(t("support", lang), parse_mode="Markdown", reply_markup=support_inline(lang))


@router.callback_query(F.data == "support:write")
async def cb_support_write(query: CallbackQuery) -> None:
    await query.answer()
    lang = _lang(
        query.from_user.id if query.from_user else None,
        getattr(query.from_user, "language_code", None) if query.from_user else None,
    )
    if query.from_user:
        _waiting_support.add(query.from_user.id)
    if query.message:
        await query.message.answer(
            t("support_write_cb", lang),
            reply_markup=cancel_support_kb(lang),
        )


async def _forward_support_to_admins(message: Message, text: str) -> bool:
    """Переслать обращение всем админам. Возвращает True если хоть кому-то ушло."""
    if not message.from_user or not message.bot:
        return False
    u = message.from_user
    admins = admin_ids()
    if not admins:
        # fallback: если задан SUPPORT_USERNAME — хотя бы скажем открыть чат
        return False

    un = f"@{u.username}" if u.username else "без юзернейма"
    header = (
        f"💬 **Обращение в поддержку**\n"
        f"От: {u.first_name or '—'} ({un})\n"
        f"id: `{u.id}`\n\n"
        f"{text}\n\n"
        f"_Ответьте **реплаем** на это сообщение — ответ уйдёт пользователю._"
    )
    ok = False
    tid = store.save_support_message(u.id, u.username, u.first_name, text)
    for aid in admins:
        try:
            sent = await message.bot.send_message(aid, header, parse_mode="Markdown")
            store.update_support_admin_msg(tid, aid, sent.message_id)
            ok = True
        except Exception as e:
            logger.warning("support notify admin %s: %s", aid, e)
    return ok


@router.message(F.text.in_(set(BUTTON_TO_SPREAD)))
async def btn_spread_legacy(message: Message) -> None:
    """Старые кнопки чата: направляем в приложение."""
    lang = _lang(
        message.from_user.id if message.from_user else None,
        getattr(message.from_user, "language_code", None) if message.from_user else None,
    )
    kb = open_app_inline(lang)
    await message.answer(
        t("open_app_msg", lang),
        reply_markup=kb or main_menu(),
    )


@router.callback_query(F.data.startswith("spread:"))
async def cb_spread(query: CallbackQuery) -> None:
    lang = _lang(
        query.from_user.id if query.from_user else None,
        getattr(query.from_user, "language_code", None) if query.from_user else None,
    )
    await query.answer(t("open_app", lang))
    if query.message:
        kb = open_app_inline(lang)
        if kb:
            await query.message.answer(t("open_app_msg", lang), reply_markup=kb)


async def _send_tip_invoice(message: Message, stars: int, lang: str) -> None:
    stars = int(stars)
    if stars < 1 or stars > 100_000:
        await message.answer(t("thanks_bad_amount", lang))
        return
    title = t("thanks_invoice_title", lang)
    desc = t("thanks_invoice_desc", lang, stars=stars)
    prices = [LabeledPrice(label=title, amount=stars)]
    await message.answer_invoice(
        title=title,
        description=desc[:255],
        payload=f"tip:{stars}",
        currency="XTR",
        prices=prices,
        provider_token="",
    )


@router.callback_query(F.data == "thanks:menu")
async def cb_thanks_menu(query: CallbackQuery) -> None:
    await query.answer()
    lang = _lang(
        query.from_user.id if query.from_user else None,
        getattr(query.from_user, "language_code", None) if query.from_user else None,
    )
    if query.message:
        await query.message.answer(
            t("thanks_title", lang),
            parse_mode="Markdown",
            reply_markup=thanks_inline(lang),
        )


@router.message(Command("spasibo", "thanks", "tip", "donate", "спасибо", "благодарность"))
async def cmd_thanks(message: Message) -> None:
    if message.from_user:
        store.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    lang = _lang(
        message.from_user.id if message.from_user else None,
        getattr(message.from_user, "language_code", None) if message.from_user else None,
    )
    # optional: /tip 25
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip().isdigit():
        await _send_tip_invoice(message, int(parts[1].strip()), lang)
        return
    await message.answer(
        t("thanks_title", lang),
        parse_mode="Markdown",
        reply_markup=thanks_inline(lang),
    )


@router.callback_query(F.data.startswith("tip:"))
async def cb_tip(query: CallbackQuery) -> None:
    lang = _lang(
        query.from_user.id if query.from_user else None,
        getattr(query.from_user, "language_code", None) if query.from_user else None,
    )
    raw = (query.data or "tip:1").split(":", 1)[1]
    if raw == "custom":
        await query.answer()
        if query.from_user:
            _waiting_tip.add(query.from_user.id)
            _waiting_support.discard(query.from_user.id)
        if query.message:
            await query.message.answer(
                t("thanks_ask_amount", lang),
                parse_mode="Markdown",
                reply_markup=cancel_support_kb(lang),
            )
        return
    if not raw.isdigit():
        await query.answer(t("thanks_bad_amount", lang), show_alert=True)
        return
    await query.answer()
    if query.message:
        await _send_tip_invoice(query.message, int(raw), lang)


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(query: CallbackQuery) -> None:
    plan_id = (query.data or "").split(":", 1)[1]
    plan = PLANS.get(plan_id)
    if not plan:
        await query.answer("Тариф не найден", show_alert=True)
        return
    await query.answer()
    prices = [LabeledPrice(label=plan["title"], amount=int(plan["stars"]))]
    await query.message.answer_invoice(
        title=plan["title"],
        description=plan["description"],
        payload=plan["payload"],
        currency="XTR",
        prices=prices,
        provider_token="",
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    plan = plan_by_payload(query.invoice_payload or "")
    if not plan:
        await query.answer(ok=False, error_message="Unknown invoice")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    sp = message.successful_payment
    if not sp or not message.from_user:
        return
    payload = sp.invoice_payload or ""
    plan = plan_by_payload(payload)
    if not plan:
        await message.answer("Payment received.")
        return
    uid = message.from_user.id
    lang = _lang(uid, getattr(message.from_user, "language_code", None))
    store.upsert_user(uid, message.from_user.username, message.from_user.first_name)
    stars = int(sp.total_amount)
    store.record_payment(
        uid, payload, stars, plan["id"], sp.telegram_payment_charge_id or ""
    )

    if plan.get("tip"):
        text = t("thanks_done", lang)
        await message.answer(text, reply_markup=open_app_inline(lang) or main_menu())
        # уведомить владельца
        un = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name or "—"
        for aid in admin_ids():
            try:
                await message.bot.send_message(
                    aid,
                    f"💛 Благодарность: {stars} ⭐ от {un} (id {uid})",
                )
            except Exception:
                pass
        return

    if plan.get("one_shot"):
        store.grant_premium(uid, days=1, plan="deep_once")
        text = (
            "⭐ Спасибо! **Глубокий разбор** открыт на сутки."
            if lang == "ru"
            else "⭐ Thank you! **Deep reading** is open for 24h."
        )
    else:
        store.grant_premium(uid, days=int(plan["days"]), plan=plan["id"])
        text = (
            f"⭐ Спасибо! **Полный доступ** на **{plan['days']} дн.**"
            if lang == "ru"
            else f"⭐ Thank you! **Full access** for **{plan['days']} days.**"
        )
    await message.answer(text, parse_mode="Markdown", reply_markup=main_menu())


@router.message(IsAdminFilter(), F.reply_to_message, F.text)
async def admin_reply_to_support(message: Message) -> None:
    """Админ отвечает реплаем на обращение — пересылаем пользователю."""
    if not message.from_user or not message.text or not message.reply_to_message or not message.bot:
        return
    rt = message.reply_to_message
    ticket = store.find_support_by_admin_message(message.chat.id, rt.message_id)
    if not ticket:
        return
    target = int(ticket["user_id"])
    try:
        await message.bot.send_message(
            target,
            f"💬 **Ответ поддержки**\n\n{message.text}",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        await message.answer("✅ Отправлено пользователю.", reply_markup=main_menu())
    except Exception as e:
        await message.answer(f"Не удалось доставить: {e}")


@router.message(F.text)
async def text_router(message: Message) -> None:
    if not message.from_user or not message.text:
        return
    uid = message.from_user.id
    text = message.text.strip()
    lang = _lang(uid, getattr(message.from_user, "language_code", None))

    # custom tip amount
    if uid in _waiting_tip:
        _waiting_tip.discard(uid)
        raw = text.replace("⭐", "").replace("звёзд", "").replace("звезд", "").replace("stars", "").strip()
        if raw.isdigit():
            await _send_tip_invoice(message, int(raw), lang)
        else:
            await message.answer(t("thanks_bad_amount", lang), reply_markup=thanks_inline(lang))
        return

    # support message to owner
    if uid in _waiting_support:
        _waiting_support.discard(uid)
        if text in BUTTON_TO_SPREAD or text in (
            t("btn_cancel", "ru"),
            t("btn_cancel", "en"),
            t("btn_full", "ru"),
            t("btn_full", "en"),
        ):
            await message.answer(t("cancelled", lang), reply_markup=main_menu())
            return
        ok = await _forward_support_to_admins(message, text)
        if ok:
            await message.answer(t("support_sent", lang), reply_markup=main_menu())
        else:
            await message.answer(t("support_fail", lang), reply_markup=main_menu())
        return

    # waiting birth data
    if uid in _waiting_birth:
        parsed = _parse_birth(text)
        if not parsed:
            await message.answer(
                "Не разобрал формат. Пример:\n`15.06.1990 14:30 Москва`",
                parse_mode="Markdown",
                reply_markup=main_menu(),
            )
            return
        date_s, time_s, place = parsed
        try:
            from bot.astrology import calculate_ascendant, result_to_dict

            result = calculate_ascendant(date_s, time_s, place)
            data = result_to_dict(result)
            data["birth_date"] = date_s
            data["birth_time"] = time_s
            store.save_profile(uid, data, label="Я", make_default=True)
            _waiting_birth.discard(uid)
            await message.answer(
                f"✅ Восходящий знак: **{data['emoji']} {data['sign']}** "
                f"({data['degree_in_sign']}°)\n_{data['place']}_",
                parse_mode="Markdown",
                reply_markup=main_menu(),
            )
            await _run_asc_day(message)
        except Exception as e:
            await message.answer(f"Не удалось рассчитать: {e}", reply_markup=main_menu())
        return

    # free text → подсказка открыть приложение
    kb = open_app_inline(lang)
    await message.answer(
        t("open_app_msg", lang) + "\n/lang · /help · /premium · /support",
        reply_markup=kb or main_menu(),
    )
