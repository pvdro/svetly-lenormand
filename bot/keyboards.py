"""Клавиатуры бота — Mini App + язык."""
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

from bot.i18n import t
from bot.premium import PLANS, TIP_PRESETS


def miniapp_url() -> str:
    return os.getenv("MINIAPP_URL", "").strip()


def main_menu() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove(remove_keyboard=True)


def language_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("lang_ru", "ru"), callback_data="lang:ru"),
                InlineKeyboardButton(text=t("lang_en", "en"), callback_data="lang:en"),
            ]
        ]
    )


def _app_url(lang: str = "ru") -> str:
    url = miniapp_url()
    if not url:
        return ""
    if "lang=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}lang={lang}"


def open_app_button(lang: str = "ru", label: str | None = None) -> InlineKeyboardButton | None:
    """Одна кнопка Open (web_app) — как у Арканума."""
    app_url = _app_url(lang)
    if not app_url:
        return None
    return InlineKeyboardButton(
        text=label or t("open_app", lang),
        web_app=WebAppInfo(url=app_url),
    )


def open_app_only(lang: str = "ru") -> InlineKeyboardMarkup | None:
    """Только Open — для короткого welcome / списка чатов."""
    btn = open_app_button(lang)
    if not btn:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


def open_app_inline(lang: str = "ru") -> InlineKeyboardMarkup | None:
    """Open + язык + доп. действия (после /start)."""
    rows: list[list[InlineKeyboardButton]] = []
    btn = open_app_button(lang)
    if btn:
        rows.append([btn])
    rows.append(
        [
            InlineKeyboardButton(text="🇷🇺", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇬🇧", callback_data="lang:en"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text=t("btn_full", lang), callback_data="buy:premium_30"),
            InlineKeyboardButton(text=t("btn_thanks", lang), callback_data="thanks:menu"),
        ]
    )
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_inline(lang: str = "ru") -> InlineKeyboardMarkup:
    """Поддержка только через бота — без ссылки в личный профиль."""
    from bot.admin import admin_ids

    rows: list[list[InlineKeyboardButton]] = []
    # писать здесь в боте (пересылка владельцу)
    if admin_ids():
        rows.append(
            [InlineKeyboardButton(text=t("btn_support_here", lang), callback_data="support:write")]
        )
    else:
        # если ADMIN_IDS ещё нет — хотя бы команда
        rows.append(
            [InlineKeyboardButton(text=t("btn_support_here", lang), callback_data="support:write")]
        )
    url = miniapp_url()
    if url:
        sep = "&" if "?" in url else "?"
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("btn_to_app", lang),
                    web_app=WebAppInfo(url=f"{url}{sep}lang={lang}"),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def premium_inline(lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    for pid, p in PLANS.items():
        mark = "💎" if p.get("badge") else "⭐"
        if lang == "en":
            titles = {
                "premium_7": "Full access · 7 days",
                "premium_30": "Full access · 30 days",
                "deep_once": "Deep reading (once)",
            }
            title = titles.get(pid, p["title"])
        else:
            title = p["title"]
        label = f"{mark} {title} — {p['stars']} ⭐"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"buy:{pid}")])
    url = miniapp_url()
    if url:
        sep = "&" if "?" in url else "?"
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("open_app", lang),
                    web_app=WebAppInfo(url=f"{url}{sep}lang={lang}"),
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=t("btn_support", lang), callback_data="support:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_spread(spread_id: str, lang: str = "ru") -> InlineKeyboardMarkup:
    url = miniapp_url()
    rows: list[list[InlineKeyboardButton]] = []
    if url:
        sep = "&" if "?" in url else "?"
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("open_app", lang),
                    web_app=WebAppInfo(url=f"{url}{sep}lang={lang}"),
                )
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=rows
        or [[InlineKeyboardButton(text=t("btn_full", lang), callback_data="buy:premium_30")]]
    )


def cancel_support_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_cancel", lang))]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def thanks_inline(lang: str = "ru") -> InlineKeyboardMarkup:
    """Быстрые суммы + своё число звёзд."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for n in TIP_PRESETS:
        row.append(InlineKeyboardButton(text=f"⭐ {n}", callback_data=f"tip:{n}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton(text=t("thanks_custom", lang), callback_data="tip:custom")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
