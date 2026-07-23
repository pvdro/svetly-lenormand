"""Простой календарь транзитов на неделю (Swiss Ephemeris)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import swisseph as swe

PLANETS = [
    (swe.SUN, "Солнце", "☀️"),
    (swe.MOON, "Луна", "🌙"),
    (swe.MERCURY, "Меркурий", "☿️"),
    (swe.VENUS, "Венера", "♀️"),
    (swe.MARS, "Марс", "♂️"),
    (swe.JUPITER, "Юпитер", "♃"),
    (swe.SATURN, "Сатурн", "♄"),
]

SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы",
]


def _sign(lon: float) -> str:
    return SIGNS[int((lon % 360) // 30)]


def week_transits(tz_name: str = "Europe/Moscow") -> dict[str, Any]:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
        tz_name = "UTC"

    now = datetime.now(tz)
    days = []
    for i in range(7):
        d = now + timedelta(days=i)
        # noon local → UT
        local_noon = d.replace(hour=12, minute=0, second=0, microsecond=0)
        utc = local_noon.astimezone(ZoneInfo("UTC"))
        hour = utc.hour + utc.minute / 60.0
        jd = swe.julday(utc.year, utc.month, utc.day, hour)
        bodies = []
        for pid, name, emoji in PLANETS:
            lon, _ = swe.calc_ut(jd, pid)
            lon = float(lon[0])
            bodies.append(
                {
                    "name": name,
                    "emoji": emoji,
                    "sign": _sign(lon),
                    "degree": round(lon % 30, 1),
                }
            )
        moon = next(b for b in bodies if b["name"] == "Луна")
        sun = next(b for b in bodies if b["name"] == "Солнце")
        tip = (
            f"Луна в {moon['sign']} — день больше про эмоции и {moon['sign'].lower()}. "
            f"Солнце в {sun['sign']}."
        )
        days.append(
            {
                "date": d.date().isoformat(),
                "label": d.strftime("%d.%m (%a)"),
                "moon_sign": moon["sign"],
                "sun_sign": sun["sign"],
                "planets": bodies,
                "tip": tip,
            }
        )

    return {
        "timezone": tz_name,
        "generated_at": now.isoformat(),
        "days": days,
        "note": "Общий фон неба (не натал). Для личного дня смотрите ASC + карту.",
    }
