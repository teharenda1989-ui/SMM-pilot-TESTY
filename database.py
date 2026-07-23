import sqlite3
import os
from contextlib import contextmanager
from config import Config

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
                    last_login TIMESTAMP,
                    timezone TEXT DEFAULT 'Asia/Novosibirsk',
                    ip_address TEXT,
                    detected_timezone TEXT
                )
            ''')
            
            # Добавляем колонки если их нет
            for col in ['timezone', 'ip_address', 'detected_timezone']:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
                except:
                    pass
            
            # Настройки ВК
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vk_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    vk_token TEXT,
                    group_id TEXT,
                    group_name TEXT,
                    is_configured BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    last_post_time TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    timezone TEXT DEFAULT 'Asia/Novosibirsk',
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            try:
                cursor.execute("ALTER TABLE vk_settings ADD COLUMN timezone TEXT DEFAULT 'Asia/Novosibirsk'")
            except:
                pass
            
            # Темы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    group_id INTEGER,
                    topic TEXT NOT NULL,
                    is_morning BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (group_id) REFERENCES vk_settings(id) ON DELETE CASCADE
                )
            ''')
            
            try:
                cursor.execute("ALTER TABLE topics ADD COLUMN group_id INTEGER REFERENCES vk_settings(id)")
            except:
                pass
            
            # Расписание
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    group_id INTEGER,
                    time TEXT NOT NULL,
                    days TEXT DEFAULT 'Ежедневно',
                    is_active BOOLEAN DEFAULT 1,
                    start_time TEXT DEFAULT '10:00',
                    end_time TEXT DEFAULT '22:00',
                    interval_minutes INTEGER DEFAULT 30,
                    days_of_week TEXT DEFAULT 'all',
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (group_id) REFERENCES vk_settings(id) ON DELETE CASCADE
                )
            ''')
            
            try:
                cursor.execute("ALTER TABLE schedule ADD COLUMN group_id INTEGER REFERENCES vk_settings(id)")
            except:
                pass
            
            for col in ['start_time', 'end_time', 'interval_minutes', 'days_of_week']:
                try:
                    cursor.execute(f"ALTER TABLE schedule ADD COLUMN {col} TEXT")
                except:
                    pass
            
            # История постов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    group_id INTEGER,
                    topic TEXT,
                    text TEXT,
                    status TEXT,
                    cost REAL DEFAULT 0.50,
                    error TEXT,
                    post_id TEXT,
                    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (group_id) REFERENCES vk_settings(id) ON DELETE CASCADE
                )
            ''')
            
            try:
                cursor.execute("ALTER TABLE posts_history ADD COLUMN group_id INTEGER REFERENCES vk_settings(id)")
            except:
                pass
            
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
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_topics_group_id ON topics(group_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedule_user_id ON schedule(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedule_group_id ON schedule(group_id)')
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
                    INSERT INTO users (email, password_hash, role, balance, timezone)
                    VALUES (?, ?, ?, ?, ?)
                ''', (admin_email, generate_password_hash(admin_pass), 'admin', 999999, 'Asia/Novosibirsk'))
                conn.commit()
                print(f"✅ Создан администратор: {admin_email} / {admin_pass}")
            
            print("✅ База данных инициализирована успешно!")
            
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        raise e

def get_user_topics(user_id, group_id=None, is_morning=False):
    with get_db() as conn:
        cursor = conn.cursor()
        if group_id:
            cursor.execute('''
                SELECT topic FROM topics 
                WHERE user_id = ? AND (group_id = ? OR group_id IS NULL) AND is_morning = ? AND is_active = 1
            ''', (user_id, group_id, 1 if is_morning else 0))
        else:
            cursor.execute('''
                SELECT topic FROM topics 
                WHERE user_id = ? AND group_id IS NULL AND is_morning = ? AND is_active = 1
            ''', (user_id, 1 if is_morning else 0))
        return [row['topic'] for row in cursor.fetchall()]

def get_user_schedule(user_id, group_id=None):
    with get_db() as conn:
        cursor = conn.cursor()
        if group_id:
            cursor.execute('''
                SELECT id, time, days, start_time, end_time, interval_minutes, days_of_week 
                FROM schedule 
                WHERE user_id = ? AND (group_id = ? OR group_id IS NULL) AND is_active = 1
                ORDER BY time
            ''', (user_id, group_id))
        else:
            cursor.execute('''
                SELECT id, time, days, start_time, end_time, interval_minutes, days_of_week 
                FROM schedule 
                WHERE user_id = ? AND group_id IS NULL AND is_active = 1
                ORDER BY time
            ''', (user_id,))
        return cursor.fetchall()

def get_user_groups(user_id, group_id=None):
    with get_db() as conn:
        cursor = conn.cursor()
        if group_id:
            cursor.execute('''
                SELECT id, vk_token, group_id, group_name, is_configured, is_active, timezone
                FROM vk_settings 
                WHERE user_id = ? AND id = ? AND is_configured = 1 AND is_active = 1
            ''', (user_id, group_id))
            return cursor.fetchone()
        else:
            cursor.execute('''
                SELECT id, vk_token, group_id, group_name, is_configured, is_active, timezone
                FROM vk_settings 
                WHERE user_id = ? AND is_configured = 1 AND is_active = 1
            ''', (user_id,))
            return cursor.fetchall()

def get_user_timezone(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT timezone FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if user and user['timezone']:
            return user['timezone']
        return 'Asia/Novosibirsk'

def get_group_timezone(group_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT timezone FROM vk_settings WHERE id = ?', (group_id,))
        group = cursor.fetchone()
        if group and group['timezone']:
            return group['timezone']
        return 'Asia/Novosibirsk'

def get_vk_settings(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT vk_token, group_id, is_configured, is_active, timezone
            FROM vk_settings 
            WHERE user_id = ? AND is_active = 1
            LIMIT 1
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
