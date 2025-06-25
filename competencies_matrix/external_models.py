# competencies_matrix/external_models.py
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base, Session
from sqlalchemy.ext.hybrid import hybrid_property # Если используется в as_dict в maps.models
from typing import Dict, Any # Добавляем импорты для типизации в as_dict

# Создаем свою базу для этих моделей, она не будет связана с db из Flask-SQLAlchemy
ExternalBase = declarative_base()

class ExternalSprFaculty(ExternalBase):
    __tablename__ = "spr_faculty"
    id_faculty = Column(Integer, primary_key=True)
    name_faculty = Column(String(255))
    # ... другие поля, если нужны для отображения или фильтрации
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
    # profiles = relationship("ExternalNameOP", back_populates="okco") # Для упрощения, пока без explicit relationships
    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ExternalNameOP(ExternalBase):
    __tablename__ = "spr_name_op"
    id_spec = Column(Integer, primary_key=True)
    program_code = Column(String(255), ForeignKey("spr_okco.program_code"))
    num_profile = Column(String(255))
    name_spec = Column(String(255))
    okco = relationship("ExternalSprOKCO", primaryjoin="ExternalNameOP.program_code == ExternalSprOKCO.program_code", foreign_keys=[program_code])
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
    # ... добавьте другие поля из tbl_aup, которые вам нужны (qualification, type_standard, etc.) ...
    qualification = Column(String(255))
    type_standard = Column(String(255))
    base = Column(String(255))
    period_educ = Column(String(255))
    years = Column(Integer)
    months = Column(Integer)
    year_end = Column(Integer)
    is_actual = Column(Boolean)


    # Relationships (определяем их для удобства запросов через ORM)
    spec = relationship("ExternalNameOP", foreign_keys=[id_spec], lazy='joined')
    form = relationship("ExternalSprFormEducation", foreign_keys=[id_form], lazy='joined')
    degree = relationship("ExternalSprDegreeEducation", foreign_keys=[id_degree], lazy='joined')
    faculty = relationship("ExternalSprFaculty", foreign_keys=[id_faculty], lazy='joined')
    department = relationship("ExternalDepartment", foreign_keys=[id_department], lazy='joined')

    # Копируем as_dict из maps.models.AupInfo, но без специфичных для Flask-SQLAlchemy вещей
    def as_dict(self) -> Dict[str, Any]:
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        # Добавляем поля из джойнов для удобства фронтенда, если они загружены (lazy='joined' должен работать)
        if self.spec:
            data['name_spec'] = self.spec.name_spec
            if self.spec.okco:
                data['program_code'] = self.spec.okco.program_code
                data['name_okco'] = self.spec.okco.name_okco
        if self.form:
            data['form_education_name'] = self.form.form
        if self.degree:
            data['degree_education_name'] = self.degree.name_deg
        if self.faculty:
            data['faculty_name'] = self.faculty.name_faculty
        if self.department:
            data['department_name'] = self.department.name_department
        return data

class ExternalAupData(ExternalBase):
    __tablename__ = "aup_data"
    id = Column(Integer, primary_key=True)
    id_aup = Column(Integer, ForeignKey("tbl_aup.id_aup"))
    shifr = Column(String(30))
    id_discipline = Column(Integer, ForeignKey("spr_discipline.id"))
    
    _discipline_from_table = Column("discipline", String(350)) 
    
    id_period = Column(Integer)
    num_row = Column(Integer)
    id_type_record = Column(Integer)
    zet = Column(Integer)
    id_type_control = Column(Integer)
    amount = Column(Integer)

    spr_discipline = relationship("ExternalSprDiscipline", foreign_keys=[id_discipline], lazy='joined')

    @hybrid_property
    def discipline(self):
        """
        Это гибридное свойство возвращает правильное название дисциплины.
        Оно будет работать и на уровне Python (self.spr_discipline), и на уровне SQL (пока не требуется).
        """
        if self.spr_discipline:
            return self.spr_discipline.title
        return self._discipline_from_table

    def as_dict(self) -> Dict[str, Any]:
        """
        Корректно формирует словарь, используя гибридное свойство `discipline`.
        """
        return {
            'id': self.id,
            'id_aup': self.id_aup,
            'shifr': self.shifr,
            'id_discipline': self.id_discipline,
            'discipline': self.discipline,
            'id_period': self.id_period,
            'num_row': self.num_row,
            'id_type_record': self.id_type_record,
            'zet': self.zet,
            'id_type_control': self.id_type_control,
            'amount': self.amount,
        }

class ExternalSprDiscipline(ExternalBase):
    __tablename__ = "spr_discipline"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))

    def as_dict(self) -> Dict[str, Any]: return {c.name: getattr(self, c.name) for c in self.__table__.columns}