"""Клавиатуры бота — русский текст."""
from __future__ import annotations

import os

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot.premium import PLANS


def miniapp_url() -> str:
    return os.getenv("MINIAPP_URL", "").strip()


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
