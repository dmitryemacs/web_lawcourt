FROM python:3.11-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive
# Установим минимально необходимое, уберём кэш apt после установки
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      gcc \
      libpq-dev \
      ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем содержимое директории app в рабочую директорию
COPY ./app/ /app/

# Устанавливаем переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Копируем статические файлы
COPY ./static /app/static

EXPOSE 8000

# Команда запуска - работаем в директории /app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
