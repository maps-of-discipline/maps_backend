from flask import Blueprint, jsonify, request, Request

from administration.admin_view import SimpleAdminView

from auth.logic import admin_only
from maps.models import db


admin = Blueprint("Administration", __name__, url_prefix="/api/admin")

'''
class RolesAdminView(SimpleAdminView):
    model = Roles
    fields = [
        ("id_role", "ИД"),
        ("name_role", "Название"),
    ]


@admin.route("/roles", methods=["GET", "POST", "PUT", "DELETE"])
@admin.route("/roles/<int:id>", methods=["GET", "POST", "PUT", "DELETE"])
@admin_only(request)
def roles_view(id: int | None = None):
    view = RolesAdminView()
    return view.handle_request(request, id)


class ModesAdminView(SimpleAdminView):
    model = Mode
    fields = [
        ("id", "ИД"),
        ("title", "Название"),
        ("action", "Режим"),
    ]


@admin.route("/modes", methods=["GET", "POST", "PUT", "DELETE"])
@admin.route("/modes/<int:id>", methods=["GET", "POST", "PUT", "DELETE"])
@admin_only(request)
def modes_view(id: int | None = None):
    view = ModesAdminView()
    return view.handle_request(request, id)


@admin.route("/users", methods=["GET", "POST", "PUT", "DELETE"])
@admin.route("/users/<int:id>", methods=["GET", "POST", "PUT", "DELETE"])
@admin_only(request)
def user_view(id: int | None = None):
    view = UserCrudView()
    print(id)
    return view.handle_request(request, id)
'''

