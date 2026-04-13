#!/bin/bash
set -e

# Создаём директорию для загруженных файлов
mkdir -p /app/uploads

# Запускаем приложение
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
