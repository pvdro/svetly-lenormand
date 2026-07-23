#!/usr/bin/env python3
"""
Production: один процесс
  • static Mini App + API (внутренний HTTP)
  • Telegram webhook (для free-хостинга без постоянного polling)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from aiohttp import ClientSession, web
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonWebApp, WebAppInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot import db as store
from bot.handlers import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

WEBHOOK_PATH = "/telegram/webhook"
INTERNAL_PORT = int(os.environ.get("INTERNAL_API_PORT", "18765"))


def public_base_url() -> str:
    for key in ("MINIAPP_URL", "RENDER_EXTERNAL_URL"):
        v = (os.getenv(key) or "").strip().rstrip("/")
        if v:
            return v
    if os.getenv("FLY_APP_NAME"):
        return f"https://{os.environ['FLY_APP_NAME']}.fly.dev"
    if os.getenv("RAILWAY_PUBLIC_DOMAIN"):
        return f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"
    return ""


def start_internal_api() -> None:
    from serve_miniapp import Handler

    server = ThreadingHTTPServer(("127.0.0.1", INTERNAL_PORT), Handler)
    log.info("Internal API on 127.0.0.1:%s", INTERNAL_PORT)
    server.serve_forever()


async def on_startup(bot: Bot) -> None:
    store.init_db()
    base = public_base_url()
    if not base:
        log.error("MINIAPP_URL / public URL not set")
        return
    os.environ["MINIAPP_URL"] = base
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Приложение", web_app=WebAppInfo(url=base))
    )
    secret = os.getenv("WEBHOOK_SECRET", "").strip() or None
    await bot.set_webhook(
        url=f"{base}{WEBHOOK_PATH}",
        secret_token=secret,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query", "pre_checkout_query"],
    )
    me = await bot.get_me()
    log.info("Bot @%s webhook=%s%s menu=%s", me.username, base, WEBHOOK_PATH, base)


async def on_shutdown(bot: Bot) -> None:
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass


async def proxy_handler(request: web.Request) -> web.Response:
    """Проксируем всё кроме webhook на внутренний API/static."""
    url = f"http://127.0.0.1:{INTERNAL_PORT}{request.path_qs}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    data = await request.read()
    async with ClientSession() as session:
        async with session.request(request.method, url, headers=headers, data=data) as resp:
            body = await resp.read()
            out_headers = {
                k: v
                for k, v in resp.headers.items()
                if k.lower() not in ("transfer-encoding", "content-encoding", "content-length", "connection")
            }
            return web.Response(body=body, status=resp.status, headers=out_headers)


async def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN required")

    base = public_base_url()
    if base:
        os.environ["MINIAPP_URL"] = base

    # internal static+api
    t = threading.Thread(target=start_internal_api, daemon=True)
    t.start()
    await asyncio.sleep(0.4)

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    dp = Dispatcher()
    dp.include_router(router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    secret = os.getenv("WEBHOOK_SECRET", "").strip() or None
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app.router.add_route("*", "/{path_info:.*}", proxy_handler)

    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")
    log.info("Public listen %s:%s base=%s", host, port, base)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
