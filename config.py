import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Базовая конфигурация Flask
DEBUG = False # Set to False for production
TESTING = False
SECRET_KEY = os.getenv('SECRET_KEY') # Must be set in production environment variables

SHOW_DEBUG_EXECUTION_TIME = False
LOG_LEVEL = logging.INFO # Adjust as needed for production

# Настройки базы данных
SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL') # Must be set in production environment variables
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Настройка подключения к внешней БД Карт Дисциплин (KD)
EXTERNAL_KD_DATABASE_URL = os.getenv('EXTERNAL_KD_DATABASE_URL') # Must be set in production environment variables

# Конфигурация множественных БД
SQLALCHEMY_BINDS = {
    'kd_external': EXTERNAL_KD_DATABASE_URL
}

# Настройки почты (если потребуется)
MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')

# Настройки CORS
CORS_HEADERS = 'Content-Type'

# Префиксы URL для разных частей приложения
URL_PREFIX_CABINET = '/api/cabinet'
URL_PREFIX_COMPETENCIES = '/api/competencies'
URL_PREFIX_COMPETENCIES_MATRIX = '/api/competencies_matrix'

# Настройки для работы с файлами
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

# Прочие настройки
ACCESS_TOKEN_LIFETIME = 3600  # 1 hour in seconds
REFRESH_TOKEN_LIFETIME = 7 * 24 * 3600  # 7 days in seconds

TELEGRAM_URL = 'https://api.telegram.org'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID') # Should be set in production environment variables