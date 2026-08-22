import sqlite3
import os
import time
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
    
    # Таблица критериев (с max_price в рублях)
    c.execute('''CREATE TABLE IF NOT EXISTS criteria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        keyword TEXT,
        max_price INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    )''')
    
    # Таблица для кеша цен
    c.execute('''CREATE TABLE IF NOT EXISTS price_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT,
        site TEXT,
        price REAL,
        price_rub REAL,
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
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = c.fetchone()
        
        if exists:
            c.execute("""
                UPDATE users 
                SET username = ?, first_name = ?, is_active = 1 
                WHERE user_id = ?
            """, (username, first_name, user_id))
        else:
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

# --- Функции для критериев (с max_price в рублях) ---

def add_criteria(user_id, keyword, max_price_rub):
    """Добавляет критерий с максимальной ценой в рублях"""
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
                SET max_price = ? 
                WHERE user_id = ? AND keyword = ?
            """, (max_price_rub, user_id, keyword.lower().strip()))
        else:
            # Добавляем новый
            c.execute("""
                INSERT INTO criteria (user_id, keyword, max_price) 
                VALUES (?, ?, ?)
            """, (user_id, keyword.lower().strip(), max_price_rub))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка добавления критерия: {e}")
        return False

def get_user_criteria(user_id):
    """Получает все критерии пользователя (id, keyword, max_price_rub)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT id, keyword, max_price 
            FROM criteria 
            WHERE user_id = ? 
            ORDER BY created_at DESC
        """, (user_id,))
        data = c.fetchall()
        conn.close()
        return data  # [(id, keyword, max_price_rub), ...]
    except Exception as e:
        print(f"Ошибка получения критериев: {e}")
        return []

def get_all_criteria():
    """Получает все критерии всех пользователей"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT u.user_id, u.username, c.keyword, c.max_price 
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

# --- Функции для кеша цен (с сохранением в рублях) ---

def save_price_cache(keyword, site, price_cny, url, title, price_rub=None):
    """Сохраняет цену в кеш (в юанях и рублях)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Удаляем старые записи (старше 7 дней)
        c.execute("DELETE FROM price_cache WHERE timestamp < ?", (int(time.time()) - 604800,))
        
        # Если цена в рублях не передана, используем курс по умолчанию
        if price_rub is None:
            price_rub = price_cny * 12.5  # примерный курс
        
        c.execute("""
            INSERT OR REPLACE INTO price_cache (keyword, site, price, price_rub, timestamp, url, title) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            keyword.lower().strip(), 
            site, 
            price_cny, 
            price_rub, 
            int(time.time()), 
            url, 
            title[:200]
        ))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка сохранения кеша цен: {e}")

def get_average_price(keyword, site):
    """Получает среднюю цену за последние 24 часа (в юанях)"""
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

def get_last_items(site, limit=5):
    """Получает последние N товаров с сайта (с ценами в рублях)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT title, price, price_rub, url, site 
            FROM price_cache 
            WHERE site = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (site, limit))
        data = c.fetchall()
        conn.close()
        
        items = []
        for title, price_cny, price_rub, url, site in data:
            items.append({
                "title": title,
                "price_cny": price_cny,
                "price_rub": price_rub,
                "url": url,
                "site": site
            })
        return items
    except Exception as e:
        print(f"Ошибка get_last_items: {e}")
        return []

def get_price_history(keyword, site, hours=24):
    """Получает историю цен за последние N часов"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT price, price_rub, timestamp, title, url 
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
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO logs (user_id, action) VALUES (?, ?)", (user_id, action))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка логирования: {e}")

def get_user_logs(user_id, limit=50):
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
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        users_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM criteria")
        criteria_count = c.fetchone()[0]
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

# --- Очистка БД ---

def clear_all_data():
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

if __name__ == "__main__":
    init_db()
    print("✅ База данных создана/обновлена")
