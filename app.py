# maps_backend/app.py
import requests
from flask import Flask, jsonify
from flask_cors import CORS # Убедитесь, что этот импорт есть
from flask_migrate import Migrate
from sqlalchemy import MetaData
from dotenv import load_dotenv
import os
import logging # Добавим для логгирования конфигурации

# --- Импорты моделей для seed_command и приложения ---
from maps.models import db # db используется для инициализации
from utils.cache import cache


# --- Импорты блюпринтов ---
from cabinet.cabinet import cabinet
from maps.routes import maps_module # Используем maps_module, а не maps
from unification import unification_blueprint
from auth.routes import auth as auth_blueprint
from administration.routes import admin as admin_blueprint
from competencies_matrix import competencies_matrix_bp
from utils.handlers import handle_exception

# --- Импорты консольных команд ---
from cli_commands.db_seed import seed_command
from cli_commands.db_unseed import unseed_command
from cli_commands.import_aup import import_aup_command
from cli_commands.fgos_import import import_fgos_command
from cli_commands.parse_profstandard import parse_ps_command # Добавим команду парсинга ПС

# Keep Flask-CORS import
from flask_cors import CORS 

load_dotenv()

app = Flask(__name__)
application = app

app.config.from_pyfile('config.py')
app.json.sort_keys = False

config_cache = { # Renamed to avoid conflict with config.py module itself
    "DEBUG": True,
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
}
app.config.from_mapping(config_cache)
cache.init_app(app) # Assuming cache is defined and imported from utils.cache

# --- НАСТРОЙКА CORS ---
cors_origins = "*"
if app.debug: # Более гибко для разработки, если "*" не работает с credentials
    cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"] # Пример для Vite
    # или ваш порт, на котором запускается фронтенд

CORS(
    app,
    # origins=cors_origins, # Используем переменную
    origins="*", # Пока оставим так для максимальной простоты, но это менее безопасно для прода
    supports_credentials=True, # Важно для передачи кук и заголовка Authorization
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"], # Все необходимые методы
    allow_headers=[ # Все необходимые заголовки
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Accept",
        "Origin",
        "Aup" # Если этот заголовок используется
    ],
    expose_headers=["Content-Disposition"], # Если этот заголовок используется клиентом
    automatic_options=True # Flask-CORS должен автоматически обрабатывать OPTIONS запросы
)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', app.config.get('SQLALCHEMY_DATABASE_URI'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if app.config.get('SQLALCHEMY_BINDS') is None and app.config.get('EXTERNAL_KD_DATABASE_URL'):
    app.config['SQLALCHEMY_BINDS'] = {
        'kd_external': app.config.get('EXTERNAL_KD_DATABASE_URL')
    }

convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}
metadata = MetaData(naming_convention=convention)
db.init_app(app) # db should be imported from maps.models
migrate = Migrate(app, db, render_as_batch=True, compare_type=True, naming_convention=convention)

# --- Регистрация blueprints ---
app.register_blueprint(cabinet, url_prefix=app.config.get('URL_PREFIX_CABINET', '/api'))
app.register_blueprint(maps_module, url_prefix=app.config.get('URL_PREFIX_MAPS', '/api/maps'))
app.register_blueprint(auth_blueprint, url_prefix='/api/auth')
app.register_blueprint(admin_blueprint, url_prefix='/api/admin')
app.register_blueprint(unification_blueprint, url_prefix='/api/unification')
app.register_blueprint(competencies_matrix_bp, url_prefix=app.config.get('URL_PREFIX_COMPETENCIES', '/api/competencies'))

if not app.config.get('DEBUG'):
    app.register_error_handler(Exception, handle_exception) # handle_exception from utils.handlers

@app.route('/')
def index():
    return jsonify({'message': 'Maps and Competencies API is running'}), 200

@app.route('/test/external-db')
def test_external_db():
    """Тестовый эндпоинт для проверки подключения к внешней БД."""
    # Эта логика требует, что модели для внешней БД были определены
    # и чтобы сессия для внешней БД создавалась корректно.
    # Если external_models.py определяет свои модели и сессию, то используйте их.
    # ВАЖНО: этот эндпоинт НЕ должен зависеть от `from kd_external_models import ...`
    # если `kd_external_models.py` находится ВНУТРИ вашего проекта.
    # Вместо этого, логика подключения и запроса должна быть инкапсулирована,
    # например, в `competencies_matrix/logic.py`.
    try:
        # Предположим, у вас есть функция в logic.py для теста
        # from competencies_matrix.logic import test_external_kd_connection
        # result = test_external_kd_connection()
        # return jsonify(result), 200 if result.get('success') else 500
        # --- ЗАГЛУШКА для примера ---
        if app.config['SQLALCHEMY_BINDS'].get('kd_external'):
            # Попытка простого запроса, если движок есть
            from sqlalchemy import text
            engine = db.get_engine(bind_key='kd_external')
            with engine.connect() as connection:
                result = connection.execute(text("SELECT 1")).scalar_one()
            return jsonify({'success': True, 'message': 'Успешное подключение к внешней БД', 'result': result}), 200
        else:
            return jsonify({'success': False, 'message': 'Внешняя БД не сконфигурирована в SQLAlchemy binds'}), 500
        # --- КОНЕЦ ЗАГЛУШКИ ---
    except Exception as e:
        logging.error(f"Error testing external DB: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'Ошибка подключения к внешней БД',
            'error': str(e)
        }), 500


@app.route('/debug/routes')
def list_routes():
    """List all registered routes with their endpoints and HTTP methods."""
    import urllib
    output = []
    for rule in app.url_map.iter_rules():
        options = {}
        for arg in rule.arguments:
            options[arg] = "[{0}]".format(arg)
        methods = ','.join(rule.methods)
        url = urllib.parse.unquote(str(rule)) # Декодируем URL
        line = "{:50s} {:20s} {}".format(rule.endpoint, methods, url)
        output.append(line)

    # Добавим сортировку для лучшей читаемости
    output.sort()
    # Используем <pre> для сохранения форматирования в HTML
    # или возвращаем как JSON, если предполагается машинная обработка
    # return "<pre>" + "\n".join(output) + "</pre>"
    return jsonify(output) # Возвращаем как JSON массив строк

# Регистрируем команды
app.cli.add_command(seed_command)
app.cli.add_command(unseed_command)
app.cli.add_command(import_aup_command)
app.cli.add_command(import_fgos_command)
app.cli.add_command(parse_ps_command) # Добавляем команду парсинга ПС


# Точка входа для запуска через `python app.py`
if __name__ == '__main__':
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=5000)