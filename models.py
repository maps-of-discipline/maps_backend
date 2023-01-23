import sqlalchemy as sa
import os
from flask_sqlalchemy import SQLAlchemy
# from app import db, app

db = SQLAlchemy()


class SprBranch(db.Model):
    __tablename__ = 'spr_branch'

    id_branch = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<Branch %r>' % self.location


class SprDegreeEducation(db.Model):
    __tablename__ = 'spr_degree_education'

    id_degree = db.Column(db.Integer, primary_key=True)
    name_deg = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<DegreeEducation %r>' % self.name_deg


class SprFaculty(db.Model):
    __tablename__ = 'spr_faculty'

    id_faculty = db.Column(db.Integer, primary_key=True)
    name_faculty = db.Column(db.String(255), nullable=False)
    id_branch = db.Column(db.Integer, db.ForeignKey(
        'spr_branch.id_branch'), nullable=False)
    dean = db.Column(db.String(255), nullable=False)

    branch = db.relationship('SprBranch')

    def __repr__(self):
        return '<Faculty %r>' % self.name_faculty


class SprFormEducation(db.Model):
    __tablename__ = 'spr_form_education'

    id_form = db.Column(db.Integer, primary_key=True)
    form = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<FormEducation %r>' % self.form


class SprOKCO(db.Model):
    __tablename__ = 'spr_okco'

    program_code = db.Column(db.String(255), primary_key=True)
    name_okco = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<OKCO %r>' % self.name_okco


class SprRop(db.Model):
    __tablename__ = 'spr_rop'

    id_rop = db.Column(db.Integer, primary_key=True)
    last_name = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(255), nullable=False)
    middle_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    telephone = db.Column(db.String(255), nullable=False)

    @property
    def full_name(self):
        return ' '.join([self.last_name, self.first_name, self.middle_name or ''])

    def __repr__(self):
        return '<Rop %r>' % self.full_name


class AUP(db.Model):
    __tablename__ = 'tbl_aup'

    id_aup = db.Column(db.Integer, primary_key=True)
    id_op = db.Column(db.Integer, db.ForeignKey(
        'tbl_op.id_op', ondelete='CASCADE'))
    file = db.Column(db.String(255), nullable=False)
    num_aup = db.Column(db.String(255), nullable=False)
    base = db.Column(db.String(255), nullable=False)

    op = db.relationship('OP')

    def __repr__(self):
        return '<№ AUP %r>' % self.num_aup


class DurationEducation(db.Model):
    __tablename__ = 'tbl_duration_edu'

    id_duration = db.Column(db.Integer, primary_key=True)
    id_degree = db.Column(db.Integer, db.ForeignKey(
        'spr_degree_education.id_degree'), nullable=False)
    id_form = db.Column(db.Integer, db.ForeignKey(
        'spr_form_education.id_form'), nullable=False)
    years = db.Column(db.Integer, nullable=False)
    months = db.Column(db.Integer, nullable=True)
    id_spec = db.Column(db.Integer, db.ForeignKey(
        'spr_name_op.id_spec'), nullable=False)
    year_beg = db.Column(db.Integer, nullable=False)
    year_end = db.Column(db.Integer, nullable=False)
    is_actual = db.Column(db.Boolean, nullable=False)

    degree = db.relationship('SprDegreeEducation')
    form = db.relationship('SprFormEducation')
    name_op = db.relationship('NameOP')

    @property
    def full_text(self):
        return '{} гг {} мм '.format(self.years, self.months)

    def __repr__(self):
        return '<DurationEducation %r>' % self.full_text


class OP(db.Model):
    __tablename__ = 'tbl_op'

    id_op = db.Column(db.Integer, primary_key=True)
    id_duration = db.Column(db.Integer, db.ForeignKey(
        'tbl_duration_edu.id_duration'), nullable=False)
    id_faculty = db.Column(db.Integer, db.ForeignKey(
        'spr_faculty.id_faculty'), nullable=False)
    id_rop = db.Column(db.Integer, db.ForeignKey(
        'spr_rop.id_rop'), nullable=False)
    type_educ = db.Column(db.String(255), nullable=False)
    qualification = db.Column(db.String(255), nullable=False)
    type_standard = db.Column(db.String(255), nullable=False)
    department = db.Column(db.String(255), nullable=True)
    period_educ = db.Column(db.String(255), nullable=False)

    duration = db.relationship('DurationEducation')
    faculty = db.relationship('SprFaculty')
    rop = db.relationship('SprRop')

    def __repr__(self):
        return '<ID_OP %r>' % self.id_op


class NameOP(db.Model):
    __tablename__ = 'spr_name_op'

    id_spec = db.Column(db.Integer, primary_key=True)
    program_code = db.Column(db.String(255), db.ForeignKey(
        'spr_okco.program_code'), nullable=False)
    num_profile = db.Column(db.String(255), nullable=False)
    name_spec = db.Column(db.String(255), nullable=False)

    okco = db.relationship('SprOKCO')

    def __repr__(self):
        return '<NameOP %r>' % self.id_spec


class Workload(db.Model):
    __tablename__ = 'workload'

    id_workload = db.Column(db.Integer, primary_key=True)
    id_aup = db.Column(db.Integer, db.ForeignKey(
        'tbl_aup.id_aup', ondelete='CASCADE'), nullable=False)
    block = db.Column(db.Integer, nullable=False)
    cypher = db.Column(db.String(255), nullable=False)
    part = db.Column(db.Integer, nullable=True)
    id_group = db.Column(db.Integer, db.ForeignKey(
        'tbl_group.id_group'), nullable=False)
    module = db.Column(db.Integer, db.ForeignKey(
        'tbl_module.id_module'), nullable=False)
    record_type = db.Column(db.Integer, nullable=False)
    discipline = db.Column(db.String(255), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    sequence_num_col = db.Column(db.Integer, nullable=False)
    load = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    measurement = db.Column(db.Integer, nullable=False)
    zet = db.Column(db.Integer, nullable=False)

    module = db.relationship('Module')
    aup = db.relationship('AUP')
    group = db.relationship('Grouping')

    def __repr__(self):
        return '<Workload %r>' % self.id_workload


class Module(db.Model):
    __tablename__ = 'tbl_module'

    id_module = db.Column(db.Integer, primary_key=True)
    name_module = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<Module.NameModule %r>' % self.name_module


class Grouping(db.Model):
    __tablename__ = 'tbl_group'

    id_group = db.Column(db.Integer, primary_key=True)
    name_group = db.Column(db.String(255), nullable=False)
    color = db.Column(db.String(8), nullable=False)

    def __repr__(self):
        return '<Grouping.NameGroup %r>' % self.name_group


class SprVolumeDegreeZET(db.Model):
    __tablename__ = 'spr_volume_degree_zet'

    id_volume_deg = db.Column(db.Integer, primary_key=True)
    program_code = db.Column(db.String(255), db.ForeignKey(
        'spr_okco.program_code'), nullable=False)
    id_standard = db.Column(db.Integer, nullable=False)
    zet = db.Column(db.Integer, nullable=False)
    effective_date = db.Column(db.Date, nullable=True)

    program_code = db.relationship('SprOKCO')

    @property
    def volume_degree_zet(self):
        return 'id: {}, program_code: {}, type_standard: {}, ZET: {}, effective date: {}'.format(self.id_volume_deg, self.program_code, self.id_standard, self.zet, self.effective_date)

    def __repr__(self):
        return '<SprVolumeDegreeZET %r>' % self.volume_degree_zet


class SprStandard(db.Model):
    __tablename__ = 'spr_standard_zet'

    id_standard = db.Column(db.Integer, primary_key=True)
    type_standard = db.Column(db.String(255), nullable=False)

    @property
    def standard_date(self):
        return 'id: {}, type_standard: {}'.format(self.id_standard, self.type_standard)

    def __repr__(self):
        return '<SprStandardZET %r>' % self.standard_date