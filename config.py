import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Базовая конфигурация Flask
DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')
TESTING = False
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

SHOW_DEBUG_EXECUTION_TIME = False
LOG_LEVEL = logging.INFO if not DEBUG else logging.DEBUG

# Настройки базы данных
SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'mysql+pymysql://user:password@localhost/db_name')
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Настройка подключения к внешней БД Карт Дисциплин (KD)
EXTERNAL_KD_DATABASE_URL = os.getenv('EXTERNAL_KD_DATABASE_URL') # Must be set in production environment variables

# Настройки CORS
CORS_HEADERS = 'Content-Type'


# Настройки для работы с файлами
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

# Прочие настройки
ACCESS_TOKEN_LIFETIME = 3600 * 24  # 1 день в секундах
REFRESH_TOKEN_LIFETIME = 7 * 24 * 3600  # 7 дней в секундах

TELEGRAM_URL = 'https://api.telegram.org'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'openrouter')

# Local LLM Configuration
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL")
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY")
LOCAL_LLM_MODEL_NAME = os.getenv("LOCAL_LLM_MODEL_NAME")

# Kluster AI Configuration
KLUSTER_AI_API_KEY = os.getenv("KLUSTER_AI_API_KEY")
KLUSTER_AI_BASE_URL = os.getenv("KLUSTER_AI_BASE_URL")
KLUSTER_AI_MODEL_NAME = os.getenv("KLUSTER_AI_MODEL_NAME")

# OpenRouter Configuration
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL_NAME = os.getenv("OPENROUTER_MODEL_NAME", "z-ai/glm-4.5-air:free")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL")
OPENROUTER_SITE_NAME = os.getenv("OPENROUTER_SITE_NAME")