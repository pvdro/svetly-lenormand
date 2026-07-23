"""Владелец: статистика и поддержка."""
from __future__ import annotations

import os
from typing import Any


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def admin_ids() -> set[int]:
    raw = _env("ADMIN_IDS") or _env("OWNER_ID") or _env("ADMIN_ID")
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return int(user_id) in admin_ids()


def support_username() -> str:
    """Личный юзернейм владельца — не для публичных кнопок (только внутреннее)."""
    u = _env("SUPPORT_USERNAME") or _env("OWNER_USERNAME")
    return u.lstrip("@")


def support_via_bot_only() -> bool:
    """По умолчанию писать только через бота, не в личку автору."""
    v = (_env("SUPPORT_VIA_BOT_ONLY") or "1").lower()
    return v not in ("0", "false", "no", "off")


def support_url() -> str | None:
    """
    Публичная ссылка поддержки.
    По умолчанию — deep-link в бота (/podderzhka), не личный профиль.
    """
    if support_via_bot_only():
        return "https://t.me/AstoManiabot?start=podderzhka"
    u = support_username()
    if not u:
        return "https://t.me/AstoManiabot?start=podderzhka"
    return f"https://t.me/{u}"


def format_stats(s: dict[str, Any]) -> str:
    """Красивый текст статистики на русском."""
    top_kinds = s.get("top_kinds") or []
    kind_lines = "\n".join(f"  · {k}: **{n}**" for k, n in top_kinds[:10]) or "  · пока нет"
    top_today = s.get("top_kinds_today") or []
    today_lines = "\n".join(f"  · {k}: **{n}**" for k, n in top_today[:8]) or "  · пока нет"

    return (
        "📊 **Статистика**\n\n"
        f"👥 Пользователей: **{s.get('users_total', 0)}**\n"
        f"  · новых сегодня: **{s.get('users_today', 0)}**\n"
        f"  · новых за 7 дней: **{s.get('users_7d', 0)}**\n"
        f"  · активных сегодня: **{s.get('active_today', 0)}**\n"
        f"  · активных за 7 дней: **{s.get('active_7d', 0)}**\n\n"
        f"🃏 Раскладов всего: **{s.get('readings_total', 0)}**\n"
        f"  · сегодня: **{s.get('readings_today', 0)}**\n"
        f"  · за 7 дней: **{s.get('readings_7d', 0)}**\n"
        f"  · с живым прогнозом: **{s.get('readings_with_ai', 0)}**\n\n"
        f"⭐ Полный доступ сейчас: **{s.get('premium_active', 0)}**\n"
        f"💫 Оплат: **{s.get('payments_count', 0)}** · звёзд: **{s.get('stars_total', 0)}**\n"
        f"  · за 7 дней: **{s.get('payments_7d', 0)}** опл. / **{s.get('stars_7d', 0)}** зв.\n\n"
        f"📈 Расклады сегодня:\n{today_lines}\n\n"
        f"🏆 Популярные (всё время):\n{kind_lines}\n\n"
        f"_Обновлено: {s.get('generated_at', '—')}_"
    )
