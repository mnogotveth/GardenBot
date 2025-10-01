FROM python:3.11-slim

WORKDIR /app

# системные зависимости для asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# приложение
COPY app ./app

# безопасный непривилегированный пользователь
RUN useradd -m appuser
USER appuser

CMD ["python", "-m", "app.bot"]
