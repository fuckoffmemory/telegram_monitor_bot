import sqlite3
import os
import json
from config import DB_PATH

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Таблица критериев пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS criteria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        keyword TEXT,
        price_deviation INTEGER DEFAULT 10,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    )''')
    
    # Таблица для кеша цен
    c.execute('''CREATE TABLE IF NOT EXISTS price_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT,
        site TEXT,
        price REAL,
        timestamp INTEGER,
        url TEXT,
        title TEXT,
        UNIQUE(keyword, site, url) ON CONFLICT REPLACE
    )''')
    
    # Таблица для логов
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()
    print(f"✅ База данных инициализирована: {DB_PATH}")

# --- Функции для пользователей ---

def add_user(user_id, username="", first_name=""):
    """Добавляет или обновляет пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Проверяем, существует ли пользователь
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = c.fetchone()
        
        if exists:
            # Обновляем существующего
            c.execute("""
                UPDATE users 
                SET username = ?, first_name = ?, is_active = 1 
                WHERE user_id = ?
            """, (username, first_name, user_id))
        else:
            # Добавляем нового
            c.execute("""
                INSERT INTO users (user_id, username, first_name, is_active) 
                VALUES (?, ?, ?, 1)
            """, (user_id, username, first_name))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка добавления пользователя: {e}")
        return False

def remove_user(user_id):
    """Удаляет пользователя и все его критерии"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM criteria WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка удаления пользователя: {e}")
        return False

def get_all_active_users():
    """Получает всех активных пользователей"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE is_active = 1")
        users = [row[0] for row in c.fetchall()]
        conn.close()
        return users
    except Exception as e:
        print(f"Ошибка получения пользователей: {e}")
        return []

def user_exists(user_id):
    """Проверяет, существует ли пользователь"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = c.fetchone() is not None
        conn.close()
        return exists
    except Exception as e:
        print(f"Ошибка проверки пользователя: {e}")
        return False

def deactivate_user(user_id):
    """Деактивирует пользователя (не удаляет)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка деактивации пользователя: {e}")
        return False

def activate_user(user_id):
    """Активирует пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET is_active = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка активации пользователя: {e}")
        return False

# --- Функции для критериев ---

def add_criteria(user_id, keyword, deviation=10):
    """Добавляет критерий для пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Проверяем, есть ли уже такой критерий
        c.execute("""
            SELECT id FROM criteria 
            WHERE user_id = ? AND keyword = ?
        """, (user_id, keyword.lower().strip()))
        
        exists = c.fetchone()
        
        if exists:
            # Обновляем существующий
            c.execute("""
                UPDATE criteria 
                SET price_deviation = ? 
                WHERE user_id = ? AND keyword = ?
            """, (deviation, user_id, keyword.lower().strip()))
        else:
            # Добавляем новый
            c.execute("""
                INSERT INTO criteria (user_id, keyword, price_deviation) 
                VALUES (?, ?, ?)
            """, (user_id, keyword.lower().strip(), deviation))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка добавления критерия: {e}")
        return False

def get_user_criteria(user_id):
    """Получает все критерии пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT id, keyword, price_deviation 
            FROM criteria 
            WHERE user_id = ? 
            ORDER BY created_at DESC
        """, (user_id,))
        data = c.fetchall()
        conn.close()
        return data  # [(id, keyword, deviation), ...]
    except Exception as e:
        print(f"Ошибка получения критериев: {e}")
        return []

def get_all_criteria():
    """Получает все критерии всех пользователей"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT u.user_id, u.username, c.keyword, c.price_deviation 
            FROM criteria c 
            JOIN users u ON c.user_id = u.user_id 
            WHERE u.is_active = 1
            ORDER BY c.created_at DESC
        """)
        data = c.fetchall()
        conn.close()
        return data
    except Exception as e:
        print(f"Ошибка получения всех критериев: {e}")
        return []

def remove_criteria(criteria_id, user_id):
    """Удаляет критерий по ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM criteria WHERE id = ? AND user_id = ?", (criteria_id, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка удаления критерия: {e}")
        return False

def remove_criteria_by_keyword(user_id, keyword):
    """Удаляет критерий по ключевому слову"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM criteria WHERE user_id = ? AND keyword = ?", (user_id, keyword.lower().strip()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка удаления критерия: {e}")
        return False

def get_criteria_count(user_id):
    """Получает количество критериев у пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM criteria WHERE user_id = ?", (user_id,))
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"Ошибка подсчета критериев: {e}")
        return 0

# --- Функции для кеша цен ---

def save_price_cache(keyword, site, price, url, title):
    """Сохраняет цену в кеш"""
    import time
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Удаляем старые записи (старше 24 часов)
        c.execute("DELETE FROM price_cache WHERE timestamp < ?", (int(time.time()) - 86400,))
        
        # Сохраняем новую запись
        c.execute("""
            INSERT OR REPLACE INTO price_cache (keyword, site, price, timestamp, url, title) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (keyword.lower().strip(), site, price, int(time.time()), url, title[:200]))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка сохранения кеша цен: {e}")

def get_average_price(keyword, site):
    """Получает среднюю цену за последние 24 часа"""
    import time
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT AVG(price) FROM price_cache 
            WHERE keyword = ? AND site = ? AND timestamp > ?
        """, (keyword.lower().strip(), site, int(time.time()) - 86400))
        avg = c.fetchone()[0]
        conn.close()
        return avg if avg else None
    except Exception as e:
        print(f"Ошибка получения средней цены: {e}")
        return None

def get_price_history(keyword, site, hours=24):
    """Получает историю цен за последние N часов"""
    import time
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT price, timestamp, title, url 
            FROM price_cache 
            WHERE keyword = ? AND site = ? AND timestamp > ?
            ORDER BY timestamp DESC
            LIMIT 50
        """, (keyword.lower().strip(), site, int(time.time()) - hours * 3600))
        data = c.fetchall()
        conn.close()
        return data
    except Exception as e:
        print(f"Ошибка получения истории цен: {e}")
        return []

def clear_old_cache(days=7):
    """Очищает старый кеш"""
    import time
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM price_cache WHERE timestamp < ?", (int(time.time()) - days * 86400,))
        conn.commit()
        conn.close()
        print(f"✅ Кеш очищен (старше {days} дней)")
    except Exception as e:
        print(f"Ошибка очистки кеша: {e}")

# --- Функции для логов ---

def log_action(user_id, action):
    """Логирует действие пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO logs (user_id, action) VALUES (?, ?)", (user_id, action))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка логирования: {e}")

def get_user_logs(user_id, limit=50):
    """Получает логи пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT action, timestamp 
            FROM logs 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (user_id, limit))
        data = c.fetchall()
        conn.close()
        return data
    except Exception as e:
        print(f"Ошибка получения логов: {e}")
        return []

# --- Статистика ---

def get_stats():
    """Получает статистику по базе"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Количество пользователей
        c.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        users_count = c.fetchone()[0]
        
        # Количество критериев
        c.execute("SELECT COUNT(*) FROM criteria")
        criteria_count = c.fetchone()[0]
        
        # Количество записей в кеше
        c.execute("SELECT COUNT(*) FROM price_cache")
        cache_count = c.fetchone()[0]
        
        conn.close()
        
        return {
            "users": users_count,
            "criteria": criteria_count,
            "cache_entries": cache_count
        }
    except Exception as e:
        print(f"Ошибка получения статистики: {e}")
        return {"users": 0, "criteria": 0, "cache_entries": 0}

# --- Очистка БД (для админа) ---

def clear_all_data():
    """Очищает все данные (для админа)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM price_cache")
        c.execute("DELETE FROM logs")
        c.execute("DELETE FROM criteria")
        c.execute("DELETE FROM users")
        conn.commit()
        conn.close()
        print("✅ Все данные очищены")
        return True
    except Exception as e:
        print(f"Ошибка очистки данных: {e}")
        return False

# --- Для тестирования ---

if __name__ == "__main__":
    # Тестирование
    init_db()
    
    # Добавляем тестового пользователя
    add_user(123456, "test_user", "Test")
    
    # Добавляем критерий
    add_criteria(123456, "Raf Simons", 10)
    
    # Получаем критерии
    criteria = get_user_criteria(123456)
    print(f"Критерии: {criteria}")
    
    # Получаем статистику
    stats = get_stats()
    print(f"Статистика: {stats}")
