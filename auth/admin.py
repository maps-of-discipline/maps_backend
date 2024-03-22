from flask_admin.actions import action
from flask_admin.contrib.sqla import ModelView

from auth.models import Mode, Roles, Users
from maps.models import db, AupData


category = __package__.capitalize()


class ModeAdminView(ModelView):
    form_choices = {
        "action": [
            ("view", "Просмотр"),
            ("edit", "Редактирование")
        ]
    }

    column_details_list = column_list = ['title', 'action', 'roles']


class RoleAdminView(ModelView):
    column_details_list = ['name_role', ]


class UserAdminView(ModelView):
    can_create = False
    column_list = ['login', 'role', 'email', 'faculties', 'department']
    column_details_list = ['login', 'role', 'email', 'faculties', 'department']
        


auth_admin_views = [
    ModeAdminView(Mode, db.session, category=category),
    RoleAdminView(Roles, db.session, category=category),
    UserAdminView(Users, db.session, category=category),
]


