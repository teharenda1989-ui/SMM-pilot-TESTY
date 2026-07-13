import sqlite3
import os
from contextlib import contextmanager
from config import Config

# ========== СОЗДАЁМ ПАПКУ ДЛЯ БД ==========
DB_DIR = os.path.dirname(Config.DATABASE_PATH)
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR, exist_ok=True)
    print(f"✅ Создана папка: {DB_DIR}")

DATABASE_PATH = Config.DATABASE_PATH

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Создание всех таблиц"""
    print("🔄 Инициализация БД...")
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Пользователи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    balance REAL DEFAULT 0,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    last_login TIMESTAMP
                )
            ''')
            
            # Настройки ВК
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vk_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    vk_token TEXT,
                    group_id TEXT,
                    is_configured BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    last_post_time TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # Темы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    is_morning BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # Расписание
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    time TEXT NOT NULL,
                    days TEXT DEFAULT 'Ежедневно',
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # История постов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    topic TEXT,
                    text TEXT,
                    status TEXT,
                    cost REAL DEFAULT 0.50,
                    error TEXT,
                    post_id TEXT,
                    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # Платежи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    payment_id TEXT,
                    payment_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # Индексы
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_topics_user_id ON topics(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedule_user_id ON schedule(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_user_id ON posts_history(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)')
            
            conn.commit()
            
            # Создаём администратора
            from werkzeug.security import generate_password_hash
            admin_email = Config.ADMIN_EMAIL
            admin_pass = Config.ADMIN_PASSWORD
            
            cursor.execute('SELECT id FROM users WHERE email = ?', (admin_email,))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO users (email, password_hash, role, balance)
                    VALUES (?, ?, ?, ?)
                ''', (admin_email, generate_password_hash(admin_pass), 'admin', 999999))
                conn.commit()
                print(f"✅ Создан администратор: {admin_email} / {admin_pass}")
            
            print("✅ База данных инициализирована успешно!")
            
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        raise e

def get_user_topics(user_id, is_morning=False):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT topic FROM topics 
            WHERE user_id = ? AND is_morning = ? AND is_active = 1
        ''', (user_id, 1 if is_morning else 0))
        return [row['topic'] for row in cursor.fetchall()]

def get_user_schedule(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT time, days FROM schedule 
            WHERE user_id = ? AND is_active = 1
        ''', (user_id,))
        return [{'time': row['time'], 'days': row['days']} for row in cursor.fetchall()]

def get_vk_settings(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT vk_token, group_id, is_configured, is_active 
            FROM vk_settings WHERE user_id = ?
        ''', (user_id,))
        return cursor.fetchone()

def deduct_post_cost(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        if row and row['balance'] >= 0.50:
            cursor.execute('UPDATE users SET balance = balance - 0.50 WHERE id = ?', (user_id,))
            conn.commit()
            return True
        return False
