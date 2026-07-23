"""
Тарифы полного доступа через звёзды Telegram (XTR).
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
    "t_day",
    "t_three",
    "t_love",
}

PREMIUM_ONLY = {
    "path",
    "week",
    "month",
    "compat",
    "deep",
    "t_celtic",
    "t_path",
}

PLANS: dict[str, dict[str, Any]] = {
    "premium_7": {
        "id": "premium_7",
        "title": "Полный доступ на 7 дней",
        "description": "Без ограничения прогнозов, неделя и месяц, совместимость, история, напоминания",
        "stars": 50,
        "days": 7,
        "payload": "plan:premium_7",
    },
    "premium_30": {
        "id": "premium_30",
        "title": "Полный доступ на 30 дней",
        "description": "Месяц полного доступа — выгоднее",
        "stars": 150,
        "days": 30,
        "payload": "plan:premium_30",
        "badge": "выгодно",
    },
    "deep_once": {
        "id": "deep_once",
        "title": "Глубокий разбор (разово)",
        "description": "Развёрнутый разбор на один запрос без длительной подписки",
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
    if is_premium:
        return {"ok": True, "reason": "premium"}

    if feature in PREMIUM_ONLY:
        return {
            "ok": False,
            "reason": "premium_required",
            "message": "Эта возможность в полном доступе. Откройте тарифы ⭐",
        }

    if feature in ("ai",) or feature.startswith("ai_"):
        if free_ai_left <= 0:
            return {
                "ok": False,
                "reason": "daily_limit",
                "message": (
                    f"Бесплатно {FREE_AI_READINGS_PER_DAY} живых прогноза в сутки. "
                    "Полный доступ — без ограничения ⭐"
                ),
            }
        return {"ok": True, "reason": "free_quota"}

    return {"ok": True, "reason": "free"}
