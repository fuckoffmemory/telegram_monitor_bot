import sqlite3
import os
from config import DB_PATH
import json

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
    
    # Таблица для логов (опционально)
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
        c.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, is_active) 
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

# --- Функции для критериев ---
def add_criteria(user_id, keyword, deviation=10):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
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
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, keyword, price_deviation FROM criteria WHERE user_id = ?", (user_id,))
        data = c.fetchall()
        conn.close()
        return data
    except Exception as e:
        print(f"Ошибка получения критериев: {e}")
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

def get_all_criteria():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT u.user_id, u.username, c.keyword, c.price_deviation 
            FROM criteria c 
            JOIN users u ON c.user_id = u.user_id 
            WHERE u.is_active = 1
        """)
        data = c.fetchall()
        conn.close()
        return data
    except Exception as e:
        print(f"Ошибка получения всех критериев: {e}")
        return []

# --- Кеш цен ---
def save_price_cache(keyword, site, price, url, title):
    import time
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM price_cache WHERE timestamp < ?", (int(time.time()) - 86400,))
        c.execute("""
            INSERT OR REPLACE INTO price_cache (keyword, site, price, timestamp, url, title) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (keyword.lower().strip(), site, price, int(time.time()), url, title))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка сохранения кеша цен: {e}")

def get_average_price(keyword, site):
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

# --- Логирование ---
def log_action(user_id, action):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO logs (user_id, action) VALUES (?, ?)", (user_id, action))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка логирования: {e}")
