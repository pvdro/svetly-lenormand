"""
Расчёт асцендента (Placidus) через Swiss Ephemeris.
Геокодинг — Nominatim (OpenStreetMap), TZ — timezonefinder.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import swisseph as swe
from timezonefinder import TimezoneFinder

SIGNS_RU = [
    ("Овен", "♈", "Aries"),
    ("Телец", "♉", "Taurus"),
    ("Близнецы", "♊", "Gemini"),
    ("Рак", "♋", "Cancer"),
    ("Лев", "♌", "Leo"),
    ("Дева", "♍", "Virgo"),
    ("Весы", "♎", "Libra"),
    ("Скорпион", "♏", "Scorpio"),
    ("Стрелец", "♐", "Sagittarius"),
    ("Козерог", "♑", "Capricorn"),
    ("Водолей", "♒", "Aquarius"),
    ("Рыбы", "♓", "Pisces"),
]

# Мягкие дневные тексты по знаку асцендента (общий тон дня «сквозь ASC»)
ASC_DAY: dict[str, dict[str, str]] = {
    "Овен": {
        "mood": "День инициативы",
        "body": "Асцендент в Овне даёт сегодня импульс «начать». Не обязательно всё геройски — достаточно одного честного шага вперёд. Энергия в голове и действиях: меньше откладывания, больше ясности «я хочу вот это».",
        "focus": "Смелость · старт · прямота",
        "care": "Не выгорайте на первом же рывке. Пауза после действия — тоже сила.",
    },
    "Телец": {
        "mood": "День опоры и тела",
        "body": "Асцендент в Тельце просит замедлиться и почувствовать почву: тело, деньги, еда, уют, то, что можно потрогать. Сегодня хорошо закреплять, а не распыляться.",
        "focus": "Стабильность · ресурс · чувственность",
        "care": "Не путайте упрямство с заботой о себе. Гибкость сохраняет то, что любите.",
    },
    "Близнецы": {
        "mood": "День слов и связей",
        "body": "Асцендент в Близнецах открывает каналы общения: сообщения, идеи, короткие поездки, обучение. Информация идёт потоком — выбирайте, что действительно важно услышать.",
        "focus": "Диалог · любопытство · лёгкость",
        "care": "Не распыляйтесь на десять чатов. Одна глубокая беседа ценнее двадцати поверхностных.",
    },
    "Рак": {
        "mood": "День чувств и дома",
        "body": "Асцендент в Раке усиливает потребность в безопасности и тёплых людях. Эмоции ближе к поверхности — это не слабость, а компас. Дом, семья, «своё гнездо» звучат громче.",
        "focus": "Забота · интуиция · близость",
        "care": "Не берите на себя чужие бури целиком. Можно обнимать и всё равно держать границы.",
    },
    "Лев": {
        "mood": "День сердца и видимости",
        "body": "Асцендент во Льве зовёт быть замеченным — мягко и по-доброму. Творчество, комплимент, смелость показать себя. Сегодня важно не столько «произвести впечатление», сколько светить изнутри.",
        "focus": "Самовыражение · радость · признание",
        "care": "Не кормите эго обидой. Ваш свет не уменьшается, если рядом светят другие.",
    },
    "Дева": {
        "mood": "День порядка и пользы",
        "body": "Асцендент в Деве любит ясность: списки, здоровье, детали, «как сделать лучше». Сегодня хорошо чинить мелочи, которые давно скрипели — в теле, быте, работе.",
        "focus": "Практика · здоровье · точность",
        "care": "Перфекционизм — не цель. Достаточно «достаточно хорошо» и с теплом к себе.",
    },
    "Весы": {
        "mood": "День гармонии и «мы»",
        "body": "Асцендент в Весах тянет к балансу: отношения, эстетика, справедливые договорённости. Сегодня важно не победить, а согласовать. Красота и вежливость — рабочие инструменты.",
        "focus": "Партнёрство · красота · дипломатия",
        "care": "Не растворяйтесь в чужом мнении. Гармония включает и ваш голос.",
    },
    "Скорпион": {
        "mood": "День глубины и правды",
        "body": "Асцендент в Скорпионе не любит поверхностность. Сегодня всплывает то, что под ковром: чувства, мотивации, «кто я на самом деле». Можно отпустить старое — и стать легче.",
        "focus": "Искренность · трансформация · доверие",
        "care": "Интенсивность — дар, если не жечь себя. Дышите, пейте воду, не копайте без опоры.",
    },
    "Стрелец": {
        "mood": "День смысла и простора",
        "body": "Асцендент в Стрельце расширяет горизонт: учёба, путь, честный разговор о «зачем». Хочется воздуха, юмора, большого жеста. Сегодня хорошо планировать дальше, чем «до вечера».",
        "focus": "Свобода · смысл · оптимизм",
        "care": "Не обещайте сгоряча то, что не удержите. Большие слова требуют почвы.",
    },
    "Козерог": {
        "mood": "День структуры и уважения",
        "body": "Асцендент в Козероге поддерживает зрелые шаги: ответственность, границы, долгую цель. Сегодня можно спокойно делать «взрослую» работу без драмы — и гордиться собой за это.",
        "focus": "Дисциплина · статус · опора",
        "care": "Не превращайте день в экзамен. Отдых — часть стратегии, не слабость.",
    },
    "Водолей": {
        "mood": "День свежего взгляда",
        "body": "Асцендент в Водолее включает «а что, если иначе?». Идеи, друзья, сообщество, необычный подход. Сегодня можно выйти из шаблона — мягко, с интересом, без бунта ради бунта.",
        "focus": "Свобода мысли · люди · обновление",
        "care": "Не уходите в холодную отстранённость. Инновации теплее, когда в них есть сердце.",
    },
    "Рыбы": {
        "mood": "День тонкости и потока",
        "body": "Асцендент в Рыбах растворяет жёсткие края: интуиция, творчество, сочувствие, сны. Сегодня лучше чувствовать, чем насиловать график. Музыка, вода, тишина — лекарства.",
        "focus": "Интуиция · творчество · сострадание",
        "care": "Не впитывайте чужую боль без фильтра. Мягкость ≠ отсутствие границ.",
    },
}

_tf = TimezoneFinder()


@dataclass
class GeoPlace:
    name: str
    lat: float
    lon: float
    timezone: str


@dataclass
class SignPos:
    sign: str
    sign_en: str
    emoji: str
    degree_in_sign: float
    absolute_degree: float


@dataclass
class AscendantResult:
    sign: str
    sign_en: str
    emoji: str
    degree_in_sign: float
    absolute_degree: float
    lat: float
    lon: float
    timezone: str
    place: str
    local_datetime: str
    utc_datetime: str
    # Солнце и Луна (натал на момент рождения)
    sun_sign: str = ""
    sun_sign_en: str = ""
    sun_emoji: str = ""
    sun_degree: float = 0.0
    sun_absolute: float = 0.0
    moon_sign: str = ""
    moon_sign_en: str = ""
    moon_emoji: str = ""
    moon_degree: float = 0.0
    moon_absolute: float = 0.0


def _http_get_json(url: str, timeout: float = 12.0) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AstromaniaBot/1.0 (local miniapp; educational)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@lru_cache(maxsize=256)
def geocode_place(query: str) -> GeoPlace:
    q = (query or "").strip()
    if not q:
        raise ValueError("Укажите город или место рождения")
    url = (
        "https://nominatim.openstreetmap.org/search?"
        + urllib.parse.urlencode(
            {"q": q, "format": "json", "limit": 1, "addressdetails": 0}
        )
    )
    data = _http_get_json(url)
    if not isinstance(data, list) or not data:
        raise ValueError(f"Место не найдено: «{q}». Попробуйте «Москва» или «Санкт-Петербург, Россия».")
    item = data[0]
    lat = float(item["lat"])
    lon = float(item["lon"])
    tz = _tf.timezone_at(lat=lat, lng=lon) or "UTC"
    display = item.get("display_name") or q
    # shorter name
    short = display.split(",")[0].strip() if display else q
    return GeoPlace(name=short, lat=lat, lon=lon, timezone=tz)


def calculate_ascendant(
    date_str: str,
    time_str: str,
    place: str,
    *,
    lat: float | None = None,
    lon: float | None = None,
    timezone: str | None = None,
) -> AscendantResult:
    """
    date_str: YYYY-MM-DD
    time_str: HH:MM or HH:MM:SS (local time at birth place)
    place: city name if lat/lon not provided
    """
    try:
        y, m, d = [int(x) for x in date_str.split("-")]
    except Exception as e:
        raise ValueError("Дата в формате ГГГГ-ММ-ДД") from e

    parts = time_str.strip().split(":")
    try:
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
        ss = int(float(parts[2])) if len(parts) > 2 else 0
    except Exception as e:
        raise ValueError("Время в формате ЧЧ:ММ") from e

    if lat is None or lon is None:
        geo = geocode_place(place)
        lat, lon = geo.lat, geo.lon
        tz_name = timezone or geo.timezone
        place_name = geo.name
    else:
        lat, lon = float(lat), float(lon)
        tz_name = timezone or _tf.timezone_at(lat=lat, lng=lon) or "UTC"
        place_name = place.strip() or f"{lat:.2f}, {lon:.2f}"

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
        tz_name = "UTC"

    local_dt = datetime(y, m, d, hh, mm, ss, tzinfo=tz)
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))

    hour_ut = (
        utc_dt.hour
        + utc_dt.minute / 60.0
        + utc_dt.second / 3600.0
    )
    jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour_ut)

    def lon_to_sign(lon: float) -> SignPos:
        abs_deg = float(lon) % 360.0
        idx = int(abs_deg // 30) % 12
        deg = abs_deg - idx * 30
        name, emoji, en = SIGNS_RU[idx]
        return SignPos(name, en, emoji, round(deg, 2), round(abs_deg, 4))

    # Солнце и Луна
    sun_xx, _ = swe.calc_ut(jd, swe.SUN)
    moon_xx, _ = swe.calc_ut(jd, swe.MOON)
    sun = lon_to_sign(sun_xx[0])
    moon = lon_to_sign(moon_xx[0])

    # Placidus houses → ASC
    _cusps, ascmc = swe.houses(jd, lat, lon, b"P")
    asc = lon_to_sign(float(ascmc[0]))

    return AscendantResult(
        sign=asc.sign,
        sign_en=asc.sign_en,
        emoji=asc.emoji,
        degree_in_sign=asc.degree_in_sign,
        absolute_degree=asc.absolute_degree,
        lat=round(lat, 5),
        lon=round(lon, 5),
        timezone=tz_name,
        place=place_name,
        local_datetime=local_dt.isoformat(),
        utc_datetime=utc_dt.isoformat(),
        sun_sign=sun.sign,
        sun_sign_en=sun.sign_en,
        sun_emoji=sun.emoji,
        sun_degree=sun.degree_in_sign,
        sun_absolute=sun.absolute_degree,
        moon_sign=moon.sign,
        moon_sign_en=moon.sign_en,
        moon_emoji=moon.emoji,
        moon_degree=moon.degree_in_sign,
        moon_absolute=moon.absolute_degree,
    )


def day_reading_for_asc(sign: str) -> dict:
    block = ASC_DAY.get(sign) or ASC_DAY["Лев"]
    return {
        "sign": sign,
        "emoji": next((e for n, e, _ in SIGNS_RU if n == sign), "✦"),
        "kind": "asc",
        **block,
    }


def day_reading_for_sun(sign: str) -> dict:
    """Тон дня через солнечный знак (ядро личности / «я»)."""
    block = ASC_DAY.get(sign) or ASC_DAY["Лев"]
    # перефразируем заголовки под Солнце
    mood = (block.get("mood") or "").replace("Асцендент", "Солнце")
    body = (block.get("body") or "").replace("Асцендент", "Солнце")
    # если не заменили (тексты про ASC в знаке) — мягкая обёртка
    if "Асцендент" in (block.get("body") or ""):
        body = block["body"]
    return {
        "sign": sign,
        "emoji": next((e for n, e, _ in SIGNS_RU if n == sign), "☀️"),
        "kind": "sun",
        "mood": f"Солнце · {mood}" if mood else f"Солнце в знаке {sign}",
        "body": (
            f"Ваше Солнце в знаке {sign}. Это ядро «кто я» и источник дневной силы. "
            f"{body}"
        ),
        "focus": block.get("focus") or "",
        "care": block.get("care") or "",
    }


def day_reading_for_moon(sign: str) -> dict:
    """Тон дня через лунный знак (чувства / потребности)."""
    block = ASC_DAY.get(sign) or ASC_DAY["Рак"]
    return {
        "sign": sign,
        "emoji": next((e for n, e, _ in SIGNS_RU if n == sign), "🌙"),
        "kind": "moon",
        "mood": f"Луна · {(block.get('mood') or sign)}",
        "body": (
            f"Ваша Луна в знаке {sign}. Это про эмоции, привычки заботы и то, что питает душу сегодня. "
            f"{block.get('body') or ''}"
        ),
        "focus": block.get("focus") or "",
        "care": block.get("care") or "",
    }


def result_to_dict(r: AscendantResult) -> dict:
    d = asdict(r)
    d["day"] = day_reading_for_asc(r.sign)
    d["sun_day"] = day_reading_for_sun(r.sun_sign) if r.sun_sign else None
    d["moon_day"] = day_reading_for_moon(r.moon_sign) if r.moon_sign else None
    # удобные вложенные блоки
    d["sun"] = {
        "sign": r.sun_sign,
        "sign_en": r.sun_sign_en,
        "emoji": r.sun_emoji,
        "degree_in_sign": r.sun_degree,
        "absolute_degree": r.sun_absolute,
    }
    d["moon"] = {
        "sign": r.moon_sign,
        "sign_en": r.moon_sign_en,
        "emoji": r.moon_emoji,
        "degree_in_sign": r.moon_degree,
        "absolute_degree": r.moon_absolute,
    }
    d["asc"] = {
        "sign": r.sign,
        "sign_en": r.sign_en,
        "emoji": r.emoji,
        "degree_in_sign": r.degree_in_sign,
        "absolute_degree": r.absolute_degree,
    }
    return d
