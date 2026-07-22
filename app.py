from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import sys
import requests
import pytz

from config import Config
from database import init_db, get_db
# from bot import start_bot   # Бот больше не запускается отсюда

print("=" * 60)
print("🚀 ЗАПУСК APP.PY")
print("=" * 60)

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = 86400

# Инициализация БД
init_db()

# === БОТ БОЛЬШЕ НЕ ЗАПУСКАЕТСЯ ЗДЕСЬ ===

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

# ==================== ФУНКЦИЯ АВТООПРЕДЕЛЕНИЯ ЧАСОВОГО ПОЯСА ====================

def detect_timezone(ip_address=None):
    try:
        if ip_address:
            response = requests.get(f'http://ip-api.com/json/{ip_address}', timeout=5)
        else:
            response = requests.get('http://ip-api.com/json/', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return data.get('timezone', 'Asia/Novosibirsk')
    except:
        pass
    return 'Asia/Novosibirsk'

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
    
    detected_timezone = detect_timezone(request.remote_addr)
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        timezone = request.form.get('timezone', detected_timezone)
        
        if not email or not password:
            flash('Заполните все поля', 'danger')
            return render_template('register.html', detected_timezone=detected_timezone)
        
        if password != password_confirm:
            flash('Пароли не совпадают', 'danger')
            return render_template('register.html', detected_timezone=detected_timezone)
        
        if len(password) < 6:
            flash('Пароль должен быть минимум 6 символов', 'danger')
            return render_template('register.html', detected_timezone=detected_timezone)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
            if cursor.fetchone():
                flash('Пользователь с таким email уже существует', 'danger')
                return render_template('register.html', detected_timezone=detected_timezone)
            
            password_hash = generate_password_hash(password)
            cursor.execute('''
                INSERT INTO users (email, password_hash, balance, timezone, ip_address, detected_timezone)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (email, password_hash, 0.0, timezone, request.remote_addr, detected_timezone))
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
    
    return render_template('register.html', detected_timezone=detected_timezone)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, email, password_hash, role, balance, timezone FROM users WHERE email = ?', (email,))
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
        
        cursor.execute('SELECT balance, email, role, timezone FROM users WHERE id = ?', (session['user_id'],))
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

# ==================== ГРУППЫ VK ====================

@app.route('/groups', methods=['GET', 'POST'])
@login_required
def groups():
    with get_db() as conn:
        cursor = conn.cursor()
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'add':
                vk_token = request.form.get('vk_token')
                group_id = request.form.get('group_id')
                group_name = request.form.get('group_name', 'Группа ВК')
                timezone = request.form.get('timezone', 'Asia/Novosibirsk')
                
                if not vk_token or not group_id:
                    flash('Заполните все поля', 'danger')
                    return redirect(url_for('groups'))
                
                try:
                    import vk_api
                    vk_session = vk_api.VkApi(token=vk_token)
                    vk = vk_session.get_api()
                    info = vk.groups.getById(group_id=group_id)
                    group_name = info[0]['name']
                    is_configured = 1
                except Exception as e:
                    flash(f'Ошибка подключения к VK: {str(e)}', 'danger')
                    is_configured = 0
                
                cursor.execute('''
                    INSERT INTO vk_settings (user_id, vk_token, group_id, group_name, is_configured, is_active, timezone)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (session['user_id'], vk_token, group_id, group_name, is_configured, 1, timezone))
                conn.commit()
                flash(f'✅ Группа "{group_name}" добавлена!', 'success')
            
            elif action == 'delete':
                group_id_db = request.form.get('group_id_db')
                cursor.execute('DELETE FROM vk_settings WHERE id = ? AND user_id = ?', 
                              (group_id_db, session['user_id']))
                conn.commit()
                flash('Группа удалена', 'info')
            
            elif action == 'toggle':
                group_id_db = request.form.get('group_id_db')
                cursor.execute('''
                    UPDATE vk_settings SET is_active = NOT is_active WHERE id = ? AND user_id = ?
                ''', (group_id_db, session['user_id']))
                conn.commit()
                flash('Статус группы изменён', 'success')
            
            return redirect(url_for('groups'))
        
        cursor.execute('SELECT * FROM vk_settings WHERE user_id = ?', (session['user_id'],))
        groups_list = cursor.fetchall()
    
    return render_template('groups.html', groups=groups_list)

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

@app.route('/api/test-vk-group/<int:group_id_db>', methods=['GET'])
@login_required
def test_vk_group(group_id_db):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT vk_token, group_id FROM vk_settings WHERE id = ? AND user_id = ?', 
                      (group_id_db, session['user_id']))
        group = cursor.fetchone()
        
        if not group:
            return jsonify({'success': False, 'message': 'Группа не найдена'}), 404
        
        try:
            import vk_api
            vk_session = vk_api.VkApi(token=group['vk_token'])
            vk = vk_session.get_api()
            info = vk.groups.getById(group_id=group['group_id'])
            return jsonify({
                'success': True,
                'message': f'✅ Группа "{info[0]["name"]}" доступна'
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'❌ Ошибка: {str(e)}'
            }), 400

# ==================== ТЕМЫ (ИСПРАВЛЕННАЯ ВЕРСИЯ) ====================

@app.route('/topics', methods=['GET', 'POST'])
@login_required
def topics():
    with get_db() as conn:
        cursor = conn.cursor()
        
        if request.method == 'POST':
            topics_bulk = request.form.get('topics_bulk', '').strip()
            is_morning = request.form.get('is_morning', '0')
            
            if topics_bulk:
                import re
                topics_list = re.split(r'[,\n]+', topics_bulk)
                topics_list = [t.strip() for t in topics_list if t.strip()]
                
                added_count = 0
                for topic in topics_list:
                    cursor.execute('''
                        SELECT id FROM topics 
                        WHERE user_id = ? AND topic = ? AND is_morning = ?
                    ''', (session['user_id'], topic, int(is_morning)))
                    
                    if not cursor.fetchone():
                        cursor.execute('''
                            INSERT INTO topics (user_id, topic, is_morning)
                            VALUES (?, ?, ?)
                        ''', (session['user_id'], topic, int(is_morning)))
                        added_count += 1
                
                conn.commit()
                flash(f'✅ Добавлено {added_count} новых тем!', 'success')
            else:
                flash('⚠️ Введите хотя бы одну тему', 'warning')
            
            return redirect(url_for('topics'))
        
        cursor.execute('SELECT * FROM topics WHERE user_id = ? AND is_morning = 0 AND is_active = 1 ORDER BY id', 
                      (session['user_id'],))
        topics_list = cursor.fetchall()
        
        cursor.execute('SELECT * FROM topics WHERE user_id = ? AND is_morning = 1 AND is_active = 1 ORDER BY id', 
                      (session['user_id'],))
        morning_list = cursor.fetchall()
    
    return render_template('topics.html', 
                         topics=topics_list, 
                         morning_topics=morning_list,
                         groups=[])

@app.route('/clear-topics', methods=['POST'])
@login_required
def clear_topics():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM topics WHERE user_id = ? AND is_morning = 0', (session['user_id'],))
        conn.commit()
    flash('🗑️ Все темы удалены', 'info')
    return redirect(url_for('topics'))

@app.route('/clear-morning-topics', methods=['POST'])
@login_required
def clear_morning_topics():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM topics WHERE user_id = ? AND is_morning = 1', (session['user_id'],))
        conn.commit()
    flash('🗑️ Все утренние темы удалены', 'info')
    return redirect(url_for('topics'))

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
            
            cursor.execute('DELETE FROM schedule WHERE user_id = ?', (session['user_id'],))
            
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
            flash(f'✅ Расписание обновлено! Добавлено {len(times)} времен публикации!', 'success')
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

@app.route('/clear-schedule', methods=['POST'])
@login_required
def clear_schedule():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM schedule WHERE user_id = ?', (session['user_id'],))
        conn.commit()
    flash('🗑️ Всё расписание удалено', 'info')
    return redirect(url_for('schedule'))

# ==================== ИСТОРИЯ ====================

@app.route('/history')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as total FROM posts_history WHERE user_id = ?', (session['user_id'],))
        total = cursor.fetchone()['total']
        
        cursor.execute('''
            SELECT * FROM posts_history 
            WHERE user_id = ? 
            ORDER BY published_at DESC
            LIMIT ? OFFSET ?
        ''', (session['user_id'], per_page, offset))
        history_list = cursor.fetchall()
        
        cursor.execute('''
            SELECT COALESCE(SUM(cost), 0) as total FROM posts_history 
            WHERE user_id = ? AND status = 'published'
        ''', (session['user_id'],))
        total_cost = cursor.fetchone()['total']
    
    return render_template('history.html', 
                         history=history_list, 
                         total_cost=total_cost,
                         page=page,
                         total=total,
                         per_page=per_page,
                         total_pages=(total + per_page - 1) // per_page if total > 0 else 1)

@app.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM posts_history WHERE user_id = ?', (session['user_id'],))
        conn.commit()
    flash('История очищена', 'info')
    return redirect(url_for('history'))

# ==================== БАЛАНС ====================

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

# ==================== АДМИНКА ====================

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

# ==================== ЧАСОВОЙ ПОЯС ====================

@app.route('/timezone', methods=['GET', 'POST'])
@login_required
def timezone_settings():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT timezone FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        current_timezone = user['timezone'] if user else 'Asia/Novosibirsk'
        
        if request.method == 'POST':
            new_timezone = request.form.get('timezone')
            
            if new_timezone:
                cursor.execute('''
                    UPDATE users SET timezone = ? WHERE id = ?
                ''', (new_timezone, session['user_id']))
                conn.commit()
                flash(f'✅ Часовой пояс изменён на {new_timezone}', 'success')
                return redirect(url_for('timezone_settings'))
        
        timezones = [
            ('UTC', 'UTC (Всемирное координированное время)'),
            ('Europe/Moscow', 'Москва (UTC+3)'),
            ('Europe/Volgograd', 'Волгоград (UTC+4)'),
            ('Asia/Yekaterinburg', 'Екатеринбург (UTC+5)'),
            ('Asia/Omsk', 'Омск (UTC+6)'),
            ('Asia/Novosibirsk', 'Новосибирск (UTC+7) — по умолчанию'),
            ('Asia/Krasnoyarsk', 'Красноярск (UTC+7)'),
            ('Asia/Irkutsk', 'Иркутск (UTC+8)'),
            ('Asia/Yakutsk', 'Якутск (UTC+9)'),
            ('Asia/Vladivostok', 'Владивосток (UTC+10)'),
            ('Asia/Magadan', 'Магадан (UTC+11)'),
            ('Asia/Kamchatka', 'Камчатка (UTC+12)'),
        ]
        
        try:
            tz = pytz.timezone(current_timezone)
            current_time = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
        except:
            current_time = 'Ошибка определения времени'
    
    return render_template('timezone.html', 
                         current_timezone=current_timezone,
                         timezones=timezones,
                         current_time=current_time)

# ==================== ЗАПУСК ====================

print("=" * 60)
print("✅ Приложение загружено, запускаю сервер...")
print("=" * 60)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)
