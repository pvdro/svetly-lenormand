FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    HOST=0.0.0.0

WORKDIR /app

# system deps for pyswisseph build if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# persist sqlite if volume mounted
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8080

# Единый процесс: Mini App + API + Telegram webhook
CMD ["python", "app_server.py"]
