import sqlalchemy as sa
import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey
from sqlalchemy.ext.associationproxy import association_proxy
from werkzeug.security import check_password_hash, generate_password_hash
from flask_login import UserMixin
from flask import url_for
from user_policy import UsersPolicy
from sqlalchemy.orm import relationship
from sqlalchemy.orm import relationship

# from app import db, app

db = SQLAlchemy()


class SprBranch(db.Model):
    __tablename__ = 'spr_branch'

    id_branch = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255), nullable=False)

    realized_okso = db.relationship("RealizedOkso")

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
    dean = db.Column(db.String(255), nullable=True)

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


# TODO: rename table
class AupInfoHasRuleTable(db.Model):
    __tablename__ = "aup_info_has_rule"

    rule_id = db.Column(db.Integer, db.ForeignKey('tbl_rule.id'), primary_key=True)
    realized_okso_id = db.Column(db.Integer, db.ForeignKey('tbl_realized_okso.id'), primary_key=True)

    min = db.Column(db.Float, nullable=True)
    max = db.Column(db.Float, nullable=True)
    ed_izmereniya_id = db.Column(db.ForeignKey('d_ed_izmereniya.id'))

    rule = db.relationship("Rule", back_populates='aup_info')
    realized_oksos = db.relationship("RealizedOkso", back_populates='rule_associations')


class Rule(db.Model):
    __tablename__ = 'tbl_rule'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    aup_info = db.relationship("AupInfoHasRuleTable", back_populates='rule')

    def __repr__(self):
        return '<Rule %r>' % self.title


class AupInfo(db.Model):
    __tablename__ = 'tbl_aup'

    id_aup = db.Column(db.Integer, primary_key=True)
    file = db.Column(db.String(255), nullable=False)
    num_aup = db.Column(db.String(255), nullable=False)
    base = db.Column(db.String(255), nullable=False)
    id_faculty = db.Column(db.Integer, db.ForeignKey(
        'spr_faculty.id_faculty'), nullable=False)
    id_rop = db.Column(db.Integer, db.ForeignKey(
        'spr_rop.id_rop'), nullable=False)
    type_educ = db.Column(db.String(255), nullable=False)
    qualification = db.Column(db.String(255), nullable=False)
    type_standard = db.Column(db.String(255), nullable=False)
    department = db.Column(db.String(255), nullable=True)
    period_educ = db.Column(db.String(255), nullable=False)
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
    faculty = db.relationship('SprFaculty')
    rop = db.relationship('SprRop')

    aup_data = relationship(
        "AupData",
        back_populates="aup_info"
    )

    def __repr__(self):
        return '<№ AUP %r>' % self.num_aup


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


class SprVolumeDegreeZET(db.Model):
    __tablename__ = 'spr_volume_degree_zet'

    id_volume_deg = db.Column(db.Integer, primary_key=True)
    program_code = db.Column(db.String(255), db.ForeignKey(
        'spr_okco.program_code'), nullable=False)
    id_standard = db.Column(db.Integer, nullable=False)
    zet = db.Column(db.Integer, nullable=False)
    effective_date = db.Column(db.Date, nullable=True)

    progr_code = db.relationship('SprOKCO')

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


class D_Blocks(db.Model):
    __tablename__ = 'd_blocks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<D_Blocks %r>' % self.title


class D_Period(db.Model):
    __tablename__ = 'd_period'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<D_Period %r>' % self.title


class D_ControlType(db.Model):
    __tablename__ = 'd_control_type'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<D_ControlType %r>' % self.title


class D_EdIzmereniya(db.Model):
    __tablename__ = 'd_ed_izmereniya'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<D_EdIzmereniya %r>' % self.title


class D_Part(db.Model):
    __tablename__ = 'd_part'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<D_Part %r>' % self.title


class D_TypeRecord(db.Model):
    __tablename__ = 'd_type_record'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<D_TypeRecord %r>' % self.title


class D_Modules(db.Model):
    __tablename__ = 'd_modules'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<D_Modules %r>' % self.title


class Groups(db.Model):
    __tablename__ = 'groups'
    id_group = db.Column(db.Integer, primary_key=True)
    name_group = db.Column(db.String(255), nullable=False)
    color = db.Column(db.String(8), nullable=False)
    weight = db.Column(db.Integer, nullable=False, default=5)

    def __repr__(self):
        return '<Groups %r>' % self.name_group


class AupData(db.Model):
    __tablename__ = 'aup_data'
    id = db.Column(db.Integer, primary_key=True)
    id_aup = db.Column(db.Integer, db.ForeignKey(
        'tbl_aup.id_aup', ondelete='CASCADE'), nullable=False)
    id_block = db.Column(db.Integer, db.ForeignKey(
        'd_blocks.id'), nullable=False)
    shifr = db.Column(db.String(30), nullable=False)
    id_part = db.Column(db.Integer, db.ForeignKey(
        'd_part.id'), nullable=False)
    id_module = db.Column(db.Integer, db.ForeignKey(
        'd_modules.id'), nullable=False)
    id_group = db.Column(db.Integer, nullable=False)
    id_type_record = db.Column(db.Integer, db.ForeignKey(
        'd_type_record.id'), nullable=False)
    discipline = db.Column(db.String(350), nullable=False)
    id_period = db.Column(db.Integer, nullable=False)
    num_row = db.Column(db.Integer, nullable=False)
    id_type_control = db.Column(db.Integer, db.ForeignKey(
        'd_control_type.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    id_edizm = db.Column(db.Integer, db.ForeignKey(
        'd_ed_izmereniya.id'), nullable=False)
    zet = db.Column(db.Integer, nullable=False)

    block = db.relationship('D_Blocks')
    part = db.relationship('D_Part')
    module = db.relationship('D_Modules')
    record_type = db.relationship('D_TypeRecord')
    type_control = db.relationship('D_ControlType')
    aup = db.relationship('AupInfo')
    ed_izmereniya = db.relationship('D_EdIzmereniya')

    aup_info = relationship(
        "AupInfo",
        back_populates='aup_data'
    )

    def __repr__(self):
        return '<AupData %r>' % self.id_aup


class Users(db.Model, UserMixin):
    __tablename__ = 'tbl_users'
    id_user = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), unique=True, nullable=False)
    id_faculty = db.Column(db.Integer, db.ForeignKey(
        'spr_faculty.id_faculty'), nullable=False)


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return ' '.join([self.last_name, self.first_name, self.middle_name or ''])

    # @property
    # def is_admin(self):
    #     return app.config.get('ADMIN_ROLE_ID') == self.role_id

    # @property
    # def is_moder(self):
    #     return app.config.get('MODER_ROLE_ID') == self.role_id

    # @property
    # def is_user(self):
    #     return app.config.get('USER_ROLE_ID') == self.role_id

    # def can(self, action):
    #     users_policy = UsersPolicy()
    #     method = getattr(users_policy, action)
    #     if method is not None:
    #         return method()
    #     return False

    def __repr__(self):
        return '<User %r>' % self.login


# --------------checks---------------- #


class DBase(db.Model):
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f'<{self.__tablename__} {self.title}>'


class DCompetencyCode(DBase):
    __tablename__ = 'd_competency_code'


class DSpecializationType(DBase):
    __tablename__ = 'd_specialization_type'


class DTypeStandard(DBase):
    __tablename__ = 'd_type_standard'


class DGeneration(DBase):
    __tablename__ = 'd_generation'


fgosvo_has_compulsory_discipline_table = db.Table(
    'fgosvo_has_compulsory_discipline',
    db.Column("fgosvo_id", db.ForeignKey('spr_fgos_vo.id')),
    db.Column("compulsory_discipline_id", db.ForeignKey('spr_compulsory_discipline.id'))
)

fgosvo_has_competency_table = db.Table(
    'fgosvo_has_competency',
    db.Column("fgosvo_id", db.ForeignKey('spr_fgos_vo.id'), nullable=False),
    db.Column("competency_id", db.ForeignKey('spr_competency.id'), nullable=False)
)

fgosvo_has_specialization_table = db.Table(
    'fgosvo_has_specialization',
    db.Column("fgosvo_id", db.ForeignKey('spr_fgos_vo.id'), nullable=False),
    db.Column("specialization_id", db.ForeignKey('spr_specialization.id'), nullable=False)
)

specialization_has_additional_competency_table = db.Table(
    'specialization_has_additional_competency',
    db.Column('specialization_id', db.ForeignKey("spr_specialization.id"), nullable=False),
    db.Column('additional_competency_id', db.ForeignKey("spr_additional_competency.id"), nullable=False)
)


class SprFgosVo(db.Model):
    __tablename__ = 'spr_fgos_vo'

    id = db.Column(db.Integer, primary_key=True)
    realized_okso_id = db.Column(db.Integer, db.ForeignKey('tbl_realized_okso.id'), nullable=False)
    IsActive = db.Column(db.Integer, nullable=False)
    number = db.Column(db.Integer, nullable=False)
    approval_date = db.Column(db.Date, nullable=False)
    modification_date = db.Column(db.Date, nullable=False)
    active_form = db.Column(db.Date, nullable=False)
    type_standard_id = db.Column(db.Integer, db.ForeignKey('d_type_standard.id'), nullable=False)
    generation_id = db.Column(db.Integer, db.ForeignKey('d_generation.id'), nullable=False)

    specializations = db.relationship(
        "SprSpecialization",
        secondary=fgosvo_has_specialization_table,
        back_populates="fgos_vo"
    )
    compulsory_disciplines = db.relationship(
        "SprCompulsoryDiscipline",
        secondary=fgosvo_has_compulsory_discipline_table,
        back_populates="fgos_vo"
    )
    competencies = db.relationship(
        "SprCompetency",
        secondary=fgosvo_has_competency_table,
        back_populates="fgos_vo"
    )

    def __repr__(self):
        return '<SprFgosVo %r>' % self.id


class SprSpecialization(db.Model):
    __tablename__ = 'spr_specialization'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    d_specialization_type_id = db.Column(db.Integer, db.ForeignKey('d_specialization_type.id'), nullable=False)

    fgos_vo = relationship(
        "SprFgosVo",
        secondary=fgosvo_has_specialization_table,
        back_populates="specializations"
    )

    additional_competencies = relationship(
        "SprAdditionalCompetency",
        secondary=specialization_has_additional_competency_table,
        back_populates='specializations'
    )

    specialisation_type = db.relationship('DSpecializationType')

    def __repr__(self):
        return '<DegreeEducation %r>' % self.title


class SprCompulsoryDiscipline(db.Model):
    __tablename__ = 'spr_compulsory_discipline'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    fgos_vo = relationship(
        "SprFgosVo",
        secondary=fgosvo_has_compulsory_discipline_table,
        back_populates="compulsory_disciplines"
    )

    def __repr__(self):
        return '<DegreeEducation %r>' % self.name


class SprCompetency(db.Model):
    __tablename__ = 'spr_competency'

    id = db.Column(db.Integer, primary_key=True)
    code_number = db.Column(db.Integer, nullable=False)
    d_competency_code_id = db.Column(db.Integer, db.ForeignKey('d_competency_code.id'), nullable=False)
    title = db.Column(db.String(511), nullable=False)

    competency_code = db.relationship('DCompetencyCode')

    fgos_vo = db.relationship(
        "SprFgosVo",
        secondary=fgosvo_has_competency_table,
        back_populates="competencies"
    )

    def __repr__(self):
        return '<DegreeEducation %r>' % self.title


class SprAdditionalCompetency(db.Model):
    __tablename__ = 'spr_additional_competency'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    Code = db.Column(db.Float, nullable=False)
    d_competency_code_id = db.Column(db.Integer, db.ForeignKey('d_competency_code.id'), nullable=False)

    competency_code = db.relationship('DCompetencyCode')

    specializations = relationship(
        "SprSpecialization",
        secondary=specialization_has_additional_competency_table,
        back_populates='additional_competencies'
    )

    def __repr__(self):
        return '<DegreeEducation %r>' % self.title


class RealizedOkso(db.Model):
    __tablename__ = 'tbl_realized_okso'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('spr_branch.id_branch'), nullable=False)
    program_code = db.Column(db.String(255), db.ForeignKey('spr_okco.program_code'), primary_key=True)

    branch = db.relationship('SprBranch')
    okco = db.relationship('SprOKCO')

    rule_associations = db.relationship("AupInfoHasRuleTable", back_populates="realized_oksos")
    rules = association_proxy('rule_associations', "rule")

    def __repr__(self):
        return '<DegreeEducation %r>' % self.program_code


