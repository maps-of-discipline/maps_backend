from flask import Blueprint

from auth.models import Users
from maps.models import db


def register_commands(app: Blueprint):
    @app.cli.command('create-user')
    def create_user():
        username = input('Username: ')
        password = input('Password: ')

        role_to_id = {'admin': 1, 'faculty': 2, 'department': 3}
        role = input('User role (admin, faculty, department): ')

        user = Users()
        user.login = username
        user.set_password(password)

        try:
            user.id_role = role_to_id[role]
        except KeyError:
            print('Incorrect role!')
            return

        db.session.add(user)
        db.session.commit()

        print(f"User {username} created!")
