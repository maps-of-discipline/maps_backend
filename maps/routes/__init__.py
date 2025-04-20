from flask import Blueprint
from .aup_info import aup_info_router
from .maps import maps

maps_module = Blueprint("maps_module", __name__, static_folder="../static")
maps_module.register_blueprint(aup_info_router)
maps_module.register_blueprint(maps)
