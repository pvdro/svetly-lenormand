# Деплой (ничего не крутится на Mac)

Код: https://github.com/pvdro/svetly-lenormand  

## Railway (рекомендуется)

1. Зайти на https://railway.com (GitHub login)
2. New Project → Deploy from GitHub → `svetly-lenormand`
3. Variables:
   - `BOT_TOKEN`
   - `OPENROUTER_API_KEY`
   - `LLM_PROVIDER=openrouter`
   - `LLM_MODEL=google/gemma-4-26b-a4b-it:free`
   - `MINIAPP_URL=https://<твой-домен>.up.railway.app` (после первого деплоя)
4. Generate Domain
5. Redeploy
6. В Telegram: `/start`

## Fly.io

```bash
export PATH="$HOME/.fly/bin:$PATH"
fly auth login
cd ~/Documents/zodiac-content/lenormand-bot
fly launch --no-deploy   # или fly apps create svetly-lenormand
fly volumes create lenormand_data --size 1 --region fra
fly secrets set BOT_TOKEN=... OPENROUTER_API_KEY=... LLM_PROVIDER=openrouter \
  LLM_MODEL=google/gemma-4-26b-a4b-it:free \
  MINIAPP_URL=https://svetly-lenormand.fly.dev
fly deploy
```

## Render free

Blueprint: `render.yaml` в репо.  
New → Blueprint → выбрать репо → задать secrets → Deploy.

На free tier сервис может «засыпать»; webhook разбудит при сообщении в бота.
