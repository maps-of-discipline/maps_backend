from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .maps import db
from user_policy import UsersPolicy

users_faculty_table = db.Table(
    'users_faculty',
    db.Column("user_id", db.ForeignKey('tbl_users.id_user'), nullable=False),
    db.Column('faculty_id', db.ForeignKey('spr_faculty.id_faculty'), nullable=False)
)


class Users(db.Model, UserMixin):
    __tablename__ = 'tbl_users'

    id_user = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), nullable=True)
    password_hash = db.Column(db.String(200), unique=True, nullable=False)

    id_role = db.Column(db.Integer, db.ForeignKey(
        'roles.id_role'), nullable=False)

    role = db.relationship('Roles')

    department_id = db.Column(db.Integer, db.ForeignKey('tbl_department.id_department'), nullable=True)

    faculties = db.Relationship(
        'SprFaculty',
        secondary=users_faculty_table,
    )

    department = db.Relationship(
        'Department',
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # @property
    # def full_name(self):
    #     return ' '.join([self.last_name, self.first_name, self.middle_name or ''])

    @property
    def is_admin(self):
        from app import app
        return app.config.get('ADMIN_ROLE_ID') == self.role_id

    @property
    def is_facult(self):
        from app import app
        return app.config.get('FACULTY_ROLE_ID') == self.role_id

    @property
    def is_depart(self):
        from app import app
        return app.config.get('DEPARTMENT_ROLE_ID') == self.role_id

    def can(self, action):
        users_policy = UsersPolicy()
        method = getattr(users_policy, action)
        if method is not None:
            return method()
        return False

    def __repr__(self):
        return '<User %r>' % self.login


class Token(db.Model):
    __tablename__ = 'tbl_token'

    id = db.Column(db.Integer(), primary_key=True)
    user_id = db.Column(db.Integer(), db.ForeignKey('tbl_users.id_user'), nullable=False)
    refresh_token = db.Column(db.String(256), nullable=False)
    user_agent = db.Column(db.String(256), nullable=False)
    ttl = db.Column(db.Integer(), nullable=False)

    user = db.relationship('Users')


permissions_table = db.Table(
    "permissions",
    db.Column("role_id", db.ForeignKey("roles.id_role"), nullable=False),
    db.Column("mode_id", db.ForeignKey("mode.id"), nullable=False)
)


class Roles(db.Model):
    __tablename__ = 'roles'

    id_role = db.Column(db.Integer, primary_key=True)
    name_role = db.Column(db.String(100), nullable=False)

    modes = db.relationship(
        "Mode",
        secondary=permissions_table,
    )

    def __repr__(self):
        return '<Role %r>' % self.name_role


class Mode(db.Model):
    __tablename__ = "mode"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(255), nullable=False)

    roles = db.relationship(
        "Roles",
        secondary=permissions_table
    )

    def __repr__(self):
        return f'{self.title}.{self.action}'