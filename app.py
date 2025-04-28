from flask import Flask, jsonify, g, current_app
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import MetaData
from flask_mail import Mail
from dotenv import load_dotenv
from flask_caching import Cache
from grpc_service.context import get_grpc_context, teardown_grpc_context
import asyncio


from maps.logic.global_variables import setGlobalVariables
from maps.logic.take_from_bd import (
    blocks,
    blocks_r,
    period,
    period_r,
    control_type,
    control_type_r,
    ed_izmereniya,
    ed_izmereniya_r,
    chast,
    chast_r,
    type_record,
    type_record_r,
)
from maps.models import db


from unification import unification_blueprint
from utils.handlers import handle_exception

load_dotenv()

config = {
    "DEBUG": True,  # some Flask specific configs
    "CACHE_TYPE": "SimpleCache",  # Flask-Caching related configs
    "CACHE_DEFAULT_TIMEOUT": 300,
}

app = Flask(__name__)


app.before_request(lambda: asyncio.run(get_grpc_context()) or None)
app.teardown_request(lambda exc: asyncio.run(teardown_grpc_context(exc)) or None)


app.config.from_mapping(config)
cache = Cache(app)

application = app
cors = CORS(app, resources={r"*": {"origins": "*"}}, supports_credentials=True)

app.config.from_pyfile("config.py")
mail = Mail(app)
app.json.sort_keys = False

from maps.routes.maps import maps as maps_blueprint
from auth.routes import auth as auth_blueprint
from administration.routes import admin as admin_blueprint
from rups.routes import rups as rups_blueprint
from maps.routes.aup_info import aup_info_router as maps_aup_info_router

# Register blueprints
app.register_blueprint(maps_blueprint)
app.register_blueprint(auth_blueprint)
app.register_blueprint(unification_blueprint)
app.register_blueprint(admin_blueprint)
app.register_blueprint(rups_blueprint)
app.register_blueprint(maps_aup_info_router)


convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)
db.init_app(app)

migrate = Migrate(app, db)

setGlobalVariables(
    app,
    blocks,
    blocks_r,
    period,
    period_r,
    control_type,
    control_type_r,
    ed_izmereniya,
    ed_izmereniya_r,
    chast,
    chast_r,
    type_record,
    type_record_r,
)


if not app.config["DEBUG"]:
    app.register_error_handler(Exception, handle_exception)
