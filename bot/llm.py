"""
Быстрые LLM для прогнозов (OpenAI-compatible).

Рекомендуется DeepSeek (китайская, быстрая, почти бесплатная):
  DEEPSEEK_API_KEY=...   # https://platform.deepseek.com

Также:
  SILICONFLOW_API_KEY  # https://siliconflow.cn — Qwen/DeepSeek free-модели
  GROQ_API_KEY         # https://console.groq.com — очень быстро, free tier
  OPENROUTER_API_KEY   # free-модели :free (ротация нескольких моделей)
  LLM_PROVIDER / LLM_API_KEY / LLM_MODEL / LLM_BASE_URL — универсально
  OPENROUTER_FREE_MODELS — свой список id через запятую (опционально)
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("llm")


SYSTEM_PROMPT = """Ты — мягкий, добрый проводник по картам Ленорман, Таро Райдера–Уэйта и астрологии.
Пиши только по-русски, тепло, спокойно, без эзотерического пафоса и без запугивания.
Не используй английские слова и англицизмы (никаких premium, free, AI, OK, update и т.п.).
Говори «восходящий знак» вместо ASC, «живой прогноз» вместо ИИ, «полный доступ» вместо premium.
Не давай медицинских, юридических и финансовых гарантий.
Не предсказывай смерть, болезни, катастрофы.
Формулируй как поддержку и зеркало: тенденции, вопросы к себе, бережные советы.
Объём: 2–4 коротких абзаца; можно короткие подзаголовки без символа #.
Эмодзи — умеренно."""


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    api_key: str


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


# Бесплатные модели OpenRouter для чат-прогнозов (приоритет сверху).
# Специализированные (код, безопасность, аудио) — ниже или пропущены.
_OPENROUTER_FREE_DEFAULT = [
    # роутер OpenRouter — сам выбирает свободную free-модель
    "openrouter/free",
    # Google Gemma 4 — хорошо для тёплого текста
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    # NVIDIA Nemotron — сильные free-модели
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-nano-9b-v2:free",
    # OpenAI OSS
    "openai/gpt-oss-20b:free",
    # прочие free
    "inclusionai/ling-3.0-flash:free",
    "poolside/laguna-xs-2.1:free",
    "poolside/laguna-m.1:free",
    "poolside/laguna-s-2.1:free",
    "cohere/north-mini-code:free",
]

# Модели, которые плохо подходят для текстовых прогнозов (роутер сам их не даст, но в списке API бывают)
_OPENROUTER_SKIP_SUBSTRINGS = (
    "content-safety",
    "lyria",  # аудио
    "-vl:",  # vision-only
    "-vl/",
)

# Бесплатные/быстрые модели Groq (free tier)
_GROQ_FREE_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "qwen/qwen3-32b",
]

# SiliconFlow — популярные дешёвые/free
_SILICONFLOW_FREE_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-14B-Instruct",
    "deepseek-ai/DeepSeek-V2.5",
    "THUDM/glm-4-9b-chat",
]

_cached_or_models: list[str] | None = None
_cached_or_ts: float = 0.0


def _parse_models_env(raw: str) -> list[str]:
    if not raw:
        return []
    return [m.strip() for m in raw.replace("\n", ",").split(",") if m.strip()]


def _openrouter_free_models() -> list[str]:
    """Список free-моделей: env override → кэш API → дефолт."""
    global _cached_or_models, _cached_or_ts

    override = _parse_models_env(_env("OPENROUTER_FREE_MODELS"))
    if override:
        return override

    # обновляем с OpenRouter не чаще раза в час
    now = time.time()
    if _cached_or_models and now - _cached_or_ts < 3600:
        return _cached_or_models

    live = _fetch_openrouter_free_models()
    if live:
        # приоритет: наши дефолты (в их порядке), потом остальные free с API
        preferred = [m for m in _OPENROUTER_FREE_DEFAULT if m in live or m == "openrouter/free"]
        rest = [m for m in live if m not in preferred]
        _cached_or_models = preferred + rest
        _cached_or_ts = now
        log.info("OpenRouter free models refreshed: %d", len(_cached_or_models))
        return _cached_or_models

    return list(_OPENROUTER_FREE_DEFAULT)


def _fetch_openrouter_free_models() -> list[str]:
    """Публичный список free-моделей OpenRouter (без ключа)."""
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"User-Agent": "Astromania/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning("OpenRouter models fetch failed: %s", e)
        return []

    free: list[str] = []
    for m in data.get("data") or []:
        mid = str(m.get("id") or "")
        if not mid:
            continue
        if any(s in mid for s in _OPENROUTER_SKIP_SUBSTRINGS):
            continue
        pricing = m.get("pricing") or {}
        prompt = str(pricing.get("prompt", "1"))
        completion = str(pricing.get("completion", "1"))
        is_free = mid.endswith(":free") or mid == "openrouter/free" or (
            prompt in ("0", "0.0") and completion in ("0", "0.0")
        )
        if is_free:
            free.append(mid)
    return free


def configured_providers() -> list[Provider]:
    """LLM_PROVIDER + его ключ идут первыми; остальные — запасные."""
    out: list[Provider] = []
    prov = _env("LLM_PROVIDER").lower()
    key = _env("LLM_API_KEY")
    model = _env("LLM_MODEL")
    base = _env("LLM_BASE_URL")
    default_or = model or _OPENROUTER_FREE_DEFAULT[1]  # gemma-4-31b

    defaults = {
        "deepseek": (
            "https://api.deepseek.com/v1",
            "deepseek-chat",
            _env("DEEPSEEK_API_KEY") or key,
        ),
        "siliconflow": (
            "https://api.siliconflow.cn/v1",
            model or _SILICONFLOW_FREE_MODELS[0],
            _env("SILICONFLOW_API_KEY") or key,
        ),
        "groq": (
            "https://api.groq.com/openai/v1",
            model or _GROQ_FREE_MODELS[0],
            _env("GROQ_API_KEY") or key,
        ),
        "openrouter": (
            "https://openrouter.ai/api/v1",
            default_or,
            _env("OPENROUTER_API_KEY") or key,
        ),
        "custom": (base, model, key),
    }

    # Primary from LLM_PROVIDER
    if prov in defaults:
        b, m, k = defaults[prov]
        if prov in ("openrouter", "groq", "siliconflow") and model:
            m = model
        if prov == "custom":
            b, m, k = base, model, key
        if b and m and k:
            out.append(Provider(prov, b.rstrip("/"), m, k))

    # Fallbacks (несколько провайдеров, если ключи есть)
    order = [
        ("openrouter", "https://openrouter.ai/api/v1", default_or, _env("OPENROUTER_API_KEY")),
        ("deepseek", "https://api.deepseek.com/v1", "deepseek-chat", _env("DEEPSEEK_API_KEY")),
        ("siliconflow", "https://api.siliconflow.cn/v1", _SILICONFLOW_FREE_MODELS[0], _env("SILICONFLOW_API_KEY")),
        ("groq", "https://api.groq.com/openai/v1", _GROQ_FREE_MODELS[0], _env("GROQ_API_KEY")),
    ]
    for name, b, m, k in order:
        if k:
            out.append(Provider(name, b.rstrip("/"), m, k))

    if key and not prov:
        out.insert(0, Provider("openrouter", "https://openrouter.ai/api/v1", default_or, key))

    seen: set[str] = set()
    unique: list[Provider] = []
    for p in out:
        if p.name not in seen and p.api_key:
            unique.append(p)
            seen.add(p.name)
    return unique


def provider_status() -> dict[str, Any]:
    providers = configured_providers()
    free_n = len(_openrouter_free_models()) if any(p.name == "openrouter" for p in providers) else 0
    return {
        "ok": True,
        "ai_enabled": bool(providers),
        "providers": [p.name for p in providers],
        "primary": providers[0].name if providers else None,
        "model": providers[0].model if providers else None,
        "openrouter_free_pool": free_n,
        "hint": (
            "Добавьте OPENROUTER_API_KEY (free-модели) или DEEPSEEK_API_KEY / GROQ_API_KEY."
            if not providers
            else f"ИИ: {providers[0].name} / {providers[0].model}"
            + (f" · free-пул: {free_n}" if free_n else "")
        ),
    }


def _chat_once(
    provider: Provider,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.75,
    max_tokens: int = 800,
    timeout: float = 55.0,
) -> str:
    endpoint = provider.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {provider.api_key}",
    }
    if provider.name == "openrouter":
        headers["HTTP-Referer"] = "https://t.me/AstoManiabot"
        headers["X-Title"] = "Astromania"

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"HTTP {e.code}: {body}") from e

    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(
            (p.get("text") if isinstance(p, dict) else str(p)) for p in content
        )
    text = str(content).strip()
    if len(text) < 15:
        raise RuntimeError("Пустой ответ модели")
    return text


def _expand_providers(providers: list[Provider]) -> list[Provider]:
    """Разворачивает провайдеров в пул моделей (free-ротация)."""
    expanded: list[Provider] = []
    seen: set[tuple[str, str]] = set()

    def add(p: Provider) -> None:
        key = (p.name, p.model)
        if key not in seen and p.api_key and p.model:
            seen.add(key)
            expanded.append(p)

    for p in providers:
        if p.name == "openrouter":
            models = list(_openrouter_free_models())
            # LLM_MODEL первым, если задан
            preferred = _env("LLM_MODEL") or p.model
            if preferred and preferred not in models:
                models.insert(0, preferred)
            elif preferred in models:
                models.remove(preferred)
                models.insert(0, preferred)
            for m in models:
                add(Provider(p.name, p.base_url, m, p.api_key))
        elif p.name == "groq":
            models = list(_GROQ_FREE_MODELS)
            if p.model and p.model not in models:
                models.insert(0, p.model)
            for m in models:
                add(Provider(p.name, p.base_url, m, p.api_key))
        elif p.name == "siliconflow":
            models = list(_SILICONFLOW_FREE_MODELS)
            if p.model and p.model not in models:
                models.insert(0, p.model)
            for m in models:
                add(Provider(p.name, p.base_url, m, p.api_key))
        else:
            add(p)
    return expanded


def chat(user_prompt: str, *, system: str = SYSTEM_PROMPT) -> tuple[str, str, str]:
    """Returns (text, provider_name, model)."""
    providers = configured_providers()
    if not providers:
        raise RuntimeError(
            "Нет API-ключа ИИ. Добавьте OPENROUTER_API_KEY или DEEPSEEK_API_KEY в .env."
        )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    errors: list[str] = []
    expanded = _expand_providers(providers)

    for p in expanded:
        for attempt in range(2):
            try:
                text = _chat_once(p, messages)
                log.info("LLM ok %s/%s", p.name, p.model)
                return text, p.name, p.model
            except Exception as e:
                err = str(e)
                errors.append(f"{p.name}/{p.model}: {err[:120]}")
                # rate limit / overloaded — чуть ждём и пробуем снова, потом следующая модель
                if any(x in err for x in ("429", "rate", "overloaded", "capacity")) and attempt == 0:
                    time.sleep(1.5)
                    continue
                break
    raise RuntimeError("ИИ недоступен: " + " | ".join(errors[:6]))


def build_spread_prompt(
    *,
    spread_title: str,
    spread_blurb: str,
    cards: list[dict[str, Any]],
    positions: list[str] | None = None,
    question: str | None = None,
    extra: str | None = None,
) -> str:
    lines = [
        f"Сделай тёплый прогноз-расклад «{spread_title}».",
        f"Контекст: {spread_blurb}",
    ]
    if question:
        lines.append(f"Вопрос пользователя: {question}")
    is_tarot = any(c.get("system") == "tarot" for c in cards) or (
        "Таро" in (spread_blurb or "") or "Райдера" in (spread_blurb or "")
    )
    lines.append("Выпавшие карты Таро Райдера–Уэйта:" if is_tarot else "Выпавшие карты Ленорман:")
    for i, c in enumerate(cards):
        pos = f" [{positions[i]}]" if positions and i < len(positions) else ""
        body = c.get("upright") or c.get("general") or ""
        num = c.get("number", "")
        lines.append(
            f"-{pos} {num}. {c.get('name')} ({c.get('emoji', '')}): "
            f"{c.get('keywords', '')}. {body}"
        )
    if extra:
        lines.append(extra)
    lines.append(
        "Свяжи карты. Дай общий тон, что важно в ситуации, бережный совет. Живым текстом."
    )
    return "\n".join(lines)


def build_asc_day_prompt(
    *,
    sign: str,
    emoji: str,
    degree: float,
    place: str,
    card: dict[str, Any] | None,
    base_day: dict[str, Any] | None = None,
    kind: str = "asc_day",
) -> str:
    """kind: sun_day | moon_day | asc_day — разные роли натальной карты, не транзит."""
    if kind == "sun_day":
        title = "Сила дня · через Солнце"
        lens = (
            f"Натальное Солнце: {emoji} {sign}, {degree}° в знаке. Место рождения: {place}. "
            "Это ядро личности и источник воли — не положение Солнца «на небе сегодня». "
            "Пиши, как опереться на солнечные качества знака в течение дня."
        )
        stitch = "Сшей силу Солнца с посланием карты."
    elif kind == "moon_day":
        title = "Чувства дня · через Луну"
        lens = (
            f"Натальная Луна: {emoji} {sign}, {degree}° в знаке. Место рождения: {place}. "
            "Это эмоции, потребности и способ заботиться о себе — не текущий транзит Луны. "
            "Пиши про внутренний климат и мягкую поддержку."
        )
        stitch = "Сшей лунные потребности с посланием карты."
    else:
        title = "Стиль дня · через восходящий знак"
        lens = (
            f"Восходящий знак: {emoji} {sign}, {degree}° в знаке. Место рождения: {place}. "
            "Это как человек встречает мир: первый контакт, общение, тело, образ. "
            "Не путай с Солнцем (ядро) и Луной (чувства)."
        )
        stitch = "Сшей стиль восходящего знака с посланием карты."

    lines = [
        f"Сделай персональный текст «{title}» на сегодня.",
        lens,
        "Важно: это линза натальной карты + карта дня. Не выдавай за полный гороскоп транзитов.",
        "Говори «восходящий знак», не ASC / асцендент. Без англицизмов.",
    ]
    if base_day:
        lines.append(
            f"Черновик (развей, не копируй): {base_day.get('mood', '')}. {base_day.get('body', '')}"
        )
    if card:
        lines.append(
            f"Карта Ленорман дня: {card.get('number')}. {card.get('name')} — "
            f"{card.get('keywords')}. {card.get('general')}"
        )
        lines.append(stitch)
    lines.append(
        "Структура:\n"
        "• Настроение (1 строка)\n"
        "• 2 абзаца\n"
        "• Фокус\n"
        "• Мягкий совет"
    )
    return "\n".join(lines)


def fallback_spread_text(cards: list[dict[str, Any]], title: str) -> str:
    names = ", ".join(f"{c.get('emoji', '')} {c.get('name')}" for c in cards)
    bits = [c.get("general", "") for c in cards if c.get("general")]
    advice = cards[-1].get("advice", "Будьте добрее к себе.") if cards else ""
    return (
        f"🌸 {title}\n\n"
        f"Сегодня с вами карты: {names}.\n\n"
        + " ".join(bits[:2])
        + f"\n\n💫 {advice}\n\n"
        "_Краткий режим: живой прогноз временно недоступен. Повторите через минуту._"
    )
