import warnings

from flask import Flask
from flask_admin import Admin
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import MetaData

from maps.logic.global_variables import setGlobalVariables
from maps.logic.take_from_bd import (blocks, blocks_r, period, period_r, control_type, control_type_r,
                                     ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r)
from maps.models import db
from maps.routes import maps as maps_blueprint
from auth import auth_blueprint
from auth.admin import auth_admin_views
from unification import unification_blueprint
from unification.admin import unification_admin_views

warnings.simplefilter("ignore")

app = Flask(__name__)


# Register admin views
admin = Admin(app, name="Maps of Disciplines", template_mode="bootstrap3")
for view in [*auth_admin_views, *unification_admin_views]:
    admin.add_view(view)


# Register blueprints
app.register_blueprint(maps_blueprint)
app.register_blueprint(auth_blueprint)
app.register_blueprint(unification_blueprint)


application = app
cors = CORS(app, resources={r"*": {"origins": "*"}}, supports_credentials=True)

app.config.from_pyfile('config.py')
app.json.sort_keys = False

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

setGlobalVariables(app, blocks, blocks_r, period, period_r, control_type, control_type_r,
                   ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r)




