#!/usr/bin/env python3
"""Бот + menu button Mini App + утренние уведомления Premium."""
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
        menu_button=MenuButtonWebApp(text="Приложение", web_app=WebAppInfo(url=url))
    )
    logging.getLogger("lenormand").info("Menu → %s", url)


async def notify_loop(bot) -> None:
    """Раз в 15 минут: Premium с notify=1 получают утреннее сообщение."""
    log = logging.getLogger("notify")
    sent_today: set[tuple[int, str]] = set()
    while True:
        try:
            from zoneinfo import ZoneInfo

            for u in store.list_notify_users():
                if not store.is_premium(u["user_id"]):
                    continue
                tz_name = u.get("timezone") or "Europe/Moscow"
                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    tz = ZoneInfo("Europe/Moscow")
                now = datetime.now(tz)
                day = now.date().isoformat()
                key = (int(u["user_id"]), day)
                if key in sent_today:
                    continue
                hour = int(u.get("notify_hour") or 9)
                if now.hour != hour:
                    continue
                # only first 15 min of the hour
                if now.minute > 20:
                    continue
                try:
                    from bot.keyboards import open_app_inline

                    await bot.send_message(
                        u["user_id"],
                        "🌅 Доброе утро! Ваш день в **Светлом Ленормане** ждёт — карта и восходящий знак.\nОткройте приложение ✨",
                        parse_mode="Markdown",
                        reply_markup=open_app_inline(),
                    )
                    sent_today.add(key)
                    log.info("notified %s", u["user_id"])
                except Exception as e:
                    log.warning("notify fail %s: %s", u["user_id"], e)
            # prune old
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
    await setup_menu_button(bot)
    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(notify_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
