"""Клавиатуры бота — только Mini App, без кнопок раскладов в чате."""
from __future__ import annotations

import os

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from bot.admin import support_url
from bot.premium import PLANS


def miniapp_url() -> str:
    return os.getenv("MINIAPP_URL", "").strip()


def main_menu() -> ReplyKeyboardRemove:
    """Скрываем нижнюю клавиатуру — всё в приложении."""
    return ReplyKeyboardRemove(remove_keyboard=True)


def open_app_inline() -> InlineKeyboardMarkup | None:
    """Единственная кнопка в чате: открыть Mini App. Без раскладов."""
    url = miniapp_url()
    if not url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Открыть приложение",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


def support_inline() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    sup = support_url()
    if sup:
        rows.append([InlineKeyboardButton(text="💬 Открыть чат с автором", url=sup)])
    rows.append(
        [InlineKeyboardButton(text="✉️ Написать здесь в боте", callback_data="support:write")]
    )
    url = miniapp_url()
    if url:
        rows.append(
            [InlineKeyboardButton(text="✨ В приложение", web_app=WebAppInfo(url=url))]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def premium_inline() -> InlineKeyboardMarkup:
    rows = []
    for pid, p in PLANS.items():
        mark = "💎" if p.get("badge") else "⭐"
        label = f"{mark} {p['title']} — {p['stars']} зв."
        rows.append([InlineKeyboardButton(text=label, callback_data=f"buy:{pid}")])
    url = miniapp_url()
    if url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✨ Открыть приложение",
                    web_app=WebAppInfo(url=url),
                )
            ]
        )
    sup = support_url()
    if sup:
        rows.append([InlineKeyboardButton(text="💬 Поддержка", url=sup)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_spread(spread_id: str) -> InlineKeyboardMarkup:
    """После редкого расклада в чате — снова в приложение."""
    url = miniapp_url()
    rows: list[list[InlineKeyboardButton]] = []
    if url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✨ Открыть приложение",
                    web_app=WebAppInfo(url=url),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="⭐ Полный доступ", callback_data="buy:premium_30")]])


def cancel_support_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✖️ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
