import os
import time
import threading
import requests
import vk_api
from datetime import datetime, timezone, timedelta
import random
from dotenv import load_dotenv

from config import Config
from database import get_db, deduct_post_cost, get_user_topics, get_user_schedule, get_vk_settings

load_dotenv()

# Настройки
YANDEX_FOLDER_ID = Config.YANDEX_FOLDER_ID
YANDEX_API_KEY = Config.YANDEX_API_KEY
POST_PRICE = Config.POST_PRICE

# Временная зона
NOVOSIBIRSK_TZ = timezone(timedelta(hours=7))

def get_novosibirsk_time():
    return datetime.now(timezone.utc).astimezone(NOVOSIBIRSK_TZ)

def generate_text(topic, style='информативный'):
    try:
        if topic.startswith("Доброе утро"):
            return topic + " 🚀"
        
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""
        Напиши развернутый, полезный пост для ВКонтакте на тему: "{topic}".
        Стиль: {style}.
        
        ТРЕБОВАНИЯ:
        1. Длина: 5-8 предложений
        2. Начни с вовлекающего вопроса или факта
        3. Используй эмодзи (минимум 3-4 штуки)
        4. Добавь конкретные советы или рекомендации
        5. Закончи вопросом для комментариев
        6. Добавь 5-7 хештегов в конце
        7. Пиши на русском языке
        """
        
        data = {
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
            "completionOptions": {
                "temperature": 0.8,
                "maxTokens": 800
            },
            "messages": [
                {"role": "system", "text": "Ты профессиональный SMM-копирайтер."},
                {"role": "user", "text": prompt}
            ]
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=60)
        result = response.json()
        
        if 'error' in result:
            return f"❌ Ошибка: {result['error']['message']}"
        
        return result['result']['alternatives'][0]['message']['text'].strip()
    except Exception as e:
        return f"❌ Ошибка: {e}"

def publish_post(vk_token, group_id, text):
    try:
        vk_session = vk_api.VkApi(token=vk_token)
        vk = vk_session.get_api()
        
        post_params = {
            'owner_id': f"-{group_id}",
            'message': text,
            'from_group': 1
        }
        
        response = vk.wall.post(**post_params)
        return response['post_id']
    except Exception as e:
        raise e

def process_user(user_id):
    try:
        vk_settings = get_vk_settings(user_id)
        if not vk_settings or not vk_settings['is_configured'] or not vk_settings['is_active']:
            return
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            if not user or user['balance'] < POST_PRICE:
                return
        
        now = get_novosibirsk_time()
        current_time = now.strftime("%H:%M")
        
        schedule = get_user_schedule(user_id)
        if not schedule:
            return
        
        scheduled_times = [item['time'] for item in schedule]
        if current_time not in scheduled_times:
            return
        
        weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        today = weekdays[now.weekday()]
        days_allowed = False
        
        for item in schedule:
            if item['time'] == current_time:
                if item['days'] == 'Ежедневно':
                    days_allowed = True
                elif item['days'] == 'Пн-Пт' and today in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт']:
                    days_allowed = True
                elif item['days'] == 'Сб-Вс' and today in ['Сб', 'Вс']:
                    days_allowed = True
                elif item['days'] == today:
                    days_allowed = True
                break
        
        if not days_allowed:
            return
        
        # Выбираем тему
        if current_time == "10:00":
            morning_topics = get_user_topics(user_id, is_morning=True)
            if morning_topics:
                topic = random.choice(morning_topics)
                style = 'информативный'
            else:
                topics = get_user_topics(user_id)
                if not topics:
                    return
                topic = random.choice(topics)
                style = random.choice(['информативный', 'юмористический', 'вовлекающий'])
        else:
            topics = get_user_topics(user_id)
            if not topics:
                return
            topic = random.choice(topics)
            style = random.choice(['информативный', 'юмористический', 'вовлекающий'])
        
        text = generate_text(topic, style)
        
        if text.startswith("❌"):
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO posts_history (user_id, topic, text, status, error)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, topic, text[:500], 'failed', text))
                conn.commit()
            return
        
        try:
            post_id = publish_post(
                vk_settings['vk_token'],
                vk_settings['group_id'],
                text
            )
            
            if deduct_post_cost(user_id):
                status = 'published'
                cost = POST_PRICE
                error = None
            else:
                status = 'insufficient_balance'
                cost = 0
                error = 'Недостаточно средств'
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO posts_history (user_id, topic, text, status, cost, error, post_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, topic, text[:500], status, cost, error, post_id))
                conn.commit()
            
            print(f"✅ Пользователь {user_id}: Пост опубликован!")
            
        except Exception as e:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO posts_history (user_id, topic, text, status, error)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, topic, text[:500], 'failed', str(e)))
                conn.commit()
            print(f"❌ Пользователь {user_id}: Ошибка - {e}")
            
    except Exception as e:
        print(f"⚠️ Ошибка обработки пользователя {user_id}: {e}")

def bot_loop():
    print("=" * 60)
    print("🤖 SMM Пилот Бот запущен!")
    print("=" * 60)
    print(f"💲 Стоимость поста: {POST_PRICE} ₽")
    print("=" * 60)
    
    last_minute = ""
    
    while True:
        try:
            now = get_novosibirsk_time()
            current_minute = now.strftime("%Y-%m-%d %H:%M")
            
            if current_minute != last_minute:
                last_minute = current_minute
                
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT DISTINCT u.id 
                        FROM users u
                        JOIN vk_settings v ON u.id = v.user_id
                        WHERE u.is_active = 1 
                        AND v.is_active = 1 
                        AND v.is_configured = 1
                        AND u.balance >= ?
                    ''', (POST_PRICE,))
                    users = cursor.fetchall()
                
                if users:
                    print(f"⏰ {current_minute} - Обработка {len(users)} пользователей...")
                    for user in users:
                        process_user(user['id'])
                    time.sleep(5)
            
            time.sleep(1)
            
        except Exception as e:
            print(f"⚠️ Ошибка бота: {e}")
            time.sleep(5)

_bot_started = False

def start_bot():
    global _bot_started
    if not _bot_started:
        _bot_started = True
        print("🔄 Запуск бота в фоновом потоке...")
        bot_thread = threading.Thread(target=bot_loop, daemon=True)
        bot_thread.start()
        print("✅ Бот запущен в фоновом режиме")
