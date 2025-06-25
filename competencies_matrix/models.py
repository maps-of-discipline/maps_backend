# filepath: competencies_matrix/models.py
from maps.models import db, AupInfo, AupData, SprDiscipline
try:
    from auth.models import Users
    USERS_MODEL_AVAILABLE = True
except ImportError:
    USERS_MODEL_AVAILABLE = False
    class Users:
        id_user = None
        pass

from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relationship, backref
from sqlalchemy import inspect
from typing import List, Dict, Any, Optional
import datetime
import re

from sqlalchemy.types import TypeEngine 
try:
    _ = db.JSON
except AttributeError:
    db.JSON = db.Column(TypeEngine)

def to_snake_case(name: str) -> str:
    """Converts a PascalCase string to snake_case."""
    name = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower()

class BaseModel:
    """Base class for models with common functionality like ID, timestamps, and to_dict method."""

    @declared_attr
    def __tablename__(cls):
        return f"competencies_{to_snake_case(cls.__name__)}"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Converts SQLAlchemy model instance to a dictionary.
        Args:
            rules: List of attributes to exclude (prefixed with '-').
            only: List of attributes to include (if provided, only these will be included).
        """
        result = {}
        exclude_columns = set()
        if rules:
            for exclusion_rule in rules:
                if exclusion_rule.startswith('-'):
                    exclude_columns.add(exclusion_rule[1:])

        for c in inspect(self).mapper.column_attrs:
            if only and c.key not in only:
                continue
            if c.key in exclude_columns:
                continue
            value = getattr(self, c.key)
            if isinstance(value, (datetime.date, datetime.datetime)):
                 result[c.key] = value.isoformat()
            elif isinstance(value, dict) or isinstance(value, list):
                result[c.key] = value
            else:
                 result[c.key] = value

        return result

class FgosVo(db.Model, BaseModel):
    """ФГОС ВО (Федеральный государственный образовательный стандарт высшего образования)"""

    number = db.Column(db.String(50), nullable=False, comment='Номер приказа')
    date = db.Column(db.Date, nullable=False, comment='Дата утверждения')
    direction_code = db.Column(db.String(10), nullable=False, comment='Код направления, например 09.03.01')
    direction_name = db.Column(db.String(255), nullable=False, comment='Название направления')
    education_level = db.Column(db.String(50), nullable=False, comment='Уровень образования (бакалавриат/магистратура/аспирантура)')
    generation = db.Column(db.String(10), nullable=False, comment='Поколение ФГОС (3+, 3++)')
    file_path = db.Column(db.String(255), nullable=True, comment='Путь к PDF файлу')
    recommended_ps_parsed_data = db.Column(db.JSON, nullable=True, comment='JSON массив рекомендованных ПС из PDF ФГОС')


    # ИЗМЕНЕНИЕ: Добавлено primaryjoin для явного определения условия объединения
    educational_programs = relationship(
        'EducationalProgram',
        back_populates='fgos',
        primaryjoin="FgosVo.id == EducationalProgram.fgos_vo_id"
    )
    recommended_ps_assoc = relationship('FgosRecommendedPs', back_populates='fgos', cascade="all, delete-orphan")
    competencies = relationship('Competency', back_populates='fgos', cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ФГОС {self.direction_code} ({self.generation})>"

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None) -> Dict[str, Any]:
        data = super().to_dict(rules=rules, only=only)
        return data

class EducationalProgram(db.Model, BaseModel):
    """Образовательная программа (направление подготовки)"""

    title = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=False, comment='Код направления, например 09.03.01')
    profile = db.Column(db.String(255), nullable=True)
    qualification = db.Column(db.String(50), nullable=True)
    form_of_education = db.Column(db.String(50), nullable=True)
    enrollment_year = db.Column(db.Integer, nullable=True, comment='Год набора')
    fgos_vo_id = db.Column(db.Integer, db.ForeignKey('competencies_fgos_vo.id'), nullable=True)

    fgos = relationship('FgosVo', back_populates='educational_programs')
    aup_assoc = relationship('EducationalProgramAup', back_populates='educational_program', cascade="all, delete-orphan")
    selected_ps_assoc = relationship('EducationalProgramPs', back_populates='educational_program', cascade="all, delete-orphan")
    competencies_assoc = relationship('CompetencyEducationalProgram', back_populates='educational_program', cascade="all, delete-orphan")

    def __repr__(self):
        return f"<EducationalProgram {self.code} {self.title}>"

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None,
                include_fgos: bool = False, include_aup_list: bool = False, include_selected_ps_list: bool = False,
                include_recommended_ps_list: bool = False, include_competencies_list: bool = False) -> Dict[str, Any]:
        data = super().to_dict(rules=rules, only=only)

        def _should_include(field_name: str, current_rules: Optional[List[str]], current_only: Optional[List[str]]) -> bool:
            if current_rules:
                for rule in current_rules:
                    if rule.startswith('-') and rule[1:] == field_name:
                        return False
            if current_only and field_name not in current_only:
                return False
            return True

        if include_fgos and _should_include('fgos_details', rules, only):
            if self.fgos:
                data['fgos_details'] = self.fgos.to_dict()
            else:
                data['fgos_details'] = None

        if include_aup_list and _should_include('aup_list', rules, only):
            data['aup_list'] = []
            if hasattr(self, 'aup_assoc') and self.aup_assoc:
                for assoc in self.aup_assoc:
                    assoc_data = assoc.to_dict()
                    data['aup_list'].append(assoc_data)

        if include_selected_ps_list and _should_include('selected_ps_list', rules, only):
            data['selected_ps_list'] = []
            if hasattr(self, 'selected_ps_assoc') and self.selected_ps_assoc:
                for assoc in self.selected_ps_assoc:
                    if assoc.prof_standard:
                        data['selected_ps_list'].append(
                            assoc.prof_standard.to_dict(rules=['-generalized_labor_functions', '-fgos_assoc', '-educational_program_assoc'])
                        )

        if include_recommended_ps_list and _should_include('recommended_ps_list', rules, only) and self.fgos:
            recommended_ps_list_data = []
            if self.fgos.recommended_ps_assoc:
                sorted_ps_assoc = sorted(
                    [psa for psa in self.fgos.recommended_ps_assoc if psa.prof_standard],
                    key=lambda ps_assoc_item: ps_assoc_item.prof_standard.code
                )
                for assoc_item in sorted_ps_assoc:
                    recommended_ps_list_data.append({
                        'id': assoc_item.prof_standard.id,
                        'code': assoc_item.prof_standard.code,
                        'name': assoc_item.prof_standard.name,
                        'is_mandatory': assoc_item.is_mandatory,
                        'description': assoc_item.description,
                    })
            data['recommended_ps_list'] = recommended_ps_list_data

        if include_competencies_list and _should_include('competencies_list', rules, only):
            data['competencies_list'] = []
            if hasattr(self, 'competencies_assoc') and self.competencies_assoc:
                for assoc in self.competencies_assoc:
                    if assoc.competency:
                        comp_dict = assoc.competency.to_dict(rules=['-indicators'], include_type=True)
                        data['competencies_list'].append(comp_dict)

        return data

class EducationalProgramAup(db.Model, BaseModel):
    """Связь Образовательной программы и АУП"""

    educational_program_id = db.Column(db.Integer, db.ForeignKey('competencies_educational_program.id', ondelete="CASCADE"), nullable=False)
    aup_id = db.Column(db.Integer, db.ForeignKey('tbl_aup.id_aup', ondelete="CASCADE"), nullable=False)
    is_primary = db.Column(db.Boolean, default=False, comment='Является ли этот АУП основным для программы')

    educational_program = relationship('EducationalProgram', back_populates='aup_assoc')
    aup = relationship('AupInfo', backref=backref('educational_program_links', cascade="all, delete-orphan", passive_deletes=True))

    __table_args__ = (
        db.UniqueConstraint('educational_program_id', 'aup_id', name='uq_educational_program_aup'),
    )

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None,
                include_aup: bool = True) -> Dict[str, Any]:
        data = super().to_dict(rules=rules, only=only)

        def _should_include(field_name: str, current_rules: Optional[List[str]], current_only: Optional[List[str]]) -> bool:
            if current_rules:
                for rule in current_rules:
                    if rule.startswith('-') and rule[1:] == field_name:
                        return False
            if current_only and field_name not in current_only:
                return False
            return True

        if include_aup and _should_include('aup', rules, only):
            if hasattr(self, 'aup') and self.aup:
                if hasattr(self.aup, 'as_dict') and callable(self.aup.as_dict):
                    data['aup'] = self.aup.as_dict() 
                else: 
                    data['aup'] = {
                        'id_aup': self.aup.id_aup,
                        'num_aup': self.aup.num_aup,
                        'file': getattr(self.aup, 'file', None),
                        'year_beg': getattr(self.aup, 'year_beg', None),
                    }
            else:
                data['aup'] = None

        return data

class ProfStandard(db.Model, BaseModel):
    """Профессиональный стандарт"""

    code = db.Column(db.String(50), nullable=False, unique=True, comment='Код профстандарта, например 06.001')
    name = db.Column(db.String(255), nullable=False, comment='Название профстандарта')
    order_number = db.Column(db.String(50), nullable=True, comment='Номер приказа')
    order_date = db.Column(db.Date, nullable=True, comment='Дата приказа')
    registration_number = db.Column(db.String(50), nullable=True, comment='Рег. номер Минюста')
    registration_date = db.Column(db.Date, nullable=True, comment='Дата регистрации в Минюсте')
    # ИСПРАВЛЕНО: Добавлены отсутствующие поля
    activity_area_name = db.Column(db.String(500), nullable=True, comment='Наименование вида профессиональной деятельности')
    activity_purpose = db.Column(db.Text, nullable=True, comment='Основная цель вида профессиональной деятельности')


    generalized_labor_functions = relationship('GeneralizedLaborFunction', back_populates='prof_standard', cascade="all, delete-orphan")
    fgos_assoc = relationship('FgosRecommendedPs', back_populates='prof_standard', cascade="all, delete-orphan")
    educational_program_assoc = relationship('EducationalProgramPs', back_populates='prof_standard', cascade="all, delete-orphan")
    
    def __repr__(self): return f"<ПС {self.code} {self.name[:30]}...>"

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None) -> Dict[str, Any]:
        return super().to_dict(rules=rules, only=only)

class FgosRecommendedPs(db.Model, BaseModel):
    """Связь между ФГОС и рекомендованными в нем профстандартами"""

    fgos_vo_id = db.Column(db.Integer, db.ForeignKey('competencies_fgos_vo.id', ondelete="CASCADE"), nullable=False)
    prof_standard_id = db.Column(db.Integer, db.ForeignKey('competencies_prof_standard.id', ondelete="CASCADE"), nullable=False)
    is_mandatory = db.Column(db.Boolean, default=False, comment='Обязательный ПС или рекомендованный')
    description = db.Column(db.String(255), nullable=True, comment='Примечание к связи')

    fgos = relationship('FgosVo', back_populates='recommended_ps_assoc')
    prof_standard = relationship('ProfStandard', back_populates='fgos_assoc')

    __table_args__ = (db.UniqueConstraint('fgos_vo_id', 'prof_standard_id', name='uq_fgos_ps'),)

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None,
                include_prof_standard: bool = True) -> Dict[str, Any]:
        data = super().to_dict(rules=rules, only=only)
        if include_prof_standard and hasattr(self, 'prof_standard') and self.prof_standard:
             data['prof_standard'] = self.prof_standard.to_dict()
        return data

class EducationalProgramPs(db.Model, BaseModel):
    """Связь между Образовательной программой и выбранными профстандартами"""

    educational_program_id = db.Column(db.Integer, db.ForeignKey('competencies_educational_program.id', ondelete="CASCADE"), nullable=False)
    prof_standard_id = db.Column(db.Integer, db.ForeignKey('competencies_prof_standard.id', ondelete="CASCADE"), nullable=False)
    priority = db.Column(db.Integer, default=0, comment='Приоритет ПС в рамках ОП')

    educational_program = relationship('EducationalProgram', back_populates='selected_ps_assoc')
    prof_standard = relationship('ProfStandard', back_populates='educational_program_assoc')

    __table_args__ = (db.UniqueConstraint('educational_program_id', 'prof_standard_id', name='uq_educational_program_ps'),)

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None,
                include_prof_standard: bool = True) -> Dict[str, Any]:
        data = super().to_dict(rules=rules, only=only)
        if include_prof_standard and hasattr(self, 'prof_standard') and self.prof_standard:
             data['prof_standard'] = self.prof_standard.to_dict()
        return data

class GeneralizedLaborFunction(db.Model, BaseModel):
    """Обобщенная трудовая функция (ОТФ)"""

    prof_standard_id = db.Column(db.Integer, db.ForeignKey('competencies_prof_standard.id', ondelete="CASCADE"), nullable=False)
    prof_standard = relationship('ProfStandard', back_populates='generalized_labor_functions')
    code = db.Column(db.String(10), nullable=False, comment='Код ОТФ, например A')
    name = db.Column(db.String(255), nullable=False, comment='Название ОТФ')
    qualification_level = db.Column(db.String(10), nullable=True, comment='Уровень квалификации')
    
    labor_functions = relationship('LaborFunction', back_populates='generalized_labor_function', cascade="all, delete-orphan")
    
    def __repr__(self): return f"<ОТФ {self.code} {self.name[:30]}...>"

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None) -> Dict[str, Any]:
        return super().to_dict(rules=rules, only=only)

class LaborFunction(db.Model, BaseModel):
    """Трудовая функция (ТФ)"""

    generalized_labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_generalized_labor_function.id', ondelete="CASCADE"), nullable=False)
    generalized_labor_function = relationship('GeneralizedLaborFunction', back_populates='labor_functions')
    code = db.Column(db.String(10), nullable=False, comment='Код ТФ, например A/01.6')
    name = db.Column(db.String(255), nullable=False, comment='Название ТФ')
    qualification_level = db.Column(db.String(10), nullable=True, comment='Уровень квалификации')

    labor_actions = relationship('LaborAction', back_populates='labor_function', cascade="all, delete-orphan")
    required_skills = relationship('RequiredSkill', back_populates='labor_function', cascade="all, delete-orphan")
    required_knowledge = relationship('RequiredKnowledge', back_populates='labor_function', cascade="all, delete-orphan")
    
    indicators = relationship('Indicator', secondary='competencies_indicator_ps_link', back_populates='labor_functions')
    competencies = relationship('Competency', back_populates='based_on_labor_function', primaryjoin="LaborFunction.id==Competency.based_on_labor_function_id")
    
    def __repr__(self): return f"<ТФ {self.code} {self.name[:30]}...>"

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None) -> Dict[str, Any]:
        return super().to_dict(rules=rules, only=only)

class LaborAction(db.Model, BaseModel):
    """Трудовое действие"""

    labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_labor_function.id', ondelete="CASCADE"), nullable=False)
    labor_function = relationship('LaborFunction', back_populates='labor_actions')
    description = db.Column(db.Text, nullable=False, comment='Описание трудового действия')
    order = db.Column(db.Integer, default=0, comment='Порядок в списке')
    
    def __repr__(self): return f"<ТД {self.description[:50]}...>"

class RequiredSkill(db.Model, BaseModel):
    """Необходимое умение"""

    labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_labor_function.id', ondelete="CASCADE"), nullable=False)
    labor_function = relationship('LaborFunction', back_populates='required_skills')
    description = db.Column(db.Text, nullable=False, comment='Описание необходимого умения')
    order = db.Column(db.Integer, default=0, comment='Порядок в списке')

    def __repr__(self): return f"<Умение {self.description[:50]}...>"

class RequiredKnowledge(db.Model, BaseModel):
    """Необходимое знание"""

    labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_labor_function.id', ondelete="CASCADE"), nullable=False)
    labor_function = relationship('LaborFunction', back_populates='required_knowledge')
    description = db.Column(db.Text, nullable=False, comment='Описание необходимого знания')
    order = db.Column(db.Integer, default=0, comment='Порядок в списке')

    def __repr__(self): return f"<Знание {self.description[:50]}...>"

class CompetencyType(db.Model, BaseModel):
    """Тип компетенции (УК, ОПК, ПК)"""

    name = db.Column(db.String(100), nullable=False, comment='Название типа компетенции')
    code = db.Column(db.String(10), nullable=False, unique=True, comment='Код типа (УК, ОПК, ПК)')
    description = db.Column(db.Text, nullable=True, comment='Описание типа компетенции')
    competencies = relationship('Competency', back_populates='competency_type')
    
    def __repr__(self): return f"<Тип {self.code} {self.name}>"

class Competency(db.Model, BaseModel):
    """Компетенция (УК, ОПК, ПК)"""

    competency_type_id = db.Column(db.Integer, db.ForeignKey('competencies_competency_type.id'), nullable=False)
    competency_type = relationship('CompetencyType', back_populates='competencies')

    fgos_vo_id = db.Column(db.Integer, db.ForeignKey('competencies_fgos_vo.id'), nullable=True)
    fgos = relationship('FgosVo', back_populates='competencies') 

    based_on_labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_labor_function.id'), nullable=True)
    based_on_labor_function = relationship('LaborFunction', back_populates='competencies', primaryjoin="LaborFunction.id==Competency.based_on_labor_function_id")

    code = db.Column(db.String(20), nullable=False, comment='Код компетенции (УК-1, ОПК-2, ПК-3...)')
    name = db.Column(db.Text, nullable=False, comment='Формулировка компетенции')
    description = db.Column(db.Text, nullable=True, comment='Дополнительное описание компетенции')
    category_name = db.Column(db.String(255), nullable=True, comment='Название категории компетенции')

    indicators = relationship('Indicator', back_populates='competency', cascade="all, delete-orphan")
    educational_programs_assoc = relationship('CompetencyEducationalProgram', back_populates='competency', cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint('code', 'fgos_vo_id', 'competency_type_id', name='uq_competency_code_fgos_type'),
    )

    def __repr__(self): return f"<{self.code} {self.name[:30]}...>"

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None,
                include_indicators: bool = False, include_type: bool = False,
                include_educational_programs: bool = False) -> Dict[str, Any]:
        data = super().to_dict(rules=rules, only=only)
        if include_indicators and hasattr(self, 'indicators') and self.indicators is not None:
             data['indicators'] = [ind.to_dict() for ind in self.indicators]
        if include_type and hasattr(self, 'competency_type') and self.competency_type is not None:
             data['type_code'] = self.competency_type.code
        
        if include_educational_programs and hasattr(self, 'educational_programs_assoc') and self.educational_programs_assoc is not None:
             data['educational_programs'] = [
                 assoc.educational_program.to_dict(rules=['-aup_assoc', '-selected_ps_assoc', '-recommended_ps_list', '-competencies_assoc'])
                 for assoc in self.educational_programs_assoc if assoc.educational_program
             ]

        return data

class CompetencyEducationalProgram(db.Model, BaseModel): 
    """Связь между Компетенцией и Образовательной программой"""

    competency_id = db.Column(db.Integer, db.ForeignKey('competencies_competency.id', ondelete="CASCADE"), nullable=False)
    educational_program_id = db.Column(db.Integer, db.ForeignKey('competencies_educational_program.id', ondelete="CASCADE"), nullable=False)
    
    competency = relationship('Competency', back_populates='educational_programs_assoc')
    educational_program = relationship('EducationalProgram', back_populates='competencies_assoc')

    __table_args__ = (
        db.UniqueConstraint('competency_id', 'educational_program_id', name='uq_comp_ep'),
    )

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None) -> Dict[str, Any]:
        return super().to_dict(rules=rules, only=only)


class Indicator(db.Model, BaseModel):
    """Индикатор достижения компетенции (ИДК)"""

    competency_id = db.Column(db.Integer, db.ForeignKey('competencies_competency.id', ondelete="CASCADE"), nullable=False)
    competency = relationship('Competency', back_populates='indicators')

    code = db.Column(db.String(20), nullable=False, comment='Код индикатора (ИУК-1.1, ИОПК-2.3, ИПК-3.2...)')
    formulation = db.Column(db.Text, nullable=False, comment='Формулировка индикатора')
    source = db.Column(db.String(255), nullable=True, comment='Источник (ФГОС, ПООП, ВУЗ, ПС...)')
    # НОВОЕ ПОЛЕ: Для хранения ID выбранных элементов ЗУН из ПС
    # Ключи: 'labor_actions', 'required_skills', 'required_knowledge'
    # Значения: список ID соответствующих элементов.
    selected_ps_elements_ids = db.Column(db.JSON, nullable=True, default={
        'labor_actions': [],
        'required_skills': [],
        'required_knowledge': []
    }, comment='JSON массив ID выбранных элементов ПС (ТД, НУ, НЗ), на основе которых сформирован индикатор')


    labor_functions = relationship('LaborFunction', secondary='competencies_indicator_ps_link', back_populates='indicators')
    matrix_entries = relationship('CompetencyMatrix', back_populates='indicator', cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint('code', 'competency_id', name='uq_indicator_code_competency'),
    )

    def __repr__(self): return f"<{self.code} {self.formulation[:30]}...>"

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None,
                include_competency: bool = False) -> Dict[str, Any]:
        data = super().to_dict(rules=rules, only=only)
        if include_competency and hasattr(self, 'competency') and self.competency is not None:
             data['competency_code'] = self.competency.code
             data['competency_name'] = self.competency.name
        return data

class IndicatorPsLink(db.Model, BaseModel):
    """Связь между индикатором компетенции и трудовой функцией"""

    indicator_id = db.Column(db.Integer, db.ForeignKey('competencies_indicator.id', ondelete="CASCADE"), nullable=False)
    labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_labor_function.id', ondelete="CASCADE"), nullable=False)
    relevance_score = db.Column(db.Float, nullable=True, comment='Оценка релевантности (от 0 до 1)')
    is_manual = db.Column(db.Boolean, default=False, comment='Связь установлена вручную')

    __table_args__ = (
        db.UniqueConstraint('indicator_id', 'labor_function_id', name='uq_indicator_tf'),
    )

class CompetencyMatrix(db.Model, BaseModel):
    """Матрица компетенций - связь между дисциплиной (AupData) и индикатором компетенции"""

    # --- ДОБАВЛЕНО ЯВНОЕ ИМЯ ТАБЛИЦЫ ---
    __tablename__ = 'competencies_matrix'
    # -------------------------------------

    aup_data_id = db.Column(db.Integer, db.ForeignKey('aup_data.id', ondelete="CASCADE"), nullable=False)
    indicator_id = db.Column(db.Integer, db.ForeignKey('competencies_indicator.id', ondelete="CASCADE"), nullable=False)
    relevance_score = db.Column(db.Float, nullable=True, comment='Оценка релевантности (от 0 до 1)')
    is_manual = db.Column(db.Boolean, default=False, comment='Связь установлена вручную')
    
    created_by = db.Column(db.Integer, db.ForeignKey('tbl_users.id_user'), nullable=True, comment='ID пользователя, создавшего связь') 
    if USERS_MODEL_AVAILABLE:
        creator = relationship('Users', foreign_keys=[created_by]) 

    indicator = relationship('Indicator', back_populates='matrix_entries')
    aup_data_entry = relationship('AupData', back_populates='matrix_entries')

    __table_args__ = (
        db.UniqueConstraint('aup_data_id', 'indicator_id', name='uq_matrix_aup_indicator'),
    )

    def __repr__(self):
        return f"<Связь AupData({self.aup_data_id})<->Indicator({self.indicator_id})>"

    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None) -> Dict[str, Any]:
        return super().to_dict(rules=rules, only=only)

from maps.models import AupData
@db.event.listens_for(AupData, 'mapper_configured', once=True)
def add_aupdata_relationships(mapper, class_):
    if not hasattr(class_, 'matrix_entries'):
        class_.matrix_entries = relationship(
            'CompetencyMatrix',
            back_populates='aup_data_entry',
            cascade="all, delete-orphan",
            lazy='dynamic' # Используем lazy='dynamic' для эффективных запросов
        )
    if hasattr(class_, 'indicators'):
        delattr(class_, 'indicators')