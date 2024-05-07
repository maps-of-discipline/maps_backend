from werkzeug.security import generate_password_hash, check_password_hash

from maps.models import db, SerializationMixin

users_faculty_table = db.Table(
    "users_faculty",
    db.Column("user_id", db.ForeignKey("tbl_users.id_user", ondelete="CASCADE"), nullable=False),
    db.Column("faculty_id", db.ForeignKey("spr_faculty.id_faculty", ondelete="CASCADE"), nullable=False),
)


permissions_table = db.Table(
    "Permissions",
    db.Column("role_id", db.ForeignKey("roles.id_role", ondelete="CASCADE"), nullable=False),
    db.Column("mode_id", db.ForeignKey("Mode.id", ondelete="CASCADE"), nullable=False),
)


user_roles_table = db.Table(
    "user_roles",
    db.Column("role_id", db.ForeignKey("roles.id_role", ondelete="CASCADE"), nullable=False),
    db.Column("user_id", db.ForeignKey("tbl_users.id_user", ondelete="CASCADE"), nullable=False),
)


class Users(db.Model, SerializationMixin):
    __tablename__ = "tbl_users"

    id_user = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), nullable=True)
    password_hash = db.Column(db.String(200), unique=True, nullable=False)

    department_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "tbl_department.id_department",
            ondelete='SET NULL'),
    )

    roles = db.relationship(
        "Roles",
        secondary=user_roles_table
    )

    faculties = db.Relationship(
        "SprFaculty",
        secondary=users_faculty_table,
    )

    department = db.Relationship(
        "Department",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return "<User %r>" % self.login

    def __str__(self):
        return self.login


class Token(db.Model):
    __tablename__ = "tbl_token"

    id = db.Column(db.Integer(), primary_key=True)
    user_id = db.Column(
        db.Integer(), 
        db.ForeignKey(
            "tbl_users.id_user",
            ondelete="CASCADE"),
            nullable=False
    )
    refresh_token = db.Column(db.String(256), nullable=False)
    user_agent = db.Column(db.String(256), nullable=False)
    ttl = db.Column(db.Integer(), nullable=False)

    user = db.relationship("Users")


class Roles(db.Model, SerializationMixin):
    __tablename__ = "roles"

    id_role = db.Column(db.Integer, primary_key=True)
    name_role = db.Column(db.String(100), nullable=False)

    modes = db.relationship(
        "Mode",
        secondary=permissions_table,
    )

    users = db.relationship("Users", secondary=user_roles_table)

    def __repr__(self):
        return "<Role %r>" % self.name_role

    def __str__(self):
        return self.name_role


class Mode(db.Model, SerializationMixin):
    __tablename__ = "Mode"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(255), nullable=False)

    roles = db.relationship(
        "Roles", secondary=permissions_table, back_populates="modes", lazy="joined"
    )

    def __repr__(self):
        return f"{self.title}.{self.action}"
