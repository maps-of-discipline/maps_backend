# filepath: app.py
import requests
from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import MetaData
from dotenv import load_dotenv
import os
import logging
import click # Import click for custom CLI commands (unused)
from flask.cli import with_appcontext # Import with_appcontext for CLI commands


from maps.models import db

from utils.cache import cache
from cabinet.cabinet import cabinet
from maps.routes import maps_module
from unification import unification_blueprint
from auth.routes import auth as auth_blueprint
from administration.routes import admin as admin_blueprint
from competencies_matrix import competencies_matrix_bp
from utils.handlers import handle_exception


from cli_commands import register_cli_commands

load_dotenv()

app = Flask(__name__)
application = app

def configure_logging():
    """Configure application logging based on config settings."""
    from config import LOG_LEVEL

    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    app.logger.setLevel(LOG_LEVEL) 
    
    logging.getLogger('pdfminer').setLevel(logging.WARNING)
    logging.getLogger('google_genai').setLevel(logging.INFO)
    logging.getLogger('httpx').setLevel(logging.INFO) # Чтобы видеть запросы к LLM API
    
    if LOG_LEVEL > logging.DEBUG:
        logging.getLogger('competencies_matrix').setLevel(logging.DEBUG)
        logging.getLogger('maps').setLevel(logging.INFO)
        logging.getLogger('auth').setLevel(logging.INFO)
        logging.getLogger('cabinet').setLevel(logging.INFO)
        logging.getLogger('administration').setLevel(logging.INFO)

configure_logging()

app.config.from_pyfile('config.py')
app.json.sort_keys = False

flask_env = os.getenv('FLASK_ENV', 'development') # development, production
app.config['ENV'] = flask_env
app.debug = (flask_env == 'development')

config_cache = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
}
app.config.from_mapping(config_cache)
cache.init_app(app)

CORS(
    app,
    origins=os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','),
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Accept",
        "Origin",
        "Aup"
    ],
    expose_headers=["Content-Disposition", "Content-Type"],
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
db.init_app(app)
migrate = Migrate(app, db, render_as_batch=True, compare_type=True, naming_convention=convention)

# Регистрация Blueprint'ов
app.register_blueprint(cabinet, url_prefix=app.config.get('URL_PREFIX_CABINET', '/api'))
app.register_blueprint(maps_module, url_prefix=app.config.get('URL_PREFIX_MAPS', '/api/maps'))
app.register_blueprint(auth_blueprint, url_prefix='/api/auth')
app.register_blueprint(admin_blueprint, url_prefix='/api/admin')
app.register_blueprint(unification_blueprint, url_prefix='/api/unification')
app.register_blueprint(competencies_matrix_bp, url_prefix=app.config.get('URL_PREFIX_COMPETENCIES', '/api/competencies'))

if not app.config.get('DEBUG'):
    app.register_error_handler(Exception, handle_exception) 

@app.route('/')
def index():
    return jsonify({'message': 'Maps and Competencies API is running'}), 200

if app.debug:
    @app.route('/test/external-db')
    def test_external_db():
        """Тестовый эндпоинт для проверки подключения к внешней БД."""
        try:
            if app.config['SQLALCHEMY_BINDS'].get('kd_external'):
                from sqlalchemy import text
                engine = db.get_engine(bind_key='kd_external')
                with engine.connect() as connection:
                    result = connection.execute(text("SELECT 1")).scalar_one()
                return jsonify({'success': True, 'message': 'Успешное подключение к внешней БД', 'result': result}), 200
            else:
                return jsonify({'success': False, 'message': 'Внешняя БД не сконфигурирована в SQLAlchemy binds'}), 500
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
            url = urllib.parse.unquote(str(rule))
            line = "{:50s} {:20s} {}".format(rule.endpoint, methods, url)
            output.append(line)

        output.sort()
        return jsonify(output)

register_cli_commands(app)