from werkzeug.security import generate_password_hash, check_password_hash

from maps.models import db, SerializationMixin

users_faculty_table = db.Table(
    "users_faculty",
    db.Column("user_id", db.ForeignKey("tbl_users.id_user", ondelete="CASCADE"), nullable=False),
    db.Column("faculty_id", db.ForeignKey("spr_faculty.id_faculty", ondelete="CASCADE"), nullable=False),
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

    faculties = db.Relationship(
        "SprFaculty",
        secondary=users_faculty_table,
    )

    department = db.Relationship(
        "Department",
    )

    control_type_shortnames = db.relationship(
        'ControlTypeShortName',
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return "<User %r>" % self.login

    def __str__(self):
        return self.login