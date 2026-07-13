import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DATABASE_PATH = 'instance/smm_bot.db'
    
    # Yandex GPT
    YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID')
    YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
    
    # Цена за пост
    POST_PRICE = 0.50
    
    # Администратор (для первого входа)
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@example.com')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')