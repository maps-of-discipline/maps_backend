import requests
from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import MetaData
from flask_mail import Mail
from dotenv import load_dotenv
import os
from flask_sqlalchemy import SQLAlchemy
from cabinet.cabinet import cabinet
from maps.logic.global_variables import setGlobalVariables
from maps.logic.take_from_bd import (blocks, blocks_r, period, period_r, control_type, control_type_r,
                                     ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r)
from maps.models import db, init_db  # Add init_db import
from maps.routes import maps as maps_blueprint
from unification import unification_blueprint
from auth.routes import auth as auth_blueprint
from administration.routes import admin as admin_blueprint
from competencies_matrix import competencies_matrix_bp  # Импортируем наш новый blueprint
from utils.handlers import handle_exception

load_dotenv()
app = Flask(__name__)
application = app
# Настройка CORS
cors = CORS(app, resources={r"*": {"origins": "*"}}, supports_credentials=True)
app.config.from_pyfile('config.py')
app.json.sort_keys = False
# Настройки приложения

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Регистрация blueprints
app.register_blueprint(cabinet, url_prefix=app.config['URL_PREFIX_CABINET'])
# app.register_blueprint(maps_blueprint)
app.register_blueprint(auth_blueprint)
app.register_blueprint(unification_blueprint)
app.register_blueprint(admin_blueprint)
app.register_blueprint(competencies_matrix_bp)  # Регистрируем наш blueprint
# Инициализация расширений
mail = Mail(app)
# db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Настройка SQLAlchemy
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)
db.init_app(app)
with app.app_context():
    init_db()  # Initialize minimal DB structure
    # # uncomment this if you want to drop all tables, 
    # # then comment these lines back after running "flask db init" once
    # # "flask db init" should output an error
    # meta = MetaData()
    # meta.reflect(bind=db.engine)
    # meta.drop_all(db.engine)
migrate = Migrate(app, db)

# Глобальные переменные
setGlobalVariables(app, blocks, blocks_r, period, period_r, control_type, control_type_r,
                   ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r)

# Обработка ошибок только в production
if not app.config['DEBUG']:
    app.register_error_handler(Exception, handle_exception)

# Простой маршрут для проверки, что приложение работает
@app.route('/')
def index():
    return {'message': 'Competencies Matrix API is running'}, 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
