"""Проверка Telegram WebApp initData."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str | None = None, max_age: int = 86400) -> dict | None:
    """
    Returns user dict {id, username, first_name} or None if invalid.
    In dev mode (ALLOW_INSECURE_WEBAPP=1) accepts user_id query without signature.
    """
    token = (bot_token or os.getenv("BOT_TOKEN") or "").strip()
    if not init_data:
        return None

    # Dev bypass: "dev:12345"
    if init_data.startswith("dev:") and os.getenv("ALLOW_INSECURE_WEBAPP", "1") == "1":
        try:
            uid = int(init_data.split(":", 1)[1])
            return {"id": uid, "username": "dev", "first_name": "Dev"}
        except Exception:
            return None

    if not token:
        return None

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        return None

    auth_date = int(parsed.get("auth_date") or 0)
    if auth_date and time.time() - auth_date > max_age:
        return None

    user_raw = parsed.get("user")
    if not user_raw:
        return None
    user = json.loads(user_raw)
    return {
        "id": int(user["id"]),
        "username": user.get("username"),
        "first_name": user.get("first_name"),
    }
