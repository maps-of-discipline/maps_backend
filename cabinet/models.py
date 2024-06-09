from sqlalchemy_serializer import SerializerMixin

from maps.models import db

# Таблица с оценками
class DisciplineTable(db.Model, SerializerMixin):
    __tablename__ = 'discipline_table'

    serialize_only = ('id', 'id_aup', 'id_unique_discipline', 'study_group_id', 'semester')

    id: int = db.Column(db.Integer(), primary_key=True)
    id_aup: int = db.Column(db.Integer(), db.ForeignKey('tbl_aup.id_aup'), nullable=False)
    id_unique_discipline: int = db.Column(db.Integer(), db.ForeignKey('spr_discipline.id'), nullable=False)
    study_group_id: int = db.Column(db.Integer(), db.ForeignKey('study_group.id'), nullable=False)
    semester: int = db.Column(db.Integer(), nullable=False)

    grade_columns = db.relationship('GradeColumn')
    grade_types = db.relationship('GradeType')
    topics = db.relationship('Topics', back_populates="discipline_table", lazy="joined")

class Topics(db.Model, SerializerMixin):
    __tablename__ = 'topic'

    serialize_only = ('id', 'topic', 'chapter', 'id_type_control', 'task_link', 'task_link_name', 'completed_task_link',
                      'completed_task_link_name', 'discipline_table_id', 'study_group_id', 'date', 'lesson_order',
                      'date_task_finish', 'date_task_finish_include', 'spr_bells_id', 'spr_place_id', 'place_note', 'note')

    id: int = db.Column(db.Integer(), primary_key=True)
    discipline_table_id: int = db.Column(db.Integer(), db.ForeignKey('discipline_table.id'))
    topic: str = db.Column(db.String(400), nullable=True)
    chapter: str = db.Column(db.String(400), nullable=True)
    id_type_control = db.Column(db.Integer(), db.ForeignKey('d_control_type.id'), nullable=True)
    task_link: str = db.Column(db.String(400), nullable=True)
    task_link_name: str = db.Column(db.String(255), nullable=True)
    completed_task_link: str = db.Column(db.String(255), nullable=True)
    completed_task_link_name: str = db.Column(db.String(255), nullable=True)
    study_group_id: int = db.Column(db.Integer(), db.ForeignKey('study_group.id'), nullable=False)

    date = db.Column(db.DateTime())
    lesson_order = db.Column(db.Integer())
    spr_bells_id = db.Column(db.Integer, db.ForeignKey("spr_bells.id"), nullable=True)
    date_task_finish = db.Column(db.DateTime())
    date_task_finish_include = db.Column(db.Boolean, default=False)

    spr_place_id = db.Column(db.Integer, db.ForeignKey("spr_place.id"), nullable=True)
    place_note = db.Column(db.String(400), nullable=True)
    note = db.Column(db.String(400), nullable=True)

    d_control_type = db.relationship('D_ControlType')
    discipline_table = db.relationship('DisciplineTable', back_populates="topics")


class StudyGroups(db.Model, SerializerMixin):
    __tablename__ = 'study_group'

    serialize_only = ('id', 'title', 'num_aup')

    id: int = db.Column(db.Integer(), primary_key=True)
    title: str = db.Column(db.String(255), nullable=False)
    num_aup: str = db.Column(db.String(255), nullable=False)
    tutor_id: int = db.Column(db.Integer, db.ForeignKey('tutors.id'), nullable=True)

    students = db.relationship("Students")

class SprPlace(db.Model, SerializerMixin):
    __tablename__ = 'spr_place'

    serialize_only = ('id', 'name', 'prefix', 'is_online')

    id: int = db.Column(db.Integer(), primary_key=True)
    name: str = db.Column(db.String(255), nullable=False)
    prefix: str = db.Column(db.String(255), nullable=False)
    is_online: str = db.Column(db.Boolean(), nullable=False, default=False)

class Students(db.Model, SerializerMixin):
    __tablename__ = 'students'

    serialize_only = ('id', 'name', 'study_group_id', 'lk_id')

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(400), nullable=False)
    study_group_id = db.Column(db.Integer, db.ForeignKey('study_group.id'), nullable=False)
    lk_id = db.Column(db.Integer, nullable=False)

    grades = db.relationship('Grade', back_populates='student', lazy='joined')


    def __repr__(self):
        return F"<Student {self.id} {self.name}>"

class Tutors(db.Model, SerializerMixin):
    __tablename__ = 'tutors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(400), nullable=False)
    lk_id = db.Column(db.Integer, nullable=False)
    post = db.Column(db.String(400))

    id_department = db.Column(db.Integer, db.ForeignKey('tbl_department.id_department'), nullable=False)

    def __repr__(self):
        return F"<Tutors {self.lk_id} {self.name}>"

# Таблица с оценками
class GradeTable(db.Model, SerializerMixin):
    __tablename__ = 'grade_table'

    serialize_only = ('id', 'id_aup', 'id_unique_discipline', 'study_group_id', 'semester')

    id: int = db.Column(db.Integer(), primary_key=True)
    id_aup: int = db.Column(db.Integer(), db.ForeignKey('tbl_aup.id_aup'), nullable=False)
    id_unique_discipline: int = db.Column(db.Integer(), db.ForeignKey('spr_discipline.id'), nullable=False)
    semester: int = db.Column(db.Integer(), nullable=False)
    study_group_id: int = db.Column(db.Integer(), db.ForeignKey('study_group.id'), nullable=False)

# Оценки
class Grade(db.Model, SerializerMixin):
    __tablename__ = 'grades'

    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Integer)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    grade_column_id = db.Column(db.Integer, db.ForeignKey("grade_column.id", ondelete="CASCADE"), nullable=False)

    grade_column = db.relationship('GradeColumn', back_populates='grades', lazy='joined')
    student = db.relationship('Students', back_populates='grades', lazy='joined')


    def __repr__(self):
        return f"<Grade {self.id} {self.value}"

class GradeColumn(db.Model, SerializerMixin):
    __tablename__ = 'grade_column'

    id = db.Column(db.Integer, primary_key=True)
    discipline_table_id = db.Column(db.Integer, db.ForeignKey("discipline_table.id"), nullable=False)
    grade_type_id = db.Column(db.Integer, db.ForeignKey("grade_type.id", ondelete="CASCADE"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("topic.id"), nullable=True)
    hidden = db.Column(db.Boolean, nullable=False, default=False)

    grade_type = db.relationship('GradeType')
    topic = db.relationship('Topics')
    grades = db.relationship("Grade", back_populates="grade_column")

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
    color = db.Column(db.String(255), nullable=True)
    is_custom = db.Column(db.Boolean, default=False)

    discipline_table_id = db.Column(db.Integer, db.ForeignKey("discipline_table.id"), nullable=False)


class SprBells(db.Model, SerializerMixin):
    __tablename__ = 'spr_bells'

    serialize_only = ('id', 'order', 'name')

    id = db.Column(db.Integer, primary_key=True)
    order = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(255), nullable=False)

class TutorsOrder(db.Model, SerializerMixin):
    __tablename__ = 'tutors_order'

    id = db.Column(db.Integer, primary_key=True)

    # Для какого факультета
    faculty_id = db.Column(db.Integer, db.ForeignKey("spr_faculty.id_faculty"), nullable=False)
    # Дата распоряжения
    date = db.Column(db.DateTime())
    # Номер распоряжения
    num_order = db.Column(db.Integer, nullable=False)
    # Форма обучения
    spr_form_education_id = db.Column(db.Integer, db.ForeignKey("spr_form_education.id_form"))
    # На какой год распоряжение
    year = db.Column(db.Integer, nullable=False)
    # На какой год распоряжение
    executor = db.Column(db.String(255), nullable=False)
    # На какой год распоряжение
    signer = db.Column(db.String(255), nullable=False)

    form_education = db.relationship('SprFormEducation')

class TutorsOrderRow(db.Model, SerializerMixin):
    __tablename__ = 'tutors_order_row'

    id = db.Column(db.Integer, primary_key=True)

    tutors_order_id = db.Column(db.Integer, db.ForeignKey('tutors_order.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('tbl_department.id_department'), nullable=False)
    study_group_id = db.Column(db.Integer(), db.ForeignKey('study_group.id'), nullable=False)
    tutor_id = db.Column(db.Integer, db.ForeignKey('tutors.id'))

    tutor = db.relationship('Tutors')
    department = db.relationship('Department')
    study_group = db.relationship('StudyGroups')

""" class Tutors(db.Model, SerializerMixin):
    __tablename__ = 'tutors_order'

    id = db.Column(db.Integer, primary_key=True)
    lk_id = db.Column(db.Integer) """