from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView

from models import *


class ModeAdminView(ModelView):
    form_choices = {
        "action": [
            ("view", "Просмотр"),
            ("edit", "Редактирование")
        ]
    }


class RoleAdminView(ModelView):
    ...


def init_admin(app, session):
    admin = Admin(app, name="Maps of Disciplines", template_mode="bootstrap3")
    admin.add_view(ModeAdminView(Mode, session, category="Auth"))
    admin.add_view(RoleAdminView(Roles, session, category="Auth"))