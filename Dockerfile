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

# SQLite data directory (Railway Volume optional, attach separately if needed)
RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 8080

# Веб (приложение) + бот (long polling — надёжнее, если веб снаружи режется)
CMD ["python", "start.py"]

# rebuild 20260723182415
