"""Бот: Mini App + Premium (Telegram Stars) + уведомления."""
from __future__ import annotations

import logging
import os

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardRemove,
)

from bot import db as store
from bot.keyboards import open_app_inline, premium_inline
from bot.premium import PLANS, plan_by_payload
from bot.texts import WELCOME, NO_APP, PREMIUM_INFO, HOW_MONEY

logger = logging.getLogger(__name__)
router = Router()


def _mini_url() -> str:
    return (os.getenv("MINIAPP_URL") or "").strip()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.from_user:
        store.upsert_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
    await message.answer(WELCOME, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    kb = open_app_inline()
    if kb:
        await message.answer("Нажмите, чтобы открыть приложение 👇", reply_markup=kb)
    else:
        await message.answer(NO_APP, parse_mode="Markdown")

    # deep link premium
    args = (message.text or "").split(maxsplit=1)
    if len(args) > 1 and args[1].strip() in ("premium", "pay", "stars"):
        await cmd_premium(message)


@router.message(Command("app", "open", "menu"))
async def cmd_app(message: Message) -> None:
    kb = open_app_inline()
    if kb:
        await message.answer("✨ Откройте приложение:", reply_markup=kb)
    else:
        await message.answer(NO_APP, parse_mode="Markdown")


@router.message(Command("premium", "stars", "pay"))
async def cmd_premium(message: Message) -> None:
    if message.from_user:
        store.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
        info = store.premium_info(message.from_user.id)
        status = (
            f"\n\n✅ У вас **Premium** до `{info['until'][:10]}`"
            if info["active"]
            else "\n\nСейчас: бесплатный тариф."
        )
    else:
        status = ""
    await message.answer(
        PREMIUM_INFO + status,
        parse_mode="Markdown",
        reply_markup=premium_inline(),
    )


@router.message(Command("money", "withdraw", "вывод"))
async def cmd_money(message: Message) -> None:
    await message.answer(HOW_MONEY, parse_mode="Markdown")


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(query: CallbackQuery) -> None:
    plan_id = (query.data or "").split(":", 1)[1]
    plan = PLANS.get(plan_id)
    if not plan:
        await query.answer("Тариф не найден", show_alert=True)
        return
    await query.answer()
    # Telegram Stars invoice
    prices = [LabeledPrice(label=plan["title"], amount=int(plan["stars"]))]
    await query.message.answer_invoice(
        title=plan["title"],
        description=plan["description"],
        payload=plan["payload"],
        currency="XTR",  # Stars
        prices=prices,
        provider_token="",  # empty for Stars
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
        await message.answer("Оплата получена, но тариф не распознан. Напишите в поддержку.")
        return

    uid = message.from_user.id
    store.upsert_user(uid, message.from_user.username, message.from_user.first_name)
    store.record_payment(
        uid,
        sp.invoice_payload,
        int(sp.total_amount),
        plan["id"],
        sp.telegram_payment_charge_id or "",
    )

    if plan.get("one_shot"):
        # one-shot deep: grant 24h mini-premium flag via short premium
        store.grant_premium(uid, days=1, plan="deep_once")
        text = (
            "⭐ Спасибо! **Глубокий разбор** доступен.\n"
            "Откройте приложение → расклад «Глубокий разбор» (24 часа доступа к premium-функциям)."
        )
    else:
        store.grant_premium(uid, days=int(plan["days"]), plan=plan["id"])
        text = (
            f"⭐ Спасибо! **Premium** активирован на **{plan['days']} дн.**\n"
            "Безлимит ИИ, неделя/месяц, совместимость, журнал, уведомления."
        )

    kb = open_app_inline()
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not message.from_user:
        return
    info = store.premium_info(message.from_user.id)
    used = store.count_ai_today(message.from_user.id)
    if info["active"]:
        await message.answer(
            f"✅ Premium до {info['until'][:16]} (UTC)\nПлан: {info['plan']}",
        )
    else:
        await message.answer(
            f"Бесплатный тариф.\nИИ сегодня: {used}/3\n/premium — открыть тарифы ⭐",
        )


@router.message()
async def fallback(message: Message) -> None:
    kb = open_app_inline()
    if kb:
        await message.answer("Все расклады — в приложении 🌸\n/premium — тарифы ⭐", reply_markup=kb)
    else:
        await message.answer(NO_APP, parse_mode="Markdown")
