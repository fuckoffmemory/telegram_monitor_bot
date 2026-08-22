import os

# Твой Telegram ID (узнай у @userinfobot)
ADMIN_ID = 123456789  # ЗАМЕНИ НА СВОЙ ID

# Токен бота от @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Настройки прокси (если нужен)
PROXY_CONFIG = {
    # "server": os.getenv("PROXY_SERVER", ""),
    # "username": os.getenv("PROXY_USERNAME", ""),
    # "password": os.getenv("PROXY_PASSWORD", ""),
}

# Время проверки (в секундах) — можно менять через переменные окружения
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 300))

# Путь к БД (для Railway лучше использовать /tmp или PostgreSQL)
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "database.db"))

# Режим отладки
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
