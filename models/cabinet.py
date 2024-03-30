from .maps import db
from sqlalchemy_serializer import SerializerMixin

class RPD(db.Model, SerializerMixin):
    __tablename__ = 'rpd'

    serialize_only = ('id', 'id_aup', 'id_unique_discipline')

    id: int = db.Column(db.Integer(), primary_key=True)
    id_aup: int = db.Column(db.Integer(), db.ForeignKey('tbl_aup.id_aup'), nullable=False)
    id_unique_discipline: int = db.Column(db.Integer(), db.ForeignKey('spr_discipline.id'), nullable=False)

    aupData = db.relationship('AupInfo')
    sprDiscipline = db.relationship('SprDiscipline')

class Topics(db.Model, SerializerMixin):
    __tablename__ = 'topic'

    serialize_only = ('id', 'topic', 'chapter', 'id_type_control', 'task_link', 'task_link_name', 'completed_task_link', 'completed_task_link_name', 'id_rpd', 'semester')

    id: int = db.Column(db.Integer(), primary_key=True)
    topic: str = db.Column(db.String(400), nullable=True)
    chapter: str = db.Column(db.String(400), nullable=True)
    id_type_control = db.Column(db.Integer(), db.ForeignKey('d_control_type.id'), nullable=True)
    task_link: str = db.Column(db.String(400), nullable=True)
    task_link_name: str = db.Column(db.String(255), nullable=True)
    completed_task_link: str = db.Column(db.String(255), nullable=True)
    completed_task_link_name: str = db.Column(db.String(255), nullable=True)
    id_rpd: int = db.Column(db.Integer(), db.ForeignKey('rpd.id'))
    semester: int = db.Column(db.Integer())

    d_control_type = db.relationship('D_ControlType')
    rpd = db.relationship('RPD')