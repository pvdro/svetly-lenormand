#!/usr/bin/env python3
"""Регресс-проверка данных Mini App и модулей бота (без сети)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def fail(msg: str) -> None:
    print("FAIL:", msg)
    raise SystemExit(1)


def main() -> None:
    data_js = (ROOT / "miniapp/js/data.js").read_text(encoding="utf-8")
    raw = data_js.split("=", 1)[1].strip().rstrip(";")
    data = json.loads(raw)

    assert len(data["deck"]) == 36, len(data["deck"])
    assert len(data["tarot"]) == 78, len(data["tarot"])
    assert data["spreads"], "no spreads"

    for s in data["spreads"]:
        assert s.get("id"), s
        assert s.get("n") is not None, s
        assert s.get("positions"), s
        assert s.get("title"), s
        if s["id"].startswith("t_"):
            assert s.get("system") == "tarot", s

    # required UI files
    for p in (
        "miniapp/index.html",
        "miniapp/js/app.js",
        "miniapp/js/config.js",
        "miniapp/css/app.css",
        "docs/index.html",
        "docs/js/app.js",
        "docs/js/data.js",
    ):
        if not (ROOT / p).exists():
            fail(f"missing {p}")

    html = (ROOT / "miniapp/index.html").read_text(encoding="utf-8")
    for needle in (
        'id="global-question"',
        'id="draw-question"',
        'id="btn-shuffle"',
        'id="status-ai"',
        'id="spread-grid"',
        'id="btn-owner-stats"',
    ):
        if needle not in html:
            fail(f"html missing {needle}")

    app = (ROOT / "miniapp/js/app.js").read_text(encoding="utf-8")
    for needle in (
        "function getQuestion",
        "function setQuestion",
        "function startSpread",
        "function runDraw",
        "function showResult",
        "loadOwnerStats",
    ):
        if needle not in app:
            fail(f"app.js missing {needle}")

    from bot.admin import admin_ids, format_stats, is_admin, support_username
    from bot.db import get_usage_stats, init_db
    from bot.tarot import TAROT_DECK, TAROT_SPREADS, draw_tarot, tarot_to_dict
    from bot.cards import DECK, draw
    from bot.spreads import SPREADS

    init_db()
    assert len(TAROT_DECK) == 78
    assert len(DECK) == 36
    assert "three" in SPREADS
    assert "t_day" in TAROT_SPREADS
    cards = [tarot_to_dict(c) for c in draw_tarot(3)]
    assert len(cards) == 3
    assert all(c.get("general") for c in cards)
    lc = draw(3)
    assert len(lc) == 3

    stats = get_usage_stats()
    text = format_stats(stats)
    assert "Пользователей" in text

    print("OK regression")
    print("  deck", len(data["deck"]), "tarot", len(data["tarot"]), "spreads", len(data["spreads"]))
    print("  support default", support_username() or "(env)")
    print("  admin_ids", admin_ids() or "(none in this env)")
    print("  is_admin sample", is_admin(367302040))


if __name__ == "__main__":
    main()
