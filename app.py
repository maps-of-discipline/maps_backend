
from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import MetaData
from flask_mail import Mail
from dotenv import load_dotenv


from maps.logic.global_variables import setGlobalVariables
from maps.logic.take_from_bd import (blocks, blocks_r, period, period_r, control_type, control_type_r,
                                     ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r)
from maps.models import db


from unification import unification_blueprint
from utils.handlers import handle_exception

load_dotenv()

app = Flask(__name__)


application = app
cors = CORS(app, resources={r"*": {"origins": "*"}}, supports_credentials=True)

app.config.from_pyfile('config.py')
mail = Mail(app)
app.config['CORS_HEADERS'] = 'Content-Type'

app.register_blueprint(cabinet, url_prefix=app.config['URL_PREFIX_CABINET'])

app.json.sort_keys = False

from maps.routes import maps as maps_blueprint
from auth.routes import auth as auth_blueprint
from administration.routes import admin as admin_blueprint


# Register blueprints
app.register_blueprint(maps_blueprint)
app.register_blueprint(auth_blueprint)
app.register_blueprint(unification_blueprint)
app.register_blueprint(admin_blueprint)

convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)
db.init_app(app)

migrate = Migrate(app, db)

# from save_into_bd import bp as save_db_bp

# app.register_blueprint(save_db_bp)

# from models import AUP


def authLK():
    payload = {
        'ulogin': app.config.get('LK_ACCOUNT_LOGIN'),
        'upassword': app.config.get('LK_ACCOUNT_PASSWORD'),
    }

    res = requests.post(app.config.get('LK_URL'), data=payload)
    data = res.json()
    return data['token']

app.config['LK_TOKEN'] = 'wuAa8rTP9Ds%2FdqEl4RwvKF1etcrn3kJKh03%2FI%2FJ7Zkn91x%2FmFKwVJffBQA8DN0XpdvhClndCo5wC7Ii6HHqiQkl6mBx58NNdyXiBAv%2FoCx3RJajn4jnhTYfz7LT%2Bl9vZDyMpFr4aJKXYlvIA6cj3W2bTOeurN5yWHdhl9yfRD1o%3D'

ZET_HEIGHT = 90

setGlobalVariables(app, blocks, blocks_r, period, period_r, control_type, control_type_r,
                   ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r)


if not app.config['DEBUG']:
    app.register_error_handler(Exception, handle_exception)