# Open в списке чатов (как у Арканума)

Кнопка **Open** в превью среди каналов/чатов — это **Main Mini App**.  
Её **нельзя** включить только через Bot API (`setChatMenuButton` даёт кнопку у поля ввода, но не в ленте).

## Включить (1 минута)

1. Открой [@BotFather](https://t.me/BotFather)
2. Команда: `/mybots`
3. Выбери **@AstoManiabot**
4. **Bot Settings**
5. **Configure Mini App**
6. **Enable Mini App**
7. Отправь URL:

```
https://pvdro.github.io/svetly-lenormand/
```

8. (Опционально) **Menu Button** → тоже этот URL, текст `Open`

## Проверка

- Перезапусти Telegram (или свайпни вниз список чатов)
- В ленте у **Астромания** справа должна быть белая **Open**
- В API: `getMe` → `"has_main_web_app": true`

## URL приложения

Тот же, что `MINIAPP_URL` на Railway (GitHub Pages).
