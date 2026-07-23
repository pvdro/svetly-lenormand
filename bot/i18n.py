"""Русский / English — тексты бота и UI."""
from __future__ import annotations

from typing import Any

LANGS = ("ru", "en")
DEFAULT_LANG = "ru"

# key -> {ru, en}
STRINGS: dict[str, dict[str, str]] = {
    "welcome": {
        "ru": (
            "🌸 **Астромания**\n\n"
            "Привет, **{name}** ✨\n\n"
            "Светлые расклады **Ленорман** и **Таро Райдера–Уэйта**,\n"
            "день по **восходящему знаку**.\n\n"
            "Всё внутри **приложения** — кнопка ниже 👇\n\n"
            "• Ленорман и Таро\n"
            "• День по восходящему знаку\n"
            "• Полный доступ — звёздами Телеграма\n\n"
            "Язык: /lang · помощь: /help"
        ),
        "en": (
            "🌸 **Astromania**\n\n"
            "Hi, **{name}** ✨\n\n"
            "Gentle **Lenormand** and **Rider–Waite Tarot** readings,\n"
            "plus a personal day by **rising sign**.\n\n"
            "Everything lives in the **app** — tap below 👇\n\n"
            "• Lenormand & Tarot\n"
            "• Day by rising sign\n"
            "• Full access with Telegram Stars\n\n"
            "Language: /lang · help: /help"
        ),
    },
    "welcome_caption": {
        "ru": "Астромания · для {name}",
        "en": "Astromania · for {name}",
    },
    "choose_lang": {
        "ru": "🌐 Выберите язык / Choose language",
        "en": "🌐 Choose language / Выберите язык",
    },
    "lang_set": {
        "ru": "✅ Язык: русский",
        "en": "✅ Language: English",
    },
    "open_app": {
        "ru": "✨ Открыть приложение",
        "en": "✨ Open the app",
    },
    "open_app_hint": {
        "ru": "👇",
        "en": "👇",
    },
    "no_app": {
        "ru": "Приложение сейчас не настроено.\nНапишите /podderzhka — свяжемся.",
        "en": "The app is not configured yet.\nMessage /support and we’ll help.",
    },
    "help": {
        "ru": (
            "🤍 **Как пользоваться · Астромания**\n\n"
            "1. Нажмите **«Открыть приложение»** — там все расклады.\n"
            "2. Ленорман, Таро, день по восходящему знаку.\n"
            "3. **Полный доступ** — /dostup (звёзды).\n"
            "4. **Поддержка** — /podderzhka.\n"
            "5. **Язык** — /lang.\n\n"
            "Это поддержка и зеркало, не приговор и не медицина."
        ),
        "en": (
            "🤍 **How to use · Astromania**\n\n"
            "1. Tap **Open the app** — all spreads are there.\n"
            "2. Lenormand, Tarot, day by rising sign.\n"
            "3. **Full access** — /premium (Telegram Stars).\n"
            "4. **Support** — /support.\n"
            "5. **Language** — /lang.\n\n"
            "This is a gentle mirror, not a verdict or medical advice."
        ),
    },
    "support": {
        "ru": (
            "💬 **Поддержка**\n\n"
            "Напишите вопрос или идею — сообщение уйдёт **автору**.\n"
            "Можно открыть чат с автором кнопкой ниже.\n\n"
            "Отмена — «✖️ Отмена»."
        ),
        "en": (
            "💬 **Support**\n\n"
            "Send a question or idea — it goes to the **author**.\n"
            "Or open a chat with the author via the button below.\n\n"
            "Cancel — «✖️ Cancel»."
        ),
    },
    "support_write": {
        "ru": "Напишите сообщение — я перешлю автору.",
        "en": "Type your message — I’ll forward it to the author.",
    },
    "support_write_cb": {
        "ru": "Напишите сообщение для автора 👇\n(или «✖️ Отмена»)",
        "en": "Write a message for the author 👇\n(or «✖️ Cancel»)",
    },
    "support_sent": {
        "ru": "✅ Сообщение отправлено автору. Ответ придёт сюда в бот.",
        "en": "✅ Message sent to the author. The reply will arrive here.",
    },
    "support_fail": {
        "ru": "Пока не удалось переслать (не настроен ADMIN_IDS).",
        "en": "Couldn’t forward yet (ADMIN_IDS is not set).",
    },
    "premium": {
        "ru": (
            "⭐ **Полный доступ**\n\n"
            "Оплата **звёздами Телеграма** — прямо в чате.\n\n"
            "**Бесплатно:**\n"
            "• карта дня\n"
            "• обычные расклады\n"
            "• **3 живых прогноза в сутки**\n\n"
            "**Полный доступ:**\n"
            "• без ограничения по прогнозам\n"
            "• неделя, месяц, путь, глубокий разбор\n"
            "• история и напоминания"
        ),
        "en": (
            "⭐ **Full access**\n\n"
            "Pay with **Telegram Stars** — right in the chat.\n\n"
            "**Free:**\n"
            "• card of the day\n"
            "• regular spreads\n"
            "• **3 live readings per day**\n\n"
            "**Full access:**\n"
            "• unlimited live readings\n"
            "• week, month, path, deep reading\n"
            "• history & reminders"
        ),
    },
    "premium_active": {
        "ru": "\n\n✅ У вас **полный доступ** до `{until}`",
        "en": "\n\n✅ You have **full access** until `{until}`",
    },
    "premium_free": {
        "ru": "\n\nСейчас: бесплатный режим.",
        "en": "\n\nCurrently: free mode.",
    },
    "status_prem": {
        "ru": "✅ Полный доступ до {until}",
        "en": "✅ Full access until {until}",
    },
    "status_free": {
        "ru": "Бесплатный режим.\nЖивых прогнозов сегодня: {used}/3\n/dostup — тарифы ⭐",
        "en": "Free mode.\nLive readings today: {used}/3\n/premium — plans ⭐",
    },
    "cancelled": {
        "ru": "Отменено.",
        "en": "Cancelled.",
    },
    "app_below": {
        "ru": "Приложение 👇",
        "en": "App 👇",
    },
    "open_app_msg": {
        "ru": "Откройте приложение 👇",
        "en": "Open the app 👇",
    },
    "btn_support_chat": {
        "ru": "💬 Открыть чат с автором",
        "en": "💬 Message the author",
    },
    "btn_support_here": {
        "ru": "✉️ Написать здесь в боте",
        "en": "✉️ Write here in the bot",
    },
    "btn_to_app": {
        "ru": "✨ В приложение",
        "en": "✨ To the app",
    },
    "btn_support": {
        "ru": "💬 Поддержка",
        "en": "💬 Support",
    },
    "btn_cancel": {
        "ru": "✖️ Отмена",
        "en": "✖️ Cancel",
    },
    "btn_full": {
        "ru": "⭐ Полный доступ",
        "en": "⭐ Full access",
    },
    "lang_ru": {
        "ru": "🇷🇺 Русский",
        "en": "🇷🇺 Русский",
    },
    "lang_en": {
        "ru": "🇬🇧 English",
        "en": "🇬🇧 English",
    },
    "ask_birth": {
        "ru": (
            "🌅 **День по восходящему знаку**\n\n"
            "Лучше открыть **приложение**.\n\n"
            "Или пришлите: `дата время город`\n"
            "Например: `15.06.1990 14:30 Москва`"
        ),
        "en": (
            "🌅 **Day by rising sign**\n\n"
            "Best to open the **app**.\n\n"
            "Or send: `date time city`\n"
            "Example: `15.06.1990 14:30 London`"
        ),
    },
    "fallback_name": {
        "ru": "друг",
        "en": "friend",
    },
    "llm_lang_note": {
        "ru": "Пиши только по-русски, без англицизмов. Тон светлый и бережный.",
        "en": "Write only in English, warm and gentle. No scare tactics.",
    },
}


def normalize_lang(code: str | None) -> str:
    if not code:
        return DEFAULT_LANG
    c = code.strip().lower()
    if c.startswith("ru") or c in ("uk", "be", "kk"):
        return "ru"
    if c.startswith("en"):
        return "en"
    if c in LANGS:
        return c
    return DEFAULT_LANG


def t(key: str, lang: str | None = None, **kwargs: Any) -> str:
    lang = normalize_lang(lang or DEFAULT_LANG)
    block = STRINGS.get(key) or {}
    text = block.get(lang) or block.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def system_prompt(lang: str) -> str:
    lang = normalize_lang(lang)
    if lang == "en":
        return (
            "You are a gentle guide for Lenormand, Rider–Waite Tarot, and rising-sign astrology. "
            "Write only in English, warm and calm, without fear-mongering. "
            "No medical, legal, or financial guarantees. "
            "No death, disease, or disaster predictions. "
            "Offer support and reflection: tendencies, soft questions, kind advice. "
            "Length: 2–4 short paragraphs. Emojis sparingly."
        )
    return (
        "Ты — мягкий, добрый проводник по картам Ленорман, Таро Райдера–Уэйта и астрологии. "
        "Пиши только по-русски, тепло, спокойно, без эзотерического пафоса и без запугивания. "
        "Не используй английские слова и англицизмы. "
        "Говори «восходящий знак», «живой прогноз», «полный доступ». "
        "Не давай медицинских, юридических и финансовых гарантий. "
        "Не предсказывай смерть, болезни, катастрофы. "
        "Формулируй как поддержку и зеркало. "
        "Объём: 2–4 коротких абзаца. Эмодзи — умеренно."
    )
