import requests
from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import MetaData
from dotenv import load_dotenv
import os

# --- Импорты моделей для seed_command и приложения ---
# Keep 'db' import, remove others if ONLY used by seed/unseed
from maps.models import db


# --- Импорты блюпринтов ---
from cabinet.cabinet import cabinet
from maps.routes import maps as maps_blueprint
from unification import unification_blueprint
from auth.routes import auth as auth_blueprint
from administration.routes import admin as admin_blueprint
from competencies_matrix import competencies_matrix_bp
from utils.handlers import handle_exception

# --- Import CLI Commands ---
from cli_commands.db_seed import seed_command
from cli_commands.db_unseed import unseed_command

# Загрузка переменных окружения
load_dotenv()

# Создание экземпляра приложения Flask
app = Flask(__name__)
application = app # Для совместимости с некоторыми WSGI серверами

# Загрузка конфигурации
app.config.from_pyfile('config.py')
app.json.sort_keys = False # Отключаем сортировку ключей в JSON ответах

# Настройка CORS
cors = CORS(app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin", "Aup"],
    automatic_options=True
)

# Настройки SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', app.config.get('SQLALCHEMY_DATABASE_URI'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация расширений
# mail = Mail(app)

# --- Инициализация SQLAlchemy и Migrate ---
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}
metadata = MetaData(naming_convention=convention)
db.init_app(app)
migrate = Migrate(app, db, render_as_batch=True, compare_type=True, naming_convention=convention)

# --- Регистрация blueprints ---
app.register_blueprint(cabinet, url_prefix=app.config.get('URL_PREFIX_CABINET', '/api'))
app.register_blueprint(maps_blueprint, url_prefix=app.config.get('URL_PREFIX_MAPS', '/api/maps'))
app.register_blueprint(auth_blueprint, url_prefix='/api/auth')
app.register_blueprint(admin_blueprint, url_prefix='/api/admin')
app.register_blueprint(unification_blueprint, url_prefix='/api/unification')
app.register_blueprint(competencies_matrix_bp, url_prefix=app.config.get('URL_PREFIX_COMPETENCIES', '/api/competencies'))

# --- Обработка ошибок ---
if not app.config.get('DEBUG'):
    app.register_error_handler(Exception, handle_exception)

# --- Базовый маршрут ---
@app.route('/')
def index():
    """Простой GET эндпоинт для проверки, что API работает."""
    return jsonify({'message': 'Maps and Competencies API is running'}), 200

@app.route('/debug/routes')
def list_routes():
    """List all registered routes with their endpoints and HTTP methods."""
    routes = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods - {'OPTIONS', 'HEAD'}))
        routes.append(f"{rule.endpoint:50s} {methods:20s} {rule}")
    return jsonify(sorted(routes))

# Регистрируем команды сидера и ансидера
app.cli.add_command(seed_command)
app.cli.add_command(unseed_command)

# Точка входа для запуска через `python app.py`
if __name__ == '__main__':
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=5000)