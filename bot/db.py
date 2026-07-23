"""SQLite: пользователи, премиум, история, профили, журнал, кэш ИИ."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                notify INTEGER DEFAULT 0,
                notify_hour INTEGER DEFAULT 9,
                timezone TEXT DEFAULT 'Europe/Moscow',
                free_ai_used_date TEXT,
                free_ai_count INTEGER DEFAULT 0,
                created_at REAL,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS premium (
                user_id INTEGER PRIMARY KEY,
                until_ts REAL,
                plan TEXT,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                payload TEXT,
                stars INTEGER,
                plan TEXT,
                telegram_payment_charge_id TEXT,
                created_at REAL
            );

            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                label TEXT,
                birth_date TEXT,
                birth_time TEXT,
                place TEXT,
                lat REAL,
                lon REAL,
                timezone TEXT,
                sign TEXT,
                emoji TEXT,
                degree_in_sign REAL,
                absolute_degree REAL,
                is_default INTEGER DEFAULT 0,
                created_at REAL
            );

            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                kind TEXT,
                title TEXT,
                question TEXT,
                cards_json TEXT,
                ai_text TEXT,
                meta_json TEXT,
                day_key TEXT,
                created_at REAL
            );

            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reading_id INTEGER,
                user_id INTEGER,
                rating INTEGER,
                note TEXT,
                created_at REAL
            );

            CREATE TABLE IF NOT EXISTS ai_cache (
                cache_key TEXT PRIMARY KEY,
                text TEXT,
                provider TEXT,
                model TEXT,
                created_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_readings_user_day ON readings(user_id, day_key, kind);
            CREATE INDEX IF NOT EXISTS idx_profiles_user ON profiles(user_id);
            """
        )


def upsert_user(user_id: int, username: str | None = None, first_name: str | None = None) -> None:
    now = time.time()
    with db() as conn:
        row = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET username=COALESCE(?,username), first_name=COALESCE(?,first_name), updated_at=? WHERE user_id=?",
                (username, first_name, now, user_id),
            )
        else:
            conn.execute(
                "INSERT INTO users(user_id, username, first_name, created_at, updated_at) VALUES (?,?,?,?,?)",
                (user_id, username, first_name, now, now),
            )


def is_premium(user_id: int) -> bool:
    with db() as conn:
        row = conn.execute("SELECT until_ts FROM premium WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return False
        return float(row["until_ts"]) > time.time()


def premium_info(user_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute(
            "SELECT until_ts, plan FROM premium WHERE user_id=?", (user_id,)
        ).fetchone()
    if not row or float(row["until_ts"]) <= time.time():
        return {"active": False, "until": None, "plan": None}
    return {
        "active": True,
        "until": datetime.fromtimestamp(float(row["until_ts"]), tz=timezone.utc).isoformat(),
        "until_ts": float(row["until_ts"]),
        "plan": row["plan"],
    }


def grant_premium(user_id: int, days: int, plan: str) -> None:
    now = time.time()
    with db() as conn:
        row = conn.execute("SELECT until_ts FROM premium WHERE user_id=?", (user_id,)).fetchone()
        base = now
        if row and float(row["until_ts"]) > now:
            base = float(row["until_ts"])
        until = base + days * 86400
        conn.execute(
            "INSERT INTO premium(user_id, until_ts, plan, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET until_ts=excluded.until_ts, plan=excluded.plan, updated_at=excluded.updated_at",
            (user_id, until, plan, now),
        )


def record_payment(user_id: int, payload: str, stars: int, plan: str, charge_id: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO payments(user_id, payload, stars, plan, telegram_payment_charge_id, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, payload, stars, plan, charge_id, time.time()),
        )


def set_notify(user_id: int, enabled: bool, hour: int = 9, tz: str = "Europe/Moscow") -> None:
    with db() as conn:
        conn.execute(
            "UPDATE users SET notify=?, notify_hour=?, timezone=?, updated_at=? WHERE user_id=?",
            (1 if enabled else 0, hour, tz, time.time(), user_id),
        )
        if conn.total_changes == 0:
            conn.execute(
                "INSERT INTO users(user_id, notify, notify_hour, timezone, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (user_id, 1 if enabled else 0, hour, tz, time.time(), time.time()),
            )


def list_notify_users() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT user_id, notify_hour, timezone FROM users WHERE notify=1"
        ).fetchall()
    return [dict(r) for r in rows]


def today_key(tz_name: str = "Europe/Moscow") -> str:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name)).date().isoformat()
    except Exception:
        return date.today().isoformat()


def get_day_reading(user_id: int, kind: str, day_key: str | None = None) -> dict | None:
    dk = day_key or today_key()
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM readings WHERE user_id=? AND kind=? AND day_key=? ORDER BY id DESC LIMIT 1",
            (user_id, kind, dk),
        ).fetchone()
    return dict(row) if row else None


def save_reading(
    user_id: int,
    kind: str,
    title: str,
    question: str | None,
    cards: list,
    ai_text: str | None,
    meta: dict | None = None,
    day_key: str | None = None,
) -> int:
    dk = day_key or today_key()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO readings(user_id, kind, title, question, cards_json, ai_text, meta_json, day_key, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                kind,
                title,
                question,
                json.dumps(cards, ensure_ascii=False),
                ai_text,
                json.dumps(meta or {}, ensure_ascii=False),
                dk,
                time.time(),
            ),
        )
        return int(cur.lastrowid)


def list_history(user_id: int, limit: int = 30) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, kind, title, question, cards_json, ai_text, day_key, created_at FROM readings "
            "WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["cards"] = json.loads(d.pop("cards_json") or "[]")
        out.append(d)
    return out


def count_ai_today(user_id: int) -> int:
    dk = today_key()
    with db() as conn:
        row = conn.execute(
            "SELECT free_ai_used_date, free_ai_count FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return 0
        if row["free_ai_used_date"] != dk:
            return 0
        return int(row["free_ai_count"] or 0)


def inc_ai_today(user_id: int) -> int:
    dk = today_key()
    with db() as conn:
        row = conn.execute(
            "SELECT free_ai_used_date, free_ai_count FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row:
            upsert_user(user_id)
            count = 1
            conn.execute(
                "UPDATE users SET free_ai_used_date=?, free_ai_count=?, updated_at=? WHERE user_id=?",
                (dk, count, time.time(), user_id),
            )
            return count
        if row["free_ai_used_date"] != dk:
            count = 1
        else:
            count = int(row["free_ai_count"] or 0) + 1
        conn.execute(
            "UPDATE users SET free_ai_used_date=?, free_ai_count=?, updated_at=? WHERE user_id=?",
            (dk, count, time.time(), user_id),
        )
        return count


def save_profile(user_id: int, data: dict, label: str = "Я", make_default: bool = True) -> int:
    now = time.time()
    with db() as conn:
        if make_default:
            conn.execute("UPDATE profiles SET is_default=0 WHERE user_id=?", (user_id,))
        cur = conn.execute(
            "INSERT INTO profiles(user_id, label, birth_date, birth_time, place, lat, lon, timezone, "
            "sign, emoji, degree_in_sign, absolute_degree, is_default, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                label,
                data.get("birth_date") or data.get("date"),
                data.get("birth_time") or data.get("time"),
                data.get("place"),
                data.get("lat"),
                data.get("lon"),
                data.get("timezone"),
                data.get("sign"),
                data.get("emoji"),
                data.get("degree_in_sign"),
                data.get("absolute_degree"),
                1 if make_default else 0,
                now,
            ),
        )
        return int(cur.lastrowid)


def list_profiles(user_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM profiles WHERE user_id=? ORDER BY is_default DESC, id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_default_profile(user_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE user_id=? AND is_default=1 ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM profiles WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
    return dict(row) if row else None


def set_default_profile(user_id: int, profile_id: int) -> None:
    with db() as conn:
        conn.execute("UPDATE profiles SET is_default=0 WHERE user_id=?", (user_id,))
        conn.execute(
            "UPDATE profiles SET is_default=1 WHERE user_id=? AND id=?",
            (user_id, profile_id),
        )


def add_journal(reading_id: int, user_id: int, rating: int, note: str = "") -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO journal(reading_id, user_id, rating, note, created_at) VALUES (?,?,?,?,?)",
            (reading_id, user_id, rating, note, time.time()),
        )


def list_journal(user_id: int, limit: int = 50) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT j.*, r.title, r.kind, r.day_key FROM journal j "
            "LEFT JOIN readings r ON r.id=j.reading_id "
            "WHERE j.user_id=? ORDER BY j.id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def cache_get(key: str, max_age_sec: int = 86400) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT text, provider, model, created_at FROM ai_cache WHERE cache_key=?",
            (key,),
        ).fetchone()
    if not row:
        return None
    if time.time() - float(row["created_at"]) > max_age_sec:
        return None
    return {"text": row["text"], "provider": row["provider"], "model": row["model"], "cached": True}


def cache_set(key: str, text: str, provider: str, model: str | None) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO ai_cache(cache_key, text, provider, model, created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(cache_key) DO UPDATE SET text=excluded.text, provider=excluded.provider, "
            "model=excluded.model, created_at=excluded.created_at",
            (key, text, provider, model, time.time()),
        )


# init on import
init_db()
