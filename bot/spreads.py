"""Расклады Ленорман и сборка тёплых текстов."""
from __future__ import annotations

from dataclasses import dataclass

from bot.cards import Card, draw, format_card_full, format_card_short


@dataclass(frozen=True)
class Spread:
    id: str
    title: str
    emoji: str
    n_cards: int
    positions: tuple[str, ...]
    blurb: str
    focus: str  # general | love | work


SPREADS: dict[str, Spread] = {
    "day": Spread(
        "day",
        "Карта дня",
        "🌅",
        1,
        ("Послание дня",),
        "Мягкий ориентир на сегодня — без давления, с теплом.",
        "general",
    ),
    "three": Spread(
        "three",
        "Три карты",
        "✨",
        3,
        ("Прошлое / фон", "Настоящее", "Совет / ближайшее"),
        "Классика: откуда пришли → где вы → куда мягко шагнуть.",
        "general",
    ),
    "love": Spread(
        "love",
        "Любовь",
        "💗",
        3,
        ("Вы", "Другой человек / поле", "Динамика между вами"),
        "Бережный взгляд на чувства. Не приговор — зеркало и поддержка.",
        "love",
    ),
    "situation": Spread(
        "situation",
        "Ситуация",
        "🌿",
        3,
        ("Суть", "Что скрыто / влияет", "Как пройти красиво"),
        "Расклад «что происходит на самом деле» — спокойно и по делу.",
        "general",
    ),
    "work": Spread(
        "work",
        "Дело и деньги",
        "🌻",
        3,
        ("Где вы сейчас", "Возможность", "Практический шаг"),
        "Работа, ресурс, признание — в светлом ключе.",
        "work",
    ),
    "path": Spread(
        "path",
        "Путь (5 карт)",
        "🌈",
        5,
        ("Корень", "Сейчас", "Вызов", "Ресурс", "Светлый исход"),
        "Развёрнутая история с опорой и надеждой в финале.",
        "general",
    ),
    "yesno": Spread(
        "yesno",
        "Да / Нет / Совет",
        "🔮",
        1,
        ("Ответ поля",),
        "Не жёсткий вердикт, а наклон: к «да», к «нет» или «ещё рано».",
        "advice",
    ),
    "week": Spread(
        "week",
        "Неделя",
        "📅",
        5,
        ("Пн–Вт", "Ср–Чт", "Пт–Вс", "Главный урок", "Итог недели"),
        "Premium: карта недели — ритм и мягкий фокус на 7 дней.",
        "general",
    ),
    "month": Spread(
        "month",
        "Месяц",
        "🗓️",
        7,
        (
            "Общий тон",
            "Любовь",
            "Дело",
            "Тело/ресурс",
            "Вызов",
            "Поддержка",
            "Куда идём",
        ),
        "Premium: развёрнутый месяц в светлом ключе.",
        "general",
    ),
    "compat": Spread(
        "compat",
        "Совместимость «мы»",
        "💞",
        5,
        ("Вы", "Другой", "Химия", "Трение", "Потенциал"),
        "Premium: бережный взгляд на двоих (ASC/карты).",
        "love",
    ),
    "deep": Spread(
        "deep",
        "Глубокий разбор",
        "🪞",
        7,
        (
            "Кто я сейчас",
            "Тень",
            "Желание",
            "Блок",
            "Ресурс",
            "Шаг",
            "Светлый исход",
        ),
        "Premium / разовый: глубокий ИИ-разбор.",
        "general",
    ),
}


# Карты, склоняющие к «да» / «нет» / «подожди» (упрощённая эвристика для yes/no)
_YES_LEAN = {1, 2, 3, 9, 13, 16, 17, 18, 24, 25, 31, 33, 34}
_NO_LEAN = {6, 8, 10, 21, 23, 36}
# остальные — «смешанно / рано»


def yesno_verdict(card: Card) -> str:
    if card.number in _YES_LEAN:
        return (
            "✅ **Склоняется к «да»**\n"
            "Поле поддерживает движение вперёд — мягко и с открытым сердцем."
        )
    if card.number in _NO_LEAN:
        return (
            "🕊️ **Скорее «не сейчас»**\n"
            "Не отказ навсегда, а пауза. Переформулируйте запрос или подождите ясности."
        )
    return (
        "🌤️ **Смешанный ответ**\n"
        "Есть и свет, и оговорки. Уточните вопрос или сделайте маленький пробный шаг."
    )


def combine_note(cards: list[Card], spread: Spread) -> str:
    """Короткий «склейка»-текст по сочетанию — добрый синтез."""
    names = ", ".join(c.name for c in cards)
    has_sun = any(c.number == 31 for c in cards)
    has_heart = any(c.number == 24 for c in cards)
    has_clouds = any(c.number == 6 for c in cards)
    has_mountain = any(c.number == 21 for c in cards)
    has_key = any(c.number == 33 for c in cards)
    has_stars = any(c.number == 16 for c in cards)

    bits: list[str] = []
    if has_sun or has_stars:
        bits.append("В раскладе есть свет — даже если рядом сложности, исходная нота тёплая.")
    if has_heart:
        bits.append("Сердечная тема активна: важны искренность и бережность к чувствам.")
    if has_clouds:
        bits.append("Пока есть дымка — не торопите финальные выводы, проясняйте.")
    if has_mountain:
        bits.append("Препятствие реально, но проходимо: шаг за шагом, без самокритики.")
    if has_key:
        bits.append("Ключ рядом: решение проще, чем кажется, если отпустить лишний контроль.")
    if not bits:
        bits.append(
            f"Карты ({names}) просят внимательности и доброты к себе. "
            "Вы уже на полпути к пониманию."
        )
    return " ".join(bits)


def run_spread(spread_id: str, seed: int | None = None) -> str:
    spread = SPREADS[spread_id]
    cards = draw(spread.n_cards, seed=seed)

    header = (
        f"{spread.emoji} **{spread.title}**\n"
        f"_{spread.blurb}_\n"
        f"{'─' * 16}\n"
    )

    blocks: list[str] = [header]

    if spread_id == "yesno":
        c = cards[0]
        blocks.append(yesno_verdict(c))
        blocks.append("")
        blocks.append(format_card_full(c, "advice"))
    else:
        for pos, card in zip(spread.positions, cards):
            focus = spread.focus if spread.focus != "advice" else "general"
            blocks.append(f"**{pos}**\n{format_card_full(card, focus)}")
            blocks.append("┄┄┄┄┄┄┄┄")

        if spread.n_cards > 1:
            blocks.append(f"🌸 **Вместе**\n{combine_note(cards, spread)}")

    blocks.append(
        "\n🤍 _Это поддержка и зеркало, не приговор. "
        "Вы всегда вольны выбрать свой следующий шаг._"
    )
    return "\n".join(blocks)


def encyclopedia_list() -> str:
    lines = ["📚 **Колода Ленорман (36)**\n_Нажмите номер карты в меню или выберите ниже интерес._\n"]
    for c in sorted(__import__("bot.cards", fromlist=["DECK"]).DECK, key=lambda x: x.number):
        lines.append(format_card_short(c))
    return "\n".join(lines)
