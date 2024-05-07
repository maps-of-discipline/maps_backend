from maps.models import db

faculty_discipline_period_assoc = db.Table(
    'faculty_discipline_period',
    db.Column('discipline_period_id', db.ForeignKey('discipline_period_assoc.id', ondelete='CASCADE')),
    db.Column('faculty_id', db.ForeignKey('spr_faculty.id_faculty', ondelete='CASCADE')),
)

unification_okso_assoc = db.Table(
    'unification_okso_assoc',
    db.Column('unification_id', db.ForeignKey('unification_discipline.id', ondelete='CASCADE')),
    db.Column('okso_id', db.String(255, collation='utf8mb4_unicode_ci'), db.ForeignKey("spr_okco.program_code", ondelete='CASCADE'))
)


class DisciplinePeriodAssoc(db.Model):
    __tablename__ = 'discipline_period_assoc'

    id = db.Column(db.Integer, primary_key=True)
    unification_discipline_id = db.Column(db.Integer, db.ForeignKey('unification_discipline.id', ondelete='CASCADE'))
    period_id = db.Column(db.Integer, db.ForeignKey('d_period.id', ondelete='CASCADE'))

    faculties = db.relationship('SprFaculty', secondary=faculty_discipline_period_assoc, lazy='subquery')
    unification_discipline = db.relationship("UnificationDiscipline")
    period = db.relationship("D_Period", lazy='subquery')
    load = db.relationship("UnificationLoad", lazy='subquery')


class UnificationLoad(db.Model):
    __tablename__ = 'unification_load'
    id = db.Column(db.Integer, primary_key=True)
    education_form_id = db.Column(db.Integer, db.ForeignKey('spr_form_education.id_form', ondelete='CASCADE'))
    discipline_period_assoc_id = db.Column(db.Integer, db.ForeignKey('discipline_period_assoc.id', ondelete='CASCADE'))
    lectures = db.Column(db.Float)
    seminars = db.Column(db.Float)
    srs = db.Column(db.Float)
    practices = db.Column(db.Float)
    control_type_id = db.Column(db.Integer, db.ForeignKey("d_control_type.id"))
    zet = db.Column(db.Float)

    education_form = db.relationship("SprFormEducation", lazy='subquery')
    control_type = db.relationship("D_ControlType", lazy='subquery')

    def as_dict(self):
        attrs = self.__dict__
        attrs.pop('_sa_instance_state')

        attrs.pop('discipline_period_assoc_id')
        attrs.pop('control_type_id')
        attrs.pop('education_form_id')

        attrs['education_form'] = {
            "id": self.education_form.id_form,
            "title": self.education_form.form
        }

        attrs['control_type'] = {
            "id": self.control_type.id,
            "title": self.control_type.title
        }

        return attrs


class UnificationDiscipline(db.Model):
    __tablename__ = 'unification_discipline'

    id = db.Column(db.Integer, primary_key=True)
    discipline = db.Column(db.String(255))
    is_faculties_different = db.Column(db.Boolean)

    ugsn = db.Column(db.String(255))
    degree = db.Column(db.String(255))
    direction = db.Column(db.Boolean(), default=False)

    semesters_count = db.Column(db.Integer)
    amount = db.Column(db.Integer)
    measure_id = db.Column(db.Integer, db.ForeignKey('d_ed_izmereniya.id', ondelete='CASCADE'))

    periods = db.relationship('DisciplinePeriodAssoc', lazy='subquery')
    related_okso = db.relationship("SprOKCO", secondary=unification_okso_assoc)
    measure = db.relationship("D_EdIzmereniya", lazy='subquery')
