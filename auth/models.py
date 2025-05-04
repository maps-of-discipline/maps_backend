from werkzeug.security import generate_password_hash, check_password_hash

from maps.models import db, SerializationMixin

users_faculty_table = db.Table(
    "users_faculty",
    db.Column("user_id", db.ForeignKey("tbl_users.id", ondelete="CASCADE"), nullable=False),
    db.Column("faculty_id", db.ForeignKey("spr_faculty.id_faculty", ondelete="CASCADE"), nullable=False),
)

class Users(db.Model, SerializationMixin):
    __tablename__ = "tbl_users"

    id = db.Column(db.String(36), primary_key=True)
    login = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), nullable=True)

    faculties = db.Relationship(
        "SprFaculty",
        secondary=users_faculty_table,
    )

    control_type_shortnames = db.relationship(
        'ControlTypeShortName',
    )

    def __repr__(self):
        return "<User %r>" % self.login

    def __str__(self):
        return self.login