from models import *


from flask import Flask
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView


class UnificationModelView(ModelView):
    inline_models = [UnificationLoad]
    can_view_details = True


def init_admin(app: Flask, session):
    admin = Admin(app, name='Title', template_mode='bootstrap3')
    admin.add_view(UnificationModelView(Unification, session, category='Unification'))