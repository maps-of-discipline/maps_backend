import os
import logging
from dotenv import load_dotenv


load_dotenv(".env")

SHOW_DEBUG_EXECUTION_TIME = False
LOG_LEVEL = logging.DEBUG

APP_URL_PREFIX = os.getenv("APP_URL_PREFIX") or "/api"

SECRET_KEY = os.getenv("SECRET_KEY")
SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = False
CORS_HEADERS = "Content-Type"

MAIL_SERVER = "smtp.mail.ru"
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

ADMIN_ROLE_ID = 1
FACULTY_ROLE_ID = 2
DEPARTMENT_ROLE_ID = 3

ACCESS_TOKEN_LIFETIME = 3600  # 1 hour in seconds
REFRESH_TOKEN_LIFETIME = 7 * 24 * 3600  # 7 days in seconds


TELEGRAM_URL = "https://api.telegram.org"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = -4226743295
