#!/usr/bin/env python3
"""Production entry: HTTP Mini App + Telegram bot in one process supervisor."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    port = os.environ.get("PORT", "8080")
    # Auto MINIAPP_URL for common platforms if not set
    if not os.environ.get("MINIAPP_URL"):
        if os.environ.get("FLY_APP_NAME"):
            os.environ["MINIAPP_URL"] = f"https://{os.environ['FLY_APP_NAME']}.fly.dev"
        elif os.environ.get("RENDER_EXTERNAL_URL"):
            os.environ["MINIAPP_URL"] = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
        elif os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
            os.environ["MINIAPP_URL"] = f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(ROOT)

    web = subprocess.Popen(
        [sys.executable, str(ROOT / "serve_miniapp.py"), "--port", str(port), "--host", "0.0.0.0"],
        cwd=str(ROOT),
        env=env,
    )
    bot = subprocess.Popen(
        [sys.executable, str(ROOT / "main.py")],
        cwd=str(ROOT),
        env=env,
    )

    def shutdown(*_args):
        for p in (web, bot):
            try:
                p.send_signal(signal.SIGTERM)
            except Exception:
                pass
        time.sleep(2)
        for p in (web, bot):
            if p.poll() is None:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    while True:
        if web.poll() is not None:
            print("web exited", web.returncode, flush=True)
            shutdown()
        if bot.poll() is not None:
            print("bot exited", bot.returncode, flush=True)
            shutdown()
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
