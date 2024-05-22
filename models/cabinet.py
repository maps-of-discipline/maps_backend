from sqlalchemy_serializer import SerializerMixin

from .maps import db


class RPD(db.Model, SerializerMixin):
    __tablename__ = 'rpd'

    serialize_only = ('id', 'id_aup', 'id_unique_discipline')

    id: int = db.Column(db.Integer(), primary_key=True)
    id_aup: int = db.Column(db.Integer(), db.ForeignKey('tbl_aup.id_aup'), nullable=False)
    id_unique_discipline: int = db.Column(db.Integer(), db.ForeignKey('spr_discipline.id'), nullable=False)

    aupData = db.relationship('AupInfo')
    sprDiscipline = db.relationship('SprDiscipline')
    topics = db.relationship('Topics', back_populates="rpd", lazy="joined")


class Topics(db.Model, SerializerMixin):
    __tablename__ = 'topic'

    serialize_only = ('id', 'topic', 'chapter', 'id_type_control', 'task_link', 'task_link_name', 'completed_task_link',
                      'completed_task_link_name', 'id_rpd', 'semester', 'study_group_id', 'date', 'lesson_order',
                      'date_task_finish', 'date_task_finish_include', 'spr_bells_id')

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
    study_group_id: int = db.Column(db.Integer(), db.ForeignKey('study_group.id'), nullable=False)

    date = db.Column(db.DateTime())
    lesson_order = db.Column(db.Integer())
    spr_bells_id = db.Column(db.Integer, db.ForeignKey("spr_bells.id"), nullable=True)
    date_task_finish = db.Column(db.DateTime())
    date_task_finish_include = db.Column(db.Boolean, default=False)

    d_control_type = db.relationship('D_ControlType')
    rpd = db.relationship('RPD', back_populates="topics")


class StudyGroups(db.Model, SerializerMixin):
    __tablename__ = 'study_group'

    serialize_only = ('id', 'title', 'num_aup')

    id: int = db.Column(db.Integer(), primary_key=True)
    title: str = db.Column(db.String(255), nullable=False)
    num_aup: str = db.Column(db.String(255), nullable=False)


class Students(db.Model, SerializerMixin):
    __tablename__ = 'students'

    serialize_only = ('id', 'name', 'study_group_id', 'lk_id')

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(400), nullable=False)
    study_group_id = db.Column(db.Integer, db.ForeignKey('study_group.id'), nullable=False)
    lk_id = db.Column(db.Integer, nullable=False)

    grades = db.relationship('Grade', back_populates='student', lazy='joined')


# Таблица с оценками
class GradeTable(db.Model, SerializerMixin):
    __tablename__ = 'grade_table'

    serialize_only = ('id', 'id_aup', 'id_unique_discipline', 'study_group_id', 'semester')

    id: int = db.Column(db.Integer(), primary_key=True)
    id_aup: int = db.Column(db.Integer(), db.ForeignKey('tbl_aup.id_aup'), nullable=False)
    id_unique_discipline: int = db.Column(db.Integer(), db.ForeignKey('spr_discipline.id'), nullable=False)
    semester: int = db.Column(db.Integer(), nullable=False)
    study_group_id: int = db.Column(db.Integer(), db.ForeignKey('study_group.id'), nullable=False)

    grade_columns = db.relationship('GradeColumn', lazy='joined')


# Оценки
class Grade(db.Model, SerializerMixin):
    __tablename__ = 'grades'

    id = db.Column(db.Integer, primary_key=True)
    grade_table_id = db.Column(db.Integer, db.ForeignKey("grade_table.id"), nullable=False)
    value = db.Column(db.Integer)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    grade_column_id = db.Column(db.Integer, db.ForeignKey("grade_column.id"), nullable=False)

    grade_column = db.relationship('GradeColumn')
    student = db.relationship('Students', back_populates='grades')


class GradeColumn(db.Model, SerializerMixin):
    __tablename__ = 'grade_column'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(400), nullable=True)
    grade_table_id = db.Column(db.Integer, db.ForeignKey("grade_table.id"), nullable=False)
    grade_type_id = db.Column(db.Integer, db.ForeignKey("grade_type.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("topic.id"), nullable=True)

    grade_type = db.relationship('GradeType')


# Виды оценивания (посещаемость, активность, задания)
class GradeType(db.Model, SerializerMixin):
    __tablename__ = 'grade_type'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(255), nullable=False)
    min_grade = db.Column(db.Integer, default=2)
    max_grade = db.Column(db.Integer, default=5)
    archived = db.Column(db.Boolean, default=False)
    binary = db.Column(db.Boolean, default=False)
    weight_grade = db.Column(db.Integer, default=1)

    grade_table_id = db.Column(db.Integer, db.ForeignKey("grade_table.id"), nullable=False)


class SprBells(db.Model, SerializerMixin):
    __tablename__ = 'spr_bells'

    serialize_only = ('id', 'order', 'name')

    id = db.Column(db.Integer, primary_key=True)
    order = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(255), nullable=False)
