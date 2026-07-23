# 🌸 Светлый Ленорман — Telegram-бот

Бесплатный бот на **классической колоде Ленорман (36 карт)**.  
Светлый тон, без paywall, без «страшилок».

## Возможности

| Расклад | Карт | Описание |
|--------|------|----------|
| Карта дня | 1 | Ориентир на день |
| Три карты | 3 | Фон → сейчас → совет |
| Любовь | 3 | Вы / другой / динамика |
| Ситуация | 3 | Суть / скрытое / путь |
| Дело и деньги | 3 | Работа и ресурс |
| Путь | 5 | Развёрнутая история |
| Да / Нет | 1 | Мягкий наклон + совет |
| Справочник | — | Все 36 карт |

## Отличия от референсов

| | Ligmar / Arcanum-подобные | **Светлый Ленорман** |
|--|--|--|
| Система | Таро + ИИ, подписки | **Ленорман**, локальные трактовки |
| Цена | freemium / платные функции | **полностью бесплатно** |
| Тон | часто «мистический/тёмный» UI | **светлый, добрый** |
| ИИ | облачный LLM | rule-based (офлайн, 0 ₽) |

## Mini App

Красивое приложение: `miniapp/` (светлый UI, анимация карт, расклады).

```bash
# 1) раздача статики
.venv/bin/python serve_miniapp.py --port 8877

# 2) HTTPS-туннель (пример: localhost.run)
ssh -R 80:127.0.0.1:8877 nokey@localhost.run
# → в .env: MINIAPP_URL=https://....lhr.life

# 3) бот (кнопка меню + WebApp)
.venv/bin/python main.py
```

## Запуск бота

```bash
cd ~/Documents/zodiac-content/lenormand-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env:
# BOT_TOKEN=...
# MINIAPP_URL=https://your-https-host/

python main.py
```

Откройте [@AstoManiabot](https://t.me/AstoManiabot) → **Start** → **Открыть приложение**.

## Структура

```
lenormand-bot/
  main.py
  bot/
    cards.py      # 36 карт
    spreads.py    # расклады
    handlers.py   # Telegram
    keyboards.py
    texts.py
  .env            # BOT_TOKEN (не коммитить)
```
