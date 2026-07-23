#!/usr/bin/env python3
"""Mini App static + full API (readings, premium, history, transits, profiles)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
MINIAPP = ROOT / "miniapp"
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from bot import db as store  # noqa: E402
from bot.auth import validate_init_data  # noqa: E402
from bot.premium import (  # noqa: E402
    FREE_AI_READINGS_PER_DAY,
    PLANS,
    PREMIUM_ONLY,
    feature_allowed,
)


def _json(handler, code: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, X-Telegram-Init-Data")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(MINIAPP), **kwargs)

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, fmt, *args):
        print(f"[api] {fmt % args}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Telegram-Init-Data")
        self.end_headers()

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def _user(self, body: dict | None = None) -> dict | None:
        init = self.headers.get("X-Telegram-Init-Data") or ""
        if body and body.get("initData"):
            init = body["initData"]
        # query fallback for GET
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if not init and qs.get("initData"):
            init = qs["initData"][0]
        user = validate_init_data(init)
        if user:
            store.upsert_user(user["id"], user.get("username"), user.get("first_name"))
        return user

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            return _json(self, 200, {"ok": True})
        if path == "/api/ai-status":
            from bot.llm import provider_status

            return _json(self, 200, provider_status())
        if path == "/api/public-config":
            from bot.admin import support_url, support_username

            return _json(
                self,
                200,
                {
                    "support_username": support_username() or None,
                    "support_url": support_url(),
                    "support_bot": "https://t.me/AstoManiabot?start=podderzhka",
                    "bot": "https://t.me/AstoManiabot",
                },
            )
        if path == "/api/admin/stats":
            return self._admin_stats()
        if path == "/api/plans":
            return _json(self, 200, {"plans": list(PLANS.values()), "free_ai_per_day": FREE_AI_READINGS_PER_DAY})
        if path == "/api/me":
            return self._me()
        if path == "/api/history":
            return self._history()
        if path == "/api/profiles":
            return self._profiles()
        if path == "/api/transits":
            return self._transits()
        if path == "/api/journal":
            return self._journal_list()
        if path == "/api/spreads":
            return self._spreads_meta()
        if path == "/api/geocode":
            return self._geocode(parsed)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        routes = {
            "/api/ascendant": self._ascendant,
            "/api/draw": self._draw,
            "/api/profile/save": self._profile_save,
            "/api/profile/default": self._profile_default,
            "/api/journal": self._journal_add,
            "/api/notify": self._notify,
            "/api/reading/day": self._day_reading_get_or_create,
        }
        fn = routes.get(path)
        if fn:
            return fn()
        _json(self, 404, {"error": "not found"})

    def _require_user(self, body: dict | None = None):
        user = self._user(body)
        if not user:
            _json(self, 401, {"error": "Откройте из Telegram Mini App"})
            return None
        return user

    def _me(self):
        from bot.admin import is_admin

        user = self._require_user()
        if not user:
            return
        uid = user["id"]
        prem = store.premium_info(uid)
        used = store.count_ai_today(uid)
        left = max(0, FREE_AI_READINGS_PER_DAY - used) if not prem["active"] else 999
        prof = store.get_default_profile(uid)
        _json(
            self,
            200,
            {
                "user": user,
                "premium": prem,
                "free_ai_used": used,
                "free_ai_left": left,
                "free_ai_limit": FREE_AI_READINGS_PER_DAY,
                "profile": prof,
                "premium_only": list(PREMIUM_ONLY),
                "is_owner": is_admin(uid),
            },
        )

    def _admin_stats(self):
        from bot.admin import format_stats, is_admin

        user = self._require_user()
        if not user:
            return
        if not is_admin(user["id"]):
            return _json(self, 403, {"error": "Статистика только для владельца"})
        stats = store.get_usage_stats()
        text = format_stats(stats)
        recent = stats.get("recent_users") or []
        if recent:
            lines = ["", "Последние пользователи:"]
            for r in recent:
                un = f"@{r['username']}" if r.get("username") else r.get("first_name") or "—"
                lines.append(f"  · {r['user_id']} {un}")
            text += "\n" + "\n".join(lines)
        # без markdown для Mini App
        plain = (
            text.replace("**", "")
            .replace("_", "")
            .replace("`", "")
        )
        _json(self, 200, {"ok": True, "stats": stats, "text": plain})

    def _history(self):
        user = self._require_user()
        if not user:
            return
        limit = 50 if store.is_premium(user["id"]) else 10
        _json(self, 200, {"items": store.list_history(user["id"], limit=limit)})

    def _profiles(self):
        user = self._require_user()
        if not user:
            return
        _json(self, 200, {"items": store.list_profiles(user["id"])})

    def _transits(self):
        from bot.transits import week_transits

        try:
            _json(self, 200, week_transits())
        except Exception as e:
            traceback.print_exc()
            _json(self, 500, {"error": str(e)})

    def _journal_list(self):
        user = self._require_user()
        if not user:
            return
        if not store.is_premium(user["id"]):
            return _json(self, 403, {"error": "Дневник — в полном доступе", "premium_required": True})
        _json(self, 200, {"items": store.list_journal(user["id"])})

    def _spreads_meta(self):
        from bot.spreads import SPREADS
        from bot.tarot import TAROT_SPREADS

        items = []
        for s in SPREADS.values():
            items.append(
                {
                    "id": s.id,
                    "title": s.title,
                    "emoji": s.emoji,
                    "n": s.n_cards,
                    "positions": list(s.positions),
                    "blurb": s.blurb,
                    "focus": s.focus,
                    "premium": s.id in PREMIUM_ONLY,
                    "system": "lenormand",
                }
            )
        # virtual asc_day
        items.insert(
            1,
            {
                "id": "asc_day",
                "title": "День по восходящему знаку",
                "emoji": "🌅",
                "n": 1,
                "positions": ["Карта дня"],
                "blurb": "Личный день через восходящий знак и карту",
                "focus": "general",
                "premium": False,
                "system": "lenormand",
            },
        )
        for meta in TAROT_SPREADS.values():
            items.append(
                {
                    "id": meta["id"],
                    "title": meta["title"],
                    "emoji": meta["emoji"],
                    "n": meta["n"],
                    "positions": list(meta["positions"]),
                    "blurb": meta["blurb"],
                    "focus": "general",
                    "premium": bool(meta.get("premium")),
                    "system": "tarot",
                }
            )
        _json(self, 200, {"items": items})

    def _geocode(self, parsed):
        from bot.astrology import geocode_place

        q = (parse_qs(parsed.query).get("q") or [""])[0]
        try:
            g = geocode_place(q)
            _json(self, 200, {"name": g.name, "lat": g.lat, "lon": g.lon, "timezone": g.timezone})
        except Exception as e:
            _json(self, 400, {"error": str(e)})

    def _ascendant(self):
        from bot.astrology import calculate_ascendant, result_to_dict

        body = self._read_json()
        try:
            date = str(body.get("date") or "").strip()
            time_s = str(body.get("time") or "").strip()
            place = str(body.get("place") or "").strip()
            if not date or not time_s or not place:
                raise ValueError("Нужны date, time, place")
            result = calculate_ascendant(date, time_s, place)
            data = result_to_dict(result)
            data["birth_date"] = date
            data["birth_time"] = time_s
            user = self._user(body)
            if user:
                store.save_profile(
                    user["id"],
                    {**data, "date": date, "time": time_s},
                    label=str(body.get("label") or "Я"),
                    make_default=bool(body.get("make_default", True)),
                )
            _json(self, 200, data)
        except ValueError as e:
            _json(self, 400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            _json(self, 500, {"error": str(e)})

    def _profile_save(self):
        body = self._read_json()
        user = self._require_user(body)
        if not user:
            return
        if not body.get("sign"):
            return _json(self, 400, {"error": "Нет данных профиля"})
        pid = store.save_profile(
            user["id"],
            body,
            label=str(body.get("label") or "Я"),
            make_default=bool(body.get("make_default", True)),
        )
        _json(self, 200, {"ok": True, "id": pid, "items": store.list_profiles(user["id"])})

    def _profile_default(self):
        body = self._read_json()
        user = self._require_user(body)
        if not user:
            return
        store.set_default_profile(user["id"], int(body["profile_id"]))
        _json(self, 200, {"ok": True, "items": store.list_profiles(user["id"])})

    def _notify(self):
        body = self._read_json()
        user = self._require_user(body)
        if not user:
            return
        if body.get("enabled") and not store.is_premium(user["id"]):
            return _json(self, 403, {"error": "Напоминания — в полном доступе", "premium_required": True})
        store.set_notify(
            user["id"],
            bool(body.get("enabled")),
            hour=int(body.get("hour") or 9),
            tz=str(body.get("timezone") or "Europe/Moscow"),
        )
        _json(self, 200, {"ok": True})

    def _journal_add(self):
        body = self._read_json()
        user = self._require_user(body)
        if not user:
            return
        if not store.is_premium(user["id"]):
            return _json(self, 403, {"error": "Дневник — в полном доступе", "premium_required": True})
        store.add_journal(
            int(body["reading_id"]),
            user["id"],
            int(body.get("rating") or 0),
            str(body.get("note") or ""),
        )
        _json(self, 200, {"ok": True})

    def _draw(self):
        """Вытянуть карты + (опц.) ИИ с лимитами premium. Ленорман и Таро."""
        from bot.cards import draw
        from bot.llm import build_spread_prompt, chat, fallback_spread_text
        from bot.spreads import SPREADS
        from bot.tarot import TAROT_SPREADS, draw_tarot, tarot_to_dict

        body = self._read_json()
        user = self._require_user(body)
        if not user:
            return
        uid = user["id"]
        sid = str(body.get("spread_id") or "three")
        question = (body.get("question") or "").strip() or None
        want_ai = bool(body.get("ai", True))

        if sid == "asc_day":
            return _json(self, 400, {"error": "Для дня по восходящему используйте другой запрос"})

        is_tarot = sid.startswith("t_") or sid in TAROT_SPREADS
        if is_tarot:
            if sid not in TAROT_SPREADS:
                return _json(self, 400, {"error": "Неизвестный расклад Таро"})
            meta = TAROT_SPREADS[sid]
            spread_title = meta["title"]
            spread_emoji = meta["emoji"]
            spread_blurb = meta["blurb"]
            n_cards = meta["n"]
            positions = list(meta["positions"])
            system = "tarot"
        else:
            if sid not in SPREADS:
                return _json(self, 400, {"error": "Неизвестный расклад"})
            spread = SPREADS[sid]
            spread_title = spread.title
            spread_emoji = spread.emoji
            spread_blurb = spread.blurb
            n_cards = spread.n_cards
            positions = list(spread.positions)
            system = "lenormand"

        prem = store.is_premium(uid)
        gate = feature_allowed(sid, is_premium=prem, free_ai_left=1)
        if not gate["ok"]:
            return _json(self, 403, {**gate, "premium_required": True})

        # once-per-day for card of day (Ленорман и Таро)
        if sid in ("day", "t_day"):
            existing = store.get_day_reading(uid, sid)
            if existing:
                return _json(
                    self,
                    200,
                    {
                        "cached": True,
                        "reading_id": existing["id"],
                        "spread_id": sid,
                        "title": existing["title"],
                        "emoji": spread_emoji,
                        "cards": json.loads(existing["cards_json"] or "[]"),
                        "ai_text": existing["ai_text"],
                        "question": existing["question"],
                        "day_key": existing["day_key"],
                        "system": system,
                    },
                )

        if is_tarot:
            cards_d = [tarot_to_dict(c) for c in draw_tarot(n_cards)]
        else:
            cards = draw(n_cards)
            cards_d = [
                {
                    "number": c.number,
                    "name": c.name,
                    "emoji": c.emoji,
                    "keywords": c.keywords,
                    "general": c.general,
                    "love": c.love,
                    "work": c.work,
                    "advice": c.advice,
                    "system": "lenormand",
                }
                for c in cards
            ]

        ai_text = None
        provider = model = None
        ai_flag = False
        sys_blurb = (
            f"{spread_blurb} Система: Таро Райдера–Уэйта."
            if is_tarot
            else f"{spread_blurb} Система: Ленорман."
        )

        if want_ai:
            used = store.count_ai_today(uid)
            left = 999 if prem else max(0, FREE_AI_READINGS_PER_DAY - used)
            agate = feature_allowed("ai", is_premium=prem, free_ai_left=left)
            if not agate["ok"]:
                rid = store.save_reading(
                    uid, sid, spread_title, question, cards_d, None, {"no_ai": agate, "system": system}
                )
                return _json(
                    self,
                    200,
                    {
                        "reading_id": rid,
                        "spread_id": sid,
                        "title": spread_title,
                        "emoji": spread_emoji,
                        "blurb": spread_blurb,
                        "positions": positions,
                        "cards": cards_d,
                        "ai_text": None,
                        "ai": False,
                        "limit": agate,
                        "premium": store.premium_info(uid),
                        "system": system,
                    },
                )

            card_ids = [c.get("id") or c.get("number") for c in cards_d]
            cache_key = hashlib.sha256(
                json.dumps(
                    {"sid": sid, "cards": card_ids, "q": question or "", "d": store.today_key()},
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            cached = store.cache_get(cache_key)
            if cached:
                ai_text, provider, model, ai_flag = cached["text"], cached["provider"], cached.get("model"), True
            else:
                prompt = build_spread_prompt(
                    spread_title=spread_title,
                    spread_blurb=sys_blurb,
                    cards=cards_d,
                    positions=positions,
                    question=question,
                    extra="Пиши только по-русски, без англицизмов. Тон светлый и бережный.",
                )
                if sid in ("week", "month", "deep", "compat", "t_celtic", "t_path"):
                    prompt += "\nСделай текст чуть подробнее, но всё ещё тёплым и без страшилок."
                try:
                    ai_text, provider, model = chat(prompt)
                    ai_flag = True
                    store.cache_set(cache_key, ai_text, provider, model)
                    if not prem:
                        store.inc_ai_today(uid)
                except Exception as e:
                    ai_text = fallback_spread_text(cards_d, spread_title)
                    provider = "fallback"
                    ai_flag = False
                    ai_text += f"\n\n_(Прогноз: {e})_"

        rid = store.save_reading(
            uid,
            sid,
            spread_title,
            question,
            cards_d,
            ai_text,
            {"provider": provider, "model": model, "system": system},
            day_key=store.today_key(),
        )

        _json(
            self,
            200,
            {
                "reading_id": rid,
                "spread_id": sid,
                "title": spread_title,
                "emoji": spread_emoji,
                "blurb": spread_blurb,
                "positions": positions,
                "cards": cards_d,
                "question": question,
                "ai_text": ai_text,
                "ai": ai_flag,
                "provider": provider,
                "model": model,
                "system": system,
                "premium": store.premium_info(uid),
                "free_ai_left": (
                    999
                    if prem
                    else max(0, FREE_AI_READINGS_PER_DAY - store.count_ai_today(uid))
                ),
            },
        )

    def _day_reading_get_or_create(self):
        """Карта дня или ASC-день — 1 раз в сутки."""
        from bot.cards import DECK
        from bot.llm import build_asc_day_prompt, build_spread_prompt, chat, fallback_spread_text
        from bot.spreads import SPREADS

        body = self._read_json()
        user = self._require_user(body)
        if not user:
            return
        uid = user["id"]
        kind = str(body.get("kind") or "day")  # day | asc_day
        force = bool(body.get("force")) and store.is_premium(uid)

        existing = store.get_day_reading(uid, kind)
        if existing and not force:
            return _json(
                self,
                200,
                {
                    "cached": True,
                    "reading_id": existing["id"],
                    "kind": kind,
                    "title": existing["title"],
                    "cards": json.loads(existing["cards_json"] or "[]"),
                    "ai_text": existing["ai_text"],
                    "meta": json.loads(existing["meta_json"] or "{}"),
                    "day_key": existing["day_key"],
                },
            )

        # build cards
        if kind == "asc_day":
            prof = store.get_default_profile(uid)
            if not prof and body.get("profile"):
                prof = body["profile"]
            if not prof or not prof.get("sign"):
                return _json(self, 400, {"error": "Сначала рассчитайте восходящий знак", "need_profile": True})
            # deterministic card
            day_key = store.today_key()
            seed_s = f"{day_key}-{prof['sign']}-{prof.get('absolute_degree', 0)}"
            h = int(hashlib.sha256(seed_s.encode()).hexdigest(), 16)
            card = DECK[h % len(DECK)]
            cards_d = [
                {
                    "number": card.number,
                    "name": card.name,
                    "emoji": card.emoji,
                    "keywords": card.keywords,
                    "general": card.general,
                    "love": card.love,
                    "work": card.work,
                    "advice": card.advice,
                }
            ]
            title = f"День по восходящему знаку · {prof['sign']}"
            prompt = build_asc_day_prompt(
                sign=prof["sign"],
                emoji=prof.get("emoji") or "✦",
                degree=float(prof.get("degree_in_sign") or 0),
                place=prof.get("place") or "",
                card=cards_d[0],
                base_day=None,
            )
            meta = {"profile": {"sign": prof["sign"], "emoji": prof.get("emoji"), "place": prof.get("place")}}
        else:
            spread = SPREADS["day"]
            from bot.cards import draw

            c = draw(1)[0]
            cards_d = [
                {
                    "number": c.number,
                    "name": c.name,
                    "emoji": c.emoji,
                    "keywords": c.keywords,
                    "general": c.general,
                    "love": c.love,
                    "work": c.work,
                    "advice": c.advice,
                }
            ]
            title = spread.title
            prompt = build_spread_prompt(
                spread_title=spread.title,
                spread_blurb=spread.blurb,
                cards=cards_d,
                positions=list(spread.positions),
            )
            meta = {}

        prem = store.is_premium(uid)
        used = store.count_ai_today(uid)
        left = 999 if prem else max(0, FREE_AI_READINGS_PER_DAY - used)
        ai_text = None
        provider = model = None
        ai_flag = False

        agate = feature_allowed("ai", is_premium=prem, free_ai_left=left)
        if agate["ok"]:
            ck = hashlib.sha256(f"{uid}:{kind}:{store.today_key()}:{cards_d[0]['number']}".encode()).hexdigest()
            cached = store.cache_get(ck)
            if cached:
                ai_text, provider, model, ai_flag = cached["text"], cached["provider"], cached.get("model"), True
            else:
                try:
                    ai_text, provider, model = chat(prompt)
                    ai_flag = True
                    store.cache_set(ck, ai_text, provider, model)
                    if not prem:
                        store.inc_ai_today(uid)
                except Exception as e:
                    ai_text = fallback_spread_text(cards_d, title) + f"\n\n_(Прогноз: {e})_"
                    provider = "fallback"
        else:
            ai_text = fallback_spread_text(cards_d, title)
            meta["limit"] = agate

        rid = store.save_reading(uid, kind, title, None, cards_d, ai_text, {**meta, "provider": provider, "model": model})
        _json(
            self,
            200,
            {
                "cached": False,
                "reading_id": rid,
                "kind": kind,
                "title": title,
                "cards": cards_d,
                "ai_text": ai_text,
                "ai": ai_flag,
                "provider": provider,
                "model": model,
                "meta": meta,
                "day_key": store.today_key(),
                "premium": store.premium_info(uid),
                "free_ai_left": 999 if prem else max(0, FREE_AI_READINGS_PER_DAY - store.count_ai_today(uid)),
            },
        )


def main() -> None:
    store.init_db()
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    args = p.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    from bot.llm import provider_status

    print(f"Mini App + API http://{args.host}:{args.port}/")
    print("MINIAPP_URL=", os.environ.get("MINIAPP_URL"))
    print("AI:", provider_status())
    server.serve_forever()


if __name__ == "__main__":
    main()
