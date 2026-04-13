# Деплой на Render / Railway

## 🚀 Вариант 1: Render (рекомендуется)

### Автоматический деплой через render.yaml

1. Зарегистрируйтесь на [render.com](https://render.com)
2. Подключите GitHub аккаунт
3. Нажмите **New +** → **Blueprint**
4. Выберите репозиторий `web_university`
5. Render автоматически создаст:
   - Web сервис (Docker)
   - PostgreSQL базу данных
6. Нажмите **Apply**

### Ручной деплой

1. **New +** → **Web Service**
2. Подключите репозиторий
3. Настройки:
   - **Environment:** Docker
   - **Plan:** Free
   - **Health Check Path:** `/health`
4. Добавьте переменную окружения:
   ```
   DATABASE_URL=postgresql+psycopg2://<user>:<password>@<host>:5432/university
   ```
   (Render автоматически подставит URL из подключённой БД)
5. Создайте **PostgreSQL** базу данных и подключите к сервису

---

## 🚀 Вариант 2: Railway

### Деплой через GitHub

1. Зарегистрируйтесь на [railway.app](https://railway.app)
2. Нажмите **New Project** → **Deploy from GitHub repo**
3. Выберите репозиторий `web_university`
4. Railway автоматически:
   - Создаст PostgreSQL базу
   - Подставит `DATABASE_URL`
   - Запустит приложение

### Ручной деплой

```bash
# Установите Railway CLI
npm i -g @railway/cli

# Авторизуйтесь
railway login

# Инициализируйте проект
railway init

# Создайте PostgreSQL
railway add postgresql

# Деплой
railway up
```

---

## ⚙️ Переменные окружения

| Переменная | Описание | Пример |
|-----------|---------|-------|
| `DATABASE_URL` | URL базы данных | `postgresql+psycopg2://...` |

---

## 📁 Структура

```
web_university/
├── Dockerfile           # Для локальной разработки
├── Dockerfile.prod      # Для продакшена (Render/Railway)
├── render.yaml          # Конфигурация Render
├── railway.json         # Конфигурация Railway
├── requirements.txt     # Python зависимости
├── docker-compose.yml   # Локальный запуск
└── app/
    ├── main.py          # Основной код приложения
    ├── models.py        # Модели SQLAlchemy
    ├── database.py      # Подключение к БД
    ├── templates/       # Jinja2 шаблоны
    └── static/          # Статические файлы
```

---

## 🔧 После деплоя

1. Войдите как судья (код: `judge123`) или как сотрудник
2. Создайте отделы, предметы, курсы
3. Загрузите тестовые данные (кнопка в навбаре)
4. Загружайте файлы к курсам, тестам, делам

---

## ⚠️ Важно

- **Free план Render:** сервис засыпает через 15 мин бездействия
- **Railway:** $5 кредитов/мес бесплатно
- Загруженные файлы хранятся в контейнере — при перезапуске они сохранятся (persistent disk)
- Для production замените `secret_key` в `SessionMiddleware`
