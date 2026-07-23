"""
Тарифы Premium через Telegram Stars (XTR).

Как владелец получает деньги:
1. Пользователь платит Stars в боте (нативная оплата Telegram).
2. Stars зачисляются на ваш бот/аккаунт (Telegram удерживает комиссию ~30%).
3. Вывод: Fragment.com → Stars/TON → биржа/кошелёк.

Документация: https://core.telegram.org/bots/payments-stars
"""
from __future__ import annotations

from typing import Any

# Бесплатные лимиты в сутки
FREE_AI_READINGS_PER_DAY = 3
FREE_FEATURES = {
    "day",
    "asc_day",
    "three",
    "love",
    "situation",
    "work",
    "yesno",
}

# Только premium (или тратит «разовый» если добавим)
PREMIUM_ONLY = {
    "path",
    "week",
    "month",
    "compat",
    "deep",
}

PLANS: dict[str, dict[str, Any]] = {
    "premium_7": {
        "id": "premium_7",
        "title": "Premium на 7 дней",
        "description": "Безлимит ИИ, неделя/месяц, совместимость, история, уведомления",
        "stars": 50,
        "days": 7,
        "payload": "plan:premium_7",
    },
    "premium_30": {
        "id": "premium_30",
        "title": "Premium на 30 дней",
        "description": "Месяц полного доступа — лучшая цена",
        "stars": 150,
        "days": 30,
        "payload": "plan:premium_30",
        "badge": "выгодно",
    },
    "deep_once": {
        "id": "deep_once",
        "title": "Глубокий разбор (1 раз)",
        "description": "Развёрнутый ИИ-отчёт на 1 расклад без подписки",
        "stars": 25,
        "days": 0,
        "payload": "plan:deep_once",
        "one_shot": True,
    },
}


def plan_by_payload(payload: str) -> dict[str, Any] | None:
    for p in PLANS.values():
        if p["payload"] == payload or payload.startswith(p["payload"]):
            return p
    return None


def feature_allowed(feature: str, *, is_premium: bool, free_ai_left: int) -> dict[str, Any]:
    """Можно ли выполнять фичу."""
    if is_premium:
        return {"ok": True, "reason": "premium"}

    if feature in PREMIUM_ONLY:
        return {
            "ok": False,
            "reason": "premium_required",
            "message": "Эта функция в Premium. Откройте тарифы ⭐",
        }

    if feature in ("ai",) or feature.startswith("ai_"):
        if free_ai_left <= 0:
            return {
                "ok": False,
                "reason": "daily_limit",
                "message": f"Бесплатно {FREE_AI_READINGS_PER_DAY} ИИ-прогноза в день. Premium — безлимит ⭐",
            }
        return {"ok": True, "reason": "free_quota"}

    return {"ok": True, "reason": "free"}
