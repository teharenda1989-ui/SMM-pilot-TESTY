from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import sys

from config import Config
from database import init_db, get_db
from bot import start_bot

print("=" * 60)
print("🚀 ЗАПУСК APP.PY")
print("=" * 60)

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = 86400

# Инициализация БД
init_db()

# Запуск бота
start_bot()

# ==================== ДЕКОРАТОРЫ ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
            user = cursor.fetchone()
            if not user or user['role'] != 'admin':
                flash('Доступ запрещён', 'danger')
                return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== HEALTH CHECK ====================

@app.route('/health')
def health():
    return {"status": "ok", "message": "SMM Пилот работает"}, 200

# ==================== ОСНОВНЫЕ РОУТЫ ====================

@app.route('/')
def index():
    return render_template('index.html', 
                         logged_in=('user_id' in session),
                         post_price=Config.POST_PRICE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        if not email or not password:
            flash('Заполните все поля', 'danger')
            return render_template('register.html')
        
        if password != password_confirm:
            flash('Пароли не совпадают', 'danger')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Пароль должен быть минимум 6 символов', 'danger')
            return render_template('register.html')
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
            if cursor.fetchone():
                flash('Пользователь с таким email уже существует', 'danger')
                return render_template('register.html')
            
            password_hash = generate_password_hash(password)
            cursor.execute('''
                INSERT INTO users (email, password_hash, balance)
                VALUES (?, ?, ?)
            ''', (email, password_hash, 0.0))
            conn.commit()
            user_id = cursor.lastrowid
            
            # Дефолтное расписание
            default_schedule = []
            for hour in range(10, 23):
                default_schedule.append(f"{hour:02d}:00")
                if hour != 22:
                    default_schedule.append(f"{hour:02d}:30")
            
            for time in default_schedule:
                cursor.execute('''
                    INSERT INTO schedule (user_id, time, days)
                    VALUES (?, ?, ?)
                ''', (user_id, time, 'Ежедневно'))
            
            # Дефолтные темы
            default_topics = [
                "Как открыть ИП в России: пошаговая инструкция",
                "Самозанятость или ИП: что выбрать в 2026",
                "Как получить кредит для бизнеса в России",
                "Налоговые льготы для малого бизнеса в 2026",
                "Как найти первых клиентов в B2B сегменте",
            ]
            for topic in default_topics:
                cursor.execute('''
                    INSERT INTO topics (user_id, topic, is_morning)
                    VALUES (?, ?, ?)
                ''', (user_id, topic, 0))
            
            morning_topics = [
                "Доброе утро, предприниматели! ☀️ Начинаем новый день с позитива!",
                "Доброе утро! ☀️ Сегодня отличный день для новых свершений!",
            ]
            for topic in morning_topics:
                cursor.execute('''
                    INSERT INTO topics (user_id, topic, is_morning)
                    VALUES (?, ?, ?)
                ''', (user_id, topic, 1))
            
            conn.commit()
        
        flash('Регистрация успешна! Войдите в систему', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, email, password_hash, role, balance FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['email'] = user['email']
                session['role'] = user['role']
                session['balance'] = user['balance']
                session.permanent = True
                
                cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
                conn.commit()
                
                flash('Добро пожаловать!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Неверный email или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance, email, role FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        
        cursor.execute('SELECT is_configured, is_active, group_id FROM vk_settings WHERE user_id = ?', (session['user_id'],))
        vk_settings = cursor.fetchone()
        
        cursor.execute('SELECT COUNT(*) as total FROM posts_history WHERE user_id = ?', (session['user_id'],))
        total_posts = cursor.fetchone()['total']
        
        cursor.execute('SELECT COUNT(*) as total FROM topics WHERE user_id = ? AND is_morning = 0 AND is_active = 1', (session['user_id'],))
        total_topics = cursor.fetchone()['total']
        
        cursor.execute('SELECT COUNT(*) as total FROM schedule WHERE user_id = ? AND is_active = 1', (session['user_id'],))
        total_schedule = cursor.fetchone()['total']
        
        cursor.execute('''
            SELECT COUNT(*) as total FROM posts_history 
            WHERE user_id = ? AND status = 'published' 
            AND date(published_at) = date('now')
        ''', (session['user_id'],))
        today_posts = cursor.fetchone()['total']
        
        cursor.execute('''
            SELECT text, topic, status, published_at, cost, post_id 
            FROM posts_history 
            WHERE user_id = ? 
            ORDER BY published_at DESC 
            LIMIT 5
        ''', (session['user_id'],))
        recent_posts = cursor.fetchall()
    
    return render_template('dashboard.html',
                         user=user,
                         vk_settings=vk_settings,
                         total_posts=total_posts,
                         total_topics=total_topics,
                         total_schedule=total_schedule,
                         today_posts=today_posts,
                         recent_posts=recent_posts,
                         post_price=Config.POST_PRICE)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    with get_db() as conn:
        cursor = conn.cursor()
        
        if request.method == 'POST':
            vk_token = request.form.get('vk_token')
            group_id = request.form.get('group_id')
            is_active = request.form.get('is_active', '1')
            
            if not vk_token or not group_id:
                flash('Заполните все поля', 'danger')
                return redirect(url_for('settings'))
            
            try:
                import vk_api
                vk_session = vk_api.VkApi(token=vk_token)
                vk = vk_session.get_api()
                vk.groups.getById(group_id=group_id)
                is_configured = 1
            except Exception as e:
                flash(f'Ошибка подключения к VK: {str(e)}', 'danger')
                is_configured = 0
            
            cursor.execute('''
                INSERT INTO vk_settings (user_id, vk_token, group_id, is_configured, is_active)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    vk_token = excluded.vk_token,
                    group_id = excluded.group_id,
                    is_configured = excluded.is_configured,
                    is_active = excluded.is_active
            ''', (session['user_id'], vk_token, group_id, is_configured, int(is_active)))
            conn.commit()
            
            flash('Настройки сохранены!', 'success')
            return redirect(url_for('settings'))
        
        cursor.execute('SELECT * FROM vk_settings WHERE user_id = ?', (session['user_id'],))
        settings_data = cursor.fetchone()
    
    return render_template('settings.html', vk_settings=settings_data)

@app.route('/api/test-vk', methods=['POST'])
@login_required
def test_vk():
    data = request.json
    vk_token = data.get('vk_token')
    group_id = data.get('group_id')
    
    try:
        import vk_api
        vk_session = vk_api.VkApi(token=vk_token)
        vk = vk_session.get_api()
        info = vk.groups.getById(group_id=group_id)
        return jsonify({
            'success': True,
            'message': f'Группа {info[0]["name"]} доступна'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

@app.route('/topics', methods=['GET', 'POST'])
@login_required
def topics():
    with get_db() as conn:
        cursor = conn.cursor()
        
        if request.method == 'POST':
            topic = request.form.get('topic')
            is_morning = request.form.get('is_morning', '0')
            
            if topic:
                cursor.execute('''
                    INSERT INTO topics (user_id, topic, is_morning)
                    VALUES (?, ?, ?)
                ''', (session['user_id'], topic, int(is_morning)))
                conn.commit()
                flash('Тема добавлена!', 'success')
            else:
                flash('Введите тему', 'danger')
            
            return redirect(url_for('topics'))
        
        cursor.execute('SELECT * FROM topics WHERE user_id = ? AND is_morning = 0 AND is_active = 1 ORDER BY id', 
                      (session['user_id'],))
        topics_list = cursor.fetchall()
        
        cursor.execute('SELECT * FROM topics WHERE user_id = ? AND is_morning = 1 AND is_active = 1 ORDER BY id', 
                      (session['user_id'],))
        morning_list = cursor.fetchall()
    
    return render_template('topics.html', 
                         topics=topics_list, 
                         morning_topics=morning_list)

@app.route('/delete-topic/<int:topic_id>', methods=['POST'])
@login_required
def delete_topic(topic_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM topics WHERE id = ? AND user_id = ?', 
                      (topic_id, session['user_id']))
        conn.commit()
    flash('Тема удалена', 'info')
    return redirect(request.referrer or url_for('topics'))

# ==================== РАСПИСАНИЕ ====================

@app.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule():
    with get_db() as conn:
        cursor = conn.cursor()
        
        if request.method == 'POST':
            start_time = request.form.get('start_time', '10:00')
            end_time = request.form.get('end_time', '22:00')
            interval_minutes = int(request.form.get('interval_minutes', 30))
            days_of_week = request.form.get('days_of_week', 'all')
            days = request.form.get('days', 'Ежедневно')
            
            from datetime import datetime, timedelta
            
            start_dt = datetime.strptime(start_time, '%H:%M')
            end_dt = datetime.strptime(end_time, '%H:%M')
            
            times = []
            current = start_dt
            while current <= end_dt:
                times.append(current.strftime('%H:%M'))
                current += timedelta(minutes=interval_minutes)
            
            for time in times:
                cursor.execute('''
                    INSERT INTO schedule (user_id, time, days, start_time, end_time, interval_minutes, days_of_week)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (session['user_id'], time, days, start_time, end_time, interval_minutes, days_of_week))
            
            conn.commit()
            flash(f'✅ Добавлено {len(times)} времен публикации!', 'success')
            return redirect(url_for('schedule'))
        
        cursor.execute('SELECT * FROM schedule WHERE user_id = ? AND is_active = 1 ORDER BY time', 
                      (session['user_id'],))
        schedule_list = cursor.fetchall()
    
    return render_template('schedule.html', schedule=schedule_list)

@app.route('/delete-schedule/<int:schedule_id>', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM schedule WHERE id = ? AND user_id = ?', 
                      (schedule_id, session['user_id']))
        conn.commit()
    flash('Время удалено', 'info')
    return redirect(request.referrer or url_for('schedule'))

@app.route('/reset-schedule', methods=['POST'])
@login_required
def reset_schedule():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM schedule WHERE user_id = ?', (session['user_id'],))
        
        default_schedule = []
        for hour in range(10, 23):
            default_schedule.append(f"{hour:02d}:00")
            if hour != 22:
                default_schedule.append(f"{hour:02d}:30")
        
        for time in default_schedule:
            cursor.execute('''
                INSERT INTO schedule (user_id, time, days)
                VALUES (?, ?, ?)
            ''', (session['user_id'], time, 'Ежедневно'))
        
        conn.commit()
    flash('Расписание восстановлено', 'success')
    return redirect(url_for('schedule'))

@app.route('/history')
@login_required
def history():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM posts_history 
            WHERE user_id = ? 
            ORDER BY published_at DESC
        ''', (session['user_id'],))
        history_list = cursor.fetchall()
        
        cursor.execute('''
            SELECT COALESCE(SUM(cost), 0) as total FROM posts_history 
            WHERE user_id = ? AND status = 'published'
        ''', (session['user_id'],))
        total_cost = cursor.fetchone()['total']
    
    return render_template('history.html', 
                         history=history_list, 
                         total_cost=total_cost)

@app.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM posts_history WHERE user_id = ?', (session['user_id'],))
        conn.commit()
    flash('История очищена', 'info')
    return redirect(url_for('history'))

@app.route('/balance', methods=['GET', 'POST'])
@login_required
def balance():
    with get_db() as conn:
        cursor = conn.cursor()
        
        if request.method == 'POST':
            try:
                amount = float(request.form.get('amount', 0))
                
                if amount < 10:
                    flash('Минимальная сумма 10 ₽', 'danger')
                    return redirect(url_for('balance'))
                
                cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', 
                              (amount, session['user_id']))
                conn.commit()
                
                session['balance'] += amount
                
                cursor.execute('''
                    INSERT INTO payments (user_id, amount, status)
                    VALUES (?, ?, ?)
                ''', (session['user_id'], amount, 'success'))
                conn.commit()
                
                flash(f'Баланс пополнен на {amount:.2f} ₽', 'success')
                return redirect(url_for('balance'))
                
            except ValueError:
                flash('Введите корректную сумму', 'danger')
        
        cursor.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        
        cursor.execute('SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT 20', 
                      (session['user_id'],))
        payments = cursor.fetchall()
    
    return render_template('balance.html', 
                         user=user, 
                         payments=payments,
                         post_price=Config.POST_PRICE)

@app.route('/admin')
@admin_required
def admin_panel():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as total FROM users')
        total_users = cursor.fetchone()['total']
        
        cursor.execute('SELECT COUNT(*) as total FROM posts_history WHERE status = "published"')
        total_posts = cursor.fetchone()['total']
        
        cursor.execute('SELECT SUM(amount) as total FROM payments WHERE status = "success"')
        total_revenue = cursor.fetchone()['total'] or 0
        
        cursor.execute('''
            SELECT id, email, balance, role, created_at, last_login 
            FROM users 
            ORDER BY created_at DESC
        ''')
        users = cursor.fetchall()
    
    return render_template('admin.html',
                         total_users=total_users,
                         total_posts=total_posts,
                         total_revenue=total_revenue,
                         users=users)

@app.route('/admin/user/<int:user_id>/toggle', methods=['POST'])
@admin_required
def admin_toggle_user(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET is_active = NOT is_active WHERE id = ?
        ''', (user_id,))
        conn.commit()
    flash('Статус пользователя изменён', 'success')
    return redirect(url_for('admin_panel'))

print("=" * 60)
print("✅ Приложение загружено, запускаю сервер...")
print("=" * 60)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)
