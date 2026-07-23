"""Клавиатуры бота — русский текст, расклады в чате."""
from __future__ import annotations

import os

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from bot.premium import PLANS


def miniapp_url() -> str:
    return os.getenv("MINIAPP_URL", "").strip()


def main_menu() -> ReplyKeyboardMarkup:
    """Основное меню прямо в чате — работает без приложения."""
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text="☀️ Карта дня"), KeyboardButton(text="🌅 День по восходящему")],
        [KeyboardButton(text="✨ Три карты"), KeyboardButton(text="💗 Любовь")],
        [KeyboardButton(text="🌿 Ситуация"), KeyboardButton(text="🌻 Дело")],
        [KeyboardButton(text="🔮 Да / Нет"), KeyboardButton(text="🌈 Путь")],
        [KeyboardButton(text="🃏 Таро: карта дня"), KeyboardButton(text="🃏 Таро: три карты")],
        [KeyboardButton(text="🃏 Таро: любовь"), KeyboardButton(text="🃏 Таро: путь")],
        [KeyboardButton(text="📅 Неделя"), KeyboardButton(text="🗓️ Месяц")],
        [KeyboardButton(text="⭐ Полный доступ"), KeyboardButton(text="ℹ️ Помощь")],
    ]
    url = miniapp_url()
    if url:
        rows.insert(
            0,
            [
                KeyboardButton(
                    text="✨ Красивое приложение",
                    web_app=WebAppInfo(url=url),
                )
            ],
        )
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите расклад…",
    )


def open_app_inline() -> InlineKeyboardMarkup | None:
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
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Полный доступ",
                    callback_data="buy:premium_30",
                ),
            ],
        ]
    )


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
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_spread(spread_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Ещё раз", callback_data=f"spread:{spread_id}"),
                InlineKeyboardButton(text="☀️ Карта дня", callback_data="spread:day"),
            ]
        ]
    )
