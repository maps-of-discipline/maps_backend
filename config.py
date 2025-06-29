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

# Конфигурация множественных БД (если используется)
# SQLALCHEMY_BINDS = {
#     'kd_external': EXTERNAL_KD_DATABASE_URL
# }

# Настройки CORS
CORS_HEADERS = 'Content-Type'


# Настройки для работы с файлами
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

# Прочие настройки
ACCESS_TOKEN_LIFETIME = 3600  # 1 hour in seconds
REFRESH_TOKEN_LIFETIME = 7 * 24 * 3600  # 7 days in seconds

TELEGRAM_URL = 'https://api.telegram.org'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Провайдер по умолчанию: 'local', 'klusterai'
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'klusterai').lower()

# --- Local OpenAI-compatible LLM (e.g., LM Studio, Ollama) ---
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "not-needed") # Часто не требуется
LOCAL_LLM_MODEL_NAME = os.getenv("LOCAL_LLM_MODEL_NAME", "local-model")

# --- Kluster.ai Configuration ---
KLUDESTER_AI_API_KEY = os.getenv("KLUDESTER_AI_API_KEY", "d31cd353-3336-4b0f-abcc-12e595c2eefc")
KLUDESTER_AI_BASE_URL = os.getenv("KLUDESTER_AI_BASE_URL", "https://api.kluster.ai/v1")
KLUDESTER_AI_MODEL_NAME = os.getenv("KLUDESTER_AI_MODEL_NAME", "google/gemma-3-27b-it")