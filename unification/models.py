from maps.models import db


class Unification(db.Model):
    __tablename__ = "unification"

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(255), nullable=False)
    year = db.Column(db.Date, nullable=False)
    zet = db.Column(db.Float)

    disciplines = db.relationship('Okso_discipline')


class Okso_discipline(db.Model):
    __tablename__ = 'okso_discipline'

    id = db.Column(db.Integer, primary_key=True)
    unification_id = db.Column(db.Integer, db.ForeignKey(
        'unification.id', ondelete="CASCADE"), nullable=False)
    ugsn = db.Column(db.String(10), nullable=False)
    level = db.Column(db.String(10), nullable=False)
    direction = db.Column(db.String(10), nullable=False)

    semesters_quantity = db.Column(db.Integer, nullable=False)
    id_equal_for_all_semesters = db.Column(db.Boolean, nullable=False)

    unification = db.relationship("Unification")
    faculty_relations = db.relationship("DisciplineFacultyRelation")


class DisciplineFacultyRelation(db.Model):
    __tablename__ = "discipline_faculty_relation"

    id = db.Column(db.Integer, primary_key=True)
    okso_discipline_id = db.Column(db.Integer, db.ForeignKey(
        'okso_discipline.id', ondelete="CASCADE"), nullable=False)
    for_all_faculty = db.Column(db.Boolean, nullable=False)
    zet = db.Column(db.Float, nullable=False)

    discipline = db.relationship("Okso_discipline")
    faculties = db.relationship('SprFaculty', secondary="discipline_has_faculties")


discipline_has_faculties = db.Table(
    'discipline_has_faculties',
    db.Column("discipline_faculty_relation_id", db.ForeignKey('discipline_faculty_relation.id'), nullable=False),
    db.Column('spr_faculty_id', db.ForeignKey("spr_faculty.id_faculty"), nullable=False)
)


class Specification(db.Model):
    __tablename__ = 'specification'

    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("d_period.id"), nullable=False)
    control_type_id = db.Column(db.Integer, db.ForeignKey("d_control_type.id"), nullable=False)
    discipline_faculty_relation_id = db.Column(db.Integer, db.ForeignKey("discipline_faculty_relation.id"),
                                               nullable=False)
    lectures = db.Column(db.Float)
    practical = db.Column(db.Float)
    seminars = db.Column(db.Float)

    period = db.relationship('D_Period')
    conrtol_type = db.relationship("D_ControlType")
