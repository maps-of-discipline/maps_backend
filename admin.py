from models import *


from flask import Flask
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView



class UnificationModelView(ModelView):
    inline_models = (UnificationLoad, ) #dict(form_columns=['unification', 'control_type', 'amount'])),)


class UnificationLoadView(ModelView):
    form_widget_args = {
        'id': {'placeholder': 'new id will be automatically created', 'readonly': True},
    }


def init_admin(app: Flask, session):
    admin = Admin(app, name='Title', template_mode='bootstrap3')
    admin.add_view(ModelView(UnificationLoad, session, category='Unification'))
    admin.add_view(ModelView(UniqueDiscipline, session, category='Unification'))
    admin.add_view(UnificationModelView(Unification, session, category='Unification'))