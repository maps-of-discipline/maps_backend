# competencies_matrix/external_models.py
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base, Session
from sqlalchemy.ext.hybrid import hybrid_property
from typing import Dict, Any

# Создаем свою базу для этих моделей, она не будет связана с db из Flask-SQLAlchemy
ExternalBase = declarative_base()

class ExternalSprFaculty(ExternalBase):
    __tablename__ = "spr_faculty"
    id_faculty = Column(Integer, primary_key=True)
    name_faculty = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalDepartment(ExternalBase):
    __tablename__ = "tbl_department"
    id_department = Column(Integer, primary_key=True)
    name_department = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalSprDegreeEducation(ExternalBase):
    __tablename__ = "spr_degree_education"
    id_degree = Column(Integer, primary_key=True)
    name_deg = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalSprFormEducation(ExternalBase):
    __tablename__ = "spr_form_education"
    id_form = Column(Integer, primary_key=True)
    form = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalSprOKCO(ExternalBase):
    __tablename__ = "spr_okco"
    program_code = Column(String(255), primary_key=True)
    name_okco = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalNameOP(ExternalBase):
    __tablename__ = "spr_name_op"
    id_spec = Column(Integer, primary_key=True)
    program_code = Column(String(255), ForeignKey("spr_okco.program_code"))
    num_profile = Column(String(255))
    name_spec = Column(String(255))
    okco = relationship("ExternalSprOKCO", primaryjoin="ExternalNameOP.program_code == ExternalSprOKCO.program_code", foreign_keys=[program_code])
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

# <<< НОВЫЕ МОДЕЛИ ВНЕШНИХ СПРАВОЧНИКОВ И ИХ as_dict >>>
class ExternalDBlocks(ExternalBase):
    __tablename__ = "d_blocks"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalDPeriod(ExternalBase):
    __tablename__ = "d_period"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalDControlType(ExternalBase):
    __tablename__ = "d_control_type"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    default_shortname = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalDEdIzmereniya(ExternalBase):
    __tablename__ = "d_ed_izmereniya"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalDPart(ExternalBase):
    __tablename__ = "d_part"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalDTypeRecord(ExternalBase):
    __tablename__ = "d_type_record"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalDModules(ExternalBase):
    __tablename__ = "d_modules"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    color = Column(String(8))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalGroups(ExternalBase):
    __tablename__ = "groups"
    id_group = Column(Integer, primary_key=True)
    name_group = Column(String(255))
    color = Column(String(8))
    weight = Column(Integer)
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalSprDiscipline(ExternalBase):
    __tablename__ = "spr_discipline"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class ExternalAupInfo(ExternalBase):
    __tablename__ = "tbl_aup"
    id_aup = Column(Integer, primary_key=True)
    num_aup = Column(String(255), nullable=False, unique=True)
    id_faculty = Column(Integer, ForeignKey("spr_faculty.id_faculty"))
    id_degree = Column(Integer, ForeignKey("spr_degree_education.id_degree"))
    id_form = Column(Integer, ForeignKey("spr_form_education.id_form"))
    id_spec = Column(Integer, ForeignKey("spr_name_op.id_spec"))
    id_department = Column(Integer, ForeignKey("tbl_department.id_department"))
    year_beg = Column(Integer)
    qualification = Column(String(255))
    type_standard = Column(String(255))
    base = Column(String(255))
    period_educ = Column(String(255))
    years = Column(Integer)
    months = Column(Integer)
    year_end = Column(Integer)
    is_actual = Column(Boolean)

    spec = relationship("ExternalNameOP", foreign_keys=[id_spec], lazy='joined')
    form = relationship("ExternalSprFormEducation", foreign_keys=[id_form], lazy='joined')
    degree = relationship("ExternalSprDegreeEducation", foreign_keys=[id_degree], lazy='joined')
    faculty = relationship("ExternalSprFaculty", foreign_keys=[id_faculty], lazy='joined')
    department = relationship("ExternalDepartment", foreign_keys=[id_department], lazy='joined')

    def as_dict(self) -> Dict[str, Any]:
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if self.spec:
            data['name_spec'] = self.spec.name_spec
            if self.spec.okco:
                data['program_code'] = self.spec.okco.program_code
                data['name_okco'] = self.spec.okco.name_okco
        if self.form: data['form_education_name'] = self.form.form
        if self.degree: data['degree_education_name'] = self.degree.name_deg
        if self.faculty: data['faculty_name'] = self.faculty.name_faculty
        if self.department: data['department_name'] = self.department.name_department
        return data

class ExternalAupData(ExternalBase):
    __tablename__ = "aup_data"
    id = Column(Integer, primary_key=True)
    id_aup = Column(Integer, ForeignKey("tbl_aup.id_aup"))
    shifr = Column(String(30))
    id_discipline = Column(Integer, ForeignKey("spr_discipline.id"))
    _discipline_from_table = Column("discipline", String(350))

    used_for_report = Column(Boolean)

    id_period = Column(Integer, ForeignKey("d_period.id"))
    num_row = Column(Integer)
    id_type_record = Column(Integer, ForeignKey("d_type_record.id"))
    zet = Column(Integer)
    id_type_control = Column(Integer, ForeignKey("d_control_type.id"))
    amount = Column(Integer)
    id_edizm = Column(Integer, ForeignKey("d_ed_izmereniya.id"))

    id_block = Column(Integer, ForeignKey("d_blocks.id"))
    id_part = Column(Integer, ForeignKey("d_part.id"))
    id_module = Column(Integer, ForeignKey("d_modules.id"))
    id_group = Column(Integer, ForeignKey("groups.id_group"))

    spr_discipline = relationship("ExternalSprDiscipline", foreign_keys=[id_discipline], lazy='joined')
    block = relationship("ExternalDBlocks", foreign_keys=[id_block], lazy='joined')
    part = relationship("ExternalDPart", foreign_keys=[id_part], lazy='joined')
    module = relationship("ExternalDModules", foreign_keys=[id_module], lazy='joined')
    type_record_rel = relationship("ExternalDTypeRecord", foreign_keys=[id_type_record], lazy='joined')
    type_control_rel = relationship("ExternalDControlType", foreign_keys=[id_type_control], lazy='joined')
    ed_izmereniya_rel = relationship("ExternalDEdIzmereniya", foreign_keys=[id_edizm], lazy='joined')
    group_rel = relationship("ExternalGroups", foreign_keys=[id_group], lazy='joined')
    period_rel = relationship("ExternalDPeriod", foreign_keys=[id_period], lazy='joined')

    @hybrid_property
    def discipline(self):
        """Returns the actual discipline title from spr_discipline or raw column."""
        if self.spr_discipline: return self.spr_discipline.title
        return self._discipline_from_table

    def as_dict(self) -> Dict[str, Any]:
        """
        Formats ExternalAupData into a dictionary, including names of related lookup tables.
        """
        data = {
            'id': self.id, 'id_aup': self.id_aup, 'shifr': self.shifr,
            'id_discipline': self.id_discipline, 'title': self.discipline,
            'semester': self.id_period,
            'num_row': self.num_row,
            'zet': (self.zet / 100) if self.zet is not None else 0,
            'amount': self.amount,
            'used_for_report': self.used_for_report,
            'id_block': self.id_block, 'block_title': self.block.title if self.block else None,
            'id_part': self.id_part, 'part_title': self.part.title if self.part else None,
            'id_module': self.id_module, 'module_title': self.module.title if self.module else None,
            'module_color': self.module.color if self.module else None,
            'id_group': self.id_group, 'group_name': self.group_rel.name_group if self.group_rel else None,
            'group_color': self.group_rel.color if self.group_rel else None,
            'id_type_record': self.id_type_record, 'type_record_title': self.type_record_rel.title if self.type_record_rel else None,
            'id_type_control': self.id_type_control, 'type_control_title': self.type_control_rel.title if self.type_control_rel else None,
            'id_edizm': self.id_edizm, 'ed_izmereniya_title': self.ed_izmereniya_rel.title if self.ed_izmereniya_rel else None,
            'period_title': self.period_rel.title if self.period_rel else None,
        }
        return data