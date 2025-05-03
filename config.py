import os
import logging
from dotenv import load_dotenv


load_dotenv(".env")

SHOW_DEBUG_EXECUTION_TIME = False
LOG_LEVEL=logging.INFO

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

TELEGRAM_URL = "https://api.telegram.org"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = -4226743295

GRPC_URL = os.getenv("GRPC_URL")