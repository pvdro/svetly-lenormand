"""
Быстрые LLM для прогнозов (OpenAI-compatible).

Рекомендуется DeepSeek (китайская, быстрая, почти бесплатная):
  DEEPSEEK_API_KEY=...   # https://platform.deepseek.com

Также:
  SILICONFLOW_API_KEY  # https://siliconflow.cn — Qwen/DeepSeek free-модели
  GROQ_API_KEY         # https://console.groq.com — очень быстро, free tier
  OPENROUTER_API_KEY   # free-модели :free
  LLM_PROVIDER / LLM_API_KEY / LLM_MODEL / LLM_BASE_URL — универсально
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


SYSTEM_PROMPT = """Ты — мягкий, добрый проводник по картам Ленорман и астрологии.
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


def configured_providers() -> list[Provider]:
    """LLM_PROVIDER + его ключ идут первыми; остальные — запасные."""
    out: list[Provider] = []
    prov = _env("LLM_PROVIDER").lower()
    key = _env("LLM_API_KEY")
    model = _env("LLM_MODEL")
    base = _env("LLM_BASE_URL")

    defaults = {
        "deepseek": (
            "https://api.deepseek.com/v1",
            "deepseek-chat",
            _env("DEEPSEEK_API_KEY") or key,
        ),
        "siliconflow": (
            "https://api.siliconflow.cn/v1",
            "Qwen/Qwen2.5-7B-Instruct",
            _env("SILICONFLOW_API_KEY") or key,
        ),
        "groq": (
            "https://api.groq.com/openai/v1",
            "llama-3.1-8b-instant",
            _env("GROQ_API_KEY") or key,
        ),
        "openrouter": (
            "https://openrouter.ai/api/v1",
            model or "google/gemma-4-26b-a4b-it:free",
            _env("OPENROUTER_API_KEY") or key,
        ),
        "custom": (base, model, key),
    }

    # Primary from LLM_PROVIDER
    if prov in defaults:
        b, m, k = defaults[prov]
        if prov == "openrouter" and model:
            m = model
        if prov == "custom":
            b, m, k = base, model, key
        if b and m and k:
            out.append(Provider(prov, b.rstrip("/"), m, k))

    # Fallbacks
    order = [
        ("openrouter", "https://openrouter.ai/api/v1", model or "google/gemma-4-26b-a4b-it:free", _env("OPENROUTER_API_KEY")),
        ("deepseek", "https://api.deepseek.com/v1", "deepseek-chat", _env("DEEPSEEK_API_KEY")),
        ("siliconflow", "https://api.siliconflow.cn/v1", "Qwen/Qwen2.5-7B-Instruct", _env("SILICONFLOW_API_KEY")),
        ("groq", "https://api.groq.com/openai/v1", "llama-3.1-8b-instant", _env("GROQ_API_KEY")),
    ]
    for name, b, m, k in order:
        if k:
            out.append(Provider(name, b.rstrip("/"), m, k))

    if key and not prov:
        out.insert(0, Provider("openrouter", "https://openrouter.ai/api/v1", model or "google/gemma-4-26b-a4b-it:free", key))

    seen: set[str] = set()
    unique: list[Provider] = []
    for p in out:
        if p.name not in seen and p.api_key:
            unique.append(p)
            seen.add(p.name)
    return unique


def provider_status() -> dict[str, Any]:
    providers = configured_providers()
    return {
        "ok": True,
        "ai_enabled": bool(providers),
        "providers": [p.name for p in providers],
        "primary": providers[0].name if providers else None,
        "model": providers[0].model if providers else None,
        "hint": (
            "Добавьте DEEPSEEK_API_KEY в .env (бесплатно: https://platform.deepseek.com) "
            "или GROQ_API_KEY / SILICONFLOW_API_KEY."
            if not providers
            else f"ИИ: {providers[0].name} / {providers[0].model}"
        ),
    }


def _chat_once(provider: Provider, messages: list[dict[str, str]], *, temperature: float = 0.75, max_tokens: int = 800, timeout: float = 60.0) -> str:
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
        headers["X-Title"] = "SvetlyLenormand"

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


# Free OpenRouter models to rotate on 429
_OPENROUTER_FREE_MODELS = [
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-20b:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "poolside/laguna-xs-2.1:free",
]


def chat(user_prompt: str, *, system: str = SYSTEM_PROMPT) -> tuple[str, str, str]:
    """Returns (text, provider_name, model)."""
    import time

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

    # Expand openrouter into several free models
    expanded: list[Provider] = []
    for p in providers:
        if p.name == "openrouter":
            models = list(_OPENROUTER_FREE_MODELS)
            if p.model and p.model not in models:
                models.insert(0, p.model)
            for m in models:
                expanded.append(Provider(p.name, p.base_url, m, p.api_key))
        else:
            expanded.append(p)

    for p in expanded:
        for attempt in range(2):
            try:
                text = _chat_once(p, messages)
                return text, p.name, p.model
            except Exception as e:
                err = str(e)
                errors.append(f"{p.name}/{p.model}: {err[:120]}")
                if "429" in err and attempt == 0:
                    time.sleep(3)
                    continue
                break
    raise RuntimeError("ИИ недоступен: " + " | ".join(errors[:4]))


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
) -> str:
    lines = [
        "Сделай персональный «День по восходящему знаку» на сегодня.",
        f"Восходящий знак: {emoji} {sign}, {degree}° в знаке. Место рождения: {place}.",
        "Опирайся на психологию восходящего знака: как человек встречает мир, стиль дня, общение, тело.",
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
        lines.append("Сшей тон восходящего знака с посланием карты.")
    lines.append(
        "Структура:\n"
        "• Настроение дня (1 строка)\n"
        "• 2 абзаца прогноза\n"
        "• Фокус дня\n"
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
