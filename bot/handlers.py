"""Бот: расклады в чате + полный доступ (звёзды). Приложение — опционально."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)


from bot import db as store
from bot.admin import admin_ids, format_stats, is_admin, support_url
from bot.cards import DECK, draw
from bot.keyboards import (
    after_spread,
    cancel_support_kb,
    main_menu,
    open_app_inline,
    premium_inline,
    support_inline,
)
from bot.llm import build_asc_day_prompt, build_spread_prompt, chat, fallback_spread_text
from bot.premium import FREE_AI_READINGS_PER_DAY, PLANS, feature_allowed, plan_by_payload
from bot.spreads import SPREADS
from bot.tarot import TAROT_SPREADS, draw_tarot, tarot_to_dict
from bot.texts import ASK_BIRTH, HELP, HOW_MONEY, NO_APP, PREMIUM_INFO, SUPPORT, WELCOME


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

    used = store.count_ai_today(uid)
    left = 999 if prem else max(0, FREE_AI_READINGS_PER_DAY - used)
    agate = feature_allowed("ai", is_premium=prem, free_ai_left=left)

    ai_text = None
    if agate["ok"]:
        system = "tarot" if is_tarot else "lenormand"
        prompt = build_spread_prompt(
            spread_title=spread_title,
            spread_blurb=spread_blurb + (f" Система: Таро Райдера–Уэйта." if is_tarot else " Система: Ленорман."),
            cards=cards_d,
            positions=positions,
            question=question,
            extra="Пиши только по-русски, без англицизмов. Тон светлый и бережный.",
        )
        try:
            ai_text, provider, model = chat(prompt)
            if not prem:
                store.inc_ai_today(uid)
            lines.append(f"\n✨ **Живой прогноз**\n{ai_text}")
        except Exception as e:
            ai_text = fallback_spread_text(cards_d, spread_title)
            lines.append(f"\n✨ **Прогноз**\n{ai_text}\n\n_(Краткий режим: {e})_")
    else:
        lines.append(f"\n_{agate['message']}_")
        ai_text = "\n".join(lines)

    text = "\n".join(lines)
    store.save_reading(
        uid,
        spread_id,
        spread_title,
        question,
        cards_d,
        ai_text or text,
        {"system": "tarot" if is_tarot else "lenormand"},
        day_key=store.today_key() if spread_id in ("day", "t_day") else store.today_key(),
    )
    await _send_long(message, text, parse_mode="Markdown", reply_markup=after_spread(spread_id))


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
        await message.answer(ASK_BIRTH, parse_mode="Markdown", reply_markup=main_menu())
        return

    existing = store.get_day_reading(uid, "asc_day")
    if existing and existing.get("ai_text"):
        await _send_long(
            message,
            f"🌅 **День по восходящему знаку** (уже на сегодня)\n\n{existing['ai_text']}",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        return

    await message.answer("🕊️ Считаю день по восходящему знаку…")
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
    used = store.count_ai_today(uid)
    left = 999 if prem else max(0, FREE_AI_READINGS_PER_DAY - used)
    agate = feature_allowed("ai", is_premium=prem, free_ai_left=left)

    header = (
        f"🌅 **День по восходящему знаку · {prof.get('emoji', '')} {prof['sign']}**\n"
        f"_{prof.get('degree_in_sign', '')}° · {prof.get('place', '')}_\n\n"
        f"Карта: {card.emoji} **{card.number}. {card.name}**\n_{card.keywords}_\n{card.general}\n"
    )
    if agate["ok"]:
        try:
            ai_text, _, _ = chat(prompt)
            if not prem:
                store.inc_ai_today(uid)
            text = header + f"\n✨ **Живой прогноз**\n{ai_text}"
        except Exception as e:
            text = header + f"\n✨ **Прогноз**\n{fallback_spread_text(cards_d, 'День')}\n\n_({e})_"
    else:
        text = header + f"\n_{agate['message']}_"

    store.save_reading(uid, "asc_day", f"День · {prof['sign']}", None, cards_d, text, {"profile": prof["sign"]})
    await _send_long(message, text, parse_mode="Markdown", reply_markup=main_menu())


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.from_user:
        store.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    # убираем старую нижнюю клавиатуру раскладов
    await message.answer(WELCOME, parse_mode="Markdown", reply_markup=main_menu())
    app_kb = open_app_inline()
    if app_kb:
        await message.answer("👇", reply_markup=app_kb)
    else:
        await message.answer(NO_APP)
    args = (message.text or "").split(maxsplit=1)
    if len(args) > 1:
        payload = args[1].strip().lower()
        if payload in ("premium", "pay", "stars", "dostup", "доступ"):
            await cmd_premium(message)
        elif payload in ("podderzhka", "support", "help", "помощь", "поддержка"):
            await cmd_support(message)


@router.message(Command("app", "open", "menu", "приложение"))
async def cmd_app(message: Message) -> None:
    kb = open_app_inline()
    if kb:
        await message.answer("Откройте приложение 👇", reply_markup=kb)
    else:
        await message.answer(NO_APP, reply_markup=main_menu())


@router.message(Command("help", "помощь"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP, parse_mode="Markdown", reply_markup=open_app_inline() or main_menu())


@router.message(Command("premium", "stars", "pay", "dostup", "доступ"))
async def cmd_premium(message: Message) -> None:
    if message.from_user:
        store.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
        info = store.premium_info(message.from_user.id)
        status = (
            f"\n\n✅ У вас **полный доступ** до `{info['until'][:10]}`"
            if info["active"]
            else "\n\nСейчас: бесплатный режим."
        )
    else:
        status = ""
    await message.answer(PREMIUM_INFO + status, parse_mode="Markdown", reply_markup=premium_inline())


@router.message(Command("money", "withdraw", "вывод"))
async def cmd_money(message: Message) -> None:
    await message.answer(HOW_MONEY, parse_mode="Markdown")


@router.message(Command("status", "статус"))
async def cmd_status(message: Message) -> None:
    if not message.from_user:
        return
    info = store.premium_info(message.from_user.id)
    used = store.count_ai_today(message.from_user.id)
    if info["active"]:
        await message.answer(
            f"✅ Полный доступ до {info['until'][:10]}",
            reply_markup=open_app_inline(),
        )
    else:
        await message.answer(
            f"Бесплатный режим.\nЖивых прогнозов сегодня: {used}/3\n/dostup — тарифы ⭐",
            reply_markup=open_app_inline(),
        )


@router.message(F.text == "✖️ Отмена")
async def btn_cancel(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    _waiting_birth.discard(uid)
    _waiting_support.discard(uid)
    await message.answer("Отменено.", reply_markup=main_menu())
    kb = open_app_inline()
    if kb:
        await message.answer("Приложение 👇", reply_markup=kb)


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
    if message.from_user:
        store.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(SUPPORT, parse_mode="Markdown", reply_markup=support_inline())
    # если админы настроены — принимаем текст здесь; иначе только ссылка на автора
    if message.from_user and admin_ids():
        _waiting_support.add(message.from_user.id)
        await message.answer(
            "Напишите сообщение — я перешлю автору.",
            reply_markup=cancel_support_kb(),
        )
    elif not support_url():
        await message.answer(
            "Поддержка пока не настроена (нет SUPPORT_USERNAME / ADMIN_IDS).",
            reply_markup=main_menu(),
        )


@router.callback_query(F.data == "support:menu")
async def cb_support_menu(query: CallbackQuery) -> None:
    await query.answer()
    if query.message:
        await query.message.answer(SUPPORT, parse_mode="Markdown", reply_markup=support_inline())


@router.callback_query(F.data == "support:write")
async def cb_support_write(query: CallbackQuery) -> None:
    await query.answer()
    if query.from_user:
        _waiting_support.add(query.from_user.id)
    if query.message:
        await query.message.answer(
            "Напишите сообщение для автора 👇\n(или «✖️ Отмена»)",
            reply_markup=cancel_support_kb(),
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
    kb = open_app_inline()
    await message.answer(
        "Расклады теперь **в приложении** ✨\nНажмите кнопку ниже.",
        parse_mode="Markdown",
        reply_markup=kb or main_menu(),
    )


@router.callback_query(F.data.startswith("spread:"))
async def cb_spread(query: CallbackQuery) -> None:
    await query.answer("Откройте приложение")
    if query.message:
        kb = open_app_inline()
        if kb:
            await query.message.answer("Расклады в приложении 👇", reply_markup=kb)


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
        await query.answer(ok=False, error_message="Неизвестный тариф")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    sp = message.successful_payment
    if not sp or not message.from_user:
        return
    plan = plan_by_payload(sp.invoice_payload)
    if not plan:
        await message.answer("Оплата получена, но тариф не распознан.")
        return
    uid = message.from_user.id
    store.upsert_user(uid, message.from_user.username, message.from_user.first_name)
    store.record_payment(uid, sp.invoice_payload, int(sp.total_amount), plan["id"], sp.telegram_payment_charge_id or "")
    if plan.get("one_shot"):
        store.grant_premium(uid, days=1, plan="deep_once")
        text = "⭐ Спасибо! **Глубокий разбор** открыт на сутки. Выберите расклад «Путь» или «Месяц»."
    else:
        store.grant_premium(uid, days=int(plan["days"]), plan=plan["id"])
        text = f"⭐ Спасибо! **Полный доступ** на **{plan['days']} дн.**"
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

    # support message to owner
    if uid in _waiting_support:
        _waiting_support.discard(uid)
        if text in BUTTON_TO_SPREAD or text in (
            "☀️ Карта дня",
            "🌅 День по восходящему",
            "⭐ Полный доступ",
            "ℹ️ Помощь",
            "💬 Поддержка",
            "✖️ Отмена",
            "✨ Красивое приложение",
        ):
            await message.answer("Отменено.", reply_markup=main_menu())
            return
        ok = await _forward_support_to_admins(message, text)
        if ok:
            await message.answer(
                "✅ Сообщение отправлено автору. Ответ придёт сюда в бот.",
                reply_markup=main_menu(),
            )
        else:
            url = support_url()
            extra = f"\nИли напишите напрямую: {url}" if url else ""
            await message.answer(
                "Пока не удалось переслать (не настроен ADMIN_IDS)." + extra,
                reply_markup=main_menu(),
            )
            if url:
                await message.answer("Кнопка связи:", reply_markup=support_inline())
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

    # free text → подсказка открыть приложение (кроме режима поддержки/даты)
    if len(text) > 2 and not text.startswith("/"):
        kb = open_app_inline()
        await message.answer(
            "Расклады — в **приложении** ✨\n"
            "Команды: /dostup · /podderzhka · /help",
            parse_mode="Markdown",
            reply_markup=kb or main_menu(),
        )
        return

    kb = open_app_inline()
    await message.answer(
        "Откройте приложение 👇",
        reply_markup=kb or main_menu(),
    )
