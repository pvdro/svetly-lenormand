#!/usr/bin/env python3
"""Бот + menu button Mini App + утренние уведомления."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from bot import db as store  # noqa: E402


async def setup_menu_button(bot) -> None:
    from aiogram.types import MenuButtonWebApp, MenuButtonDefault, WebAppInfo

    url = os.getenv("MINIAPP_URL", "").strip()
    if not url:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
        return
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="App / Приложение", web_app=WebAppInfo(url=url))
    )
    logging.getLogger("lenormand").info("Menu → %s", url)
    await bot.delete_webhook(drop_pending_updates=False)


async def setup_bot_profile(bot) -> None:
    """Кликбейтные описания RU/EN + команды."""
    log = logging.getLogger("lenormand")
    try:
        await bot.set_my_description(
            description=(
                "✨ Астромания — светлые расклады без запугивания\n\n"
                "• Карта дня (Ленорман / Таро Райдера–Уэйта)\n"
                "• Расклады: любовь, ситуация, путь, «да/нет»\n"
                "• День по восходящему знаку\n"
                "• Красивое приложение внутри Telegram\n"
                "• Живой тёплый прогноз (лимит бесплатно)\n\n"
                "Не приговор — зеркало и поддержка. RU / EN.\n"
                "Сказать спасибо звёздами: /spasibo 💛"
            ),
            language_code="ru",
        )
        await bot.set_my_short_description(
            short_description="Карта дня и Таро Райдера–Уэйта без страшилок. Любовь, «да/нет», ASC ✨",
            language_code="ru",
        )
        await bot.set_my_description(
            description=(
                "✨ Astromania — soft Tarot & Lenormand, no scare tactics\n\n"
                "• Daily card (Lenormand / Rider–Waite)\n"
                "• Love, path, yes/no, situation spreads\n"
                "• Personal day by rising sign\n"
                "• Beautiful Mini App inside Telegram\n"
                "• Warm live reading (free daily limit)\n\n"
                "Not a verdict — a gentle mirror. RU / EN.\n"
                "Tip the author: /thanks 💛"
            ),
            language_code="en",
        )
        await bot.set_my_short_description(
            short_description="Soft Tarot & Lenormand. Daily card. No doom. Open free ✨",
            language_code="en",
        )
        from aiogram.types import BotCommand

        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Открыть Астроманию"),
                BotCommand(command="lang", description="Язык / Language"),
                BotCommand(command="help", description="Как пользоваться"),
                BotCommand(command="dostup", description="Полный доступ"),
                BotCommand(command="spasibo", description="Спасибо автору (звёзды)"),
                BotCommand(command="invite", description="Пригласить друга (+прогноз)"),
                BotCommand(command="notify", description="Утренние напоминания"),
                BotCommand(command="podderzhka", description="Поддержка"),
                BotCommand(command="stats", description="Статистика"),
            ],
            language_code="ru",
        )
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Open Astromania"),
                BotCommand(command="lang", description="Language"),
                BotCommand(command="help", description="How to use"),
                BotCommand(command="premium", description="Full access"),
                BotCommand(command="thanks", description="Thank the author"),
                BotCommand(command="invite", description="Invite a friend"),
                BotCommand(command="notify", description="Morning reminders"),
                BotCommand(command="support", description="Support"),
            ],
            language_code="en",
        )
        log.info("Bot profile texts/commands set")
    except Exception as e:
        log.warning("setup_bot_profile: %s", e)


async def notify_loop(bot) -> None:
    """Утренние напоминания: все с notify=1 (не только premium)."""
    log = logging.getLogger("notify")
    sent_today: set[tuple[int, str]] = set()
    while True:
        try:
            from zoneinfo import ZoneInfo

            from bot.i18n import t
            from bot.keyboards import open_app_inline

            for u in store.list_notify_users():
                uid = int(u["user_id"])
                tz_name = u.get("timezone") or "Europe/Moscow"
                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    tz = ZoneInfo("Europe/Moscow")
                now = datetime.now(tz)
                day = now.date().isoformat()
                key = (uid, day)
                if key in sent_today:
                    continue
                hour = int(u.get("notify_hour") or 9)
                if now.hour != hour or now.minute > 20:
                    continue
                try:
                    lang = store.get_user_lang(uid) or "ru"
                    prem = store.is_premium(uid)
                    if lang == "en":
                        text = (
                            "🌅 Good morning! Your day in Astromania is ready — "
                            "card of the day or rising-sign day 👇"
                            + (" ⭐" if prem else "")
                        )
                    else:
                        text = (
                            "🌅 Доброе утро! Ваш день в Астромании — "
                            "карта дня или день по восходящему знаку 👇"
                            + (" ⭐" if prem else "")
                        )
                    await bot.send_message(
                        uid,
                        text,
                        reply_markup=open_app_inline(lang or "ru"),
                    )
                    sent_today.add(key)
                    log.info("notified %s", uid)
                except Exception as e:
                    log.warning("notify fail %s: %s", uid, e)
            if len(sent_today) > 5000:
                sent_today.clear()
        except Exception as e:
            log.exception("notify loop: %s", e)
        await asyncio.sleep(60 * 15)


async def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        print("Нет BOT_TOKEN в .env")
        sys.exit(1)

    store.init_db()

    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from bot.handlers import router

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("lenormand")

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    dp = Dispatcher()
    dp.include_router(router)

    me = await bot.get_me()
    log.info("Bot @%s", me.username)
    from bot.admin import admin_ids, support_username

    log.info("ADMIN_IDS=%s SUPPORT=@%s", admin_ids() or "{}", support_username() or "-")
    await setup_menu_button(bot)
    await setup_bot_profile(bot)
    # сброс webhook + пауза: меньше Conflict при rolling-deploy
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2.5)
    log.info("Starting long polling…")

    for aid in admin_ids():
        try:
            await bot.send_message(
                aid,
                f"✅ Бот онлайн (@{me.username})\n"
                f"Админ id: {aid}\n"
                f"/stats · /invite · /spasibo · /notify",
            )
        except Exception as e:
            log.warning("startup notify admin %s: %s", aid, e)

    asyncio.create_task(notify_loop(bot))
    # handle_signals: корректное завершение; allowed_updates — меньше шума
    await dp.start_polling(
        bot,
        allowed_updates=["message", "callback_query", "pre_checkout_query"],
        handle_signals=False,  # start.py шлёт SIGTERM самому процессу
        close_bot_session=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
