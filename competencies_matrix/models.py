# competencies_matrix/models.py
# При изменении моделей в этом файле, не забудьте обновить Alembic миграции
from maps.models import db, AupInfo, AupData, SprDiscipline
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relationship, backref
from sqlalchemy import inspect
from typing import List, Dict, Any, Optional, Set, Union
import datetime

# Note: The create_tables_if_needed() and initialize_lookup_data() functions
# have been removed as they are not needed with Alembic migrations

# Базовый класс для всех моделей
class BaseModel:
    """Базовый класс для моделей с общей функциональностью"""
    
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), 
                           onupdate=db.func.current_timestamp())
    
    def to_dict(self, rules: Optional[List[str]] = None, only: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Сериализует модель в словарь.
        
        Args:
            rules: Правила сериализации (напр. ['-password', '-tokens'])
            only: Если указано, возвращает только перечисленные поля
            
        Returns:
            Словарь с данными модели
        """
        result = {}
        
        # Обрабатываем список исключений
        exclude_columns = set()
        if rules:
            for rule in rules:
                if rule.startswith('-'):
                    exclude_columns.add(rule[1:])
        
        # Получаем атрибуты модели
        for c in inspect(self).mapper.column_attrs:
            if only and c.key not in only:
                continue
            if c.key in exclude_columns:
                continue
            result[c.key] = getattr(self, c.key)
            
        return result


# === Модели для образовательных программ и фгос ===

class FgosVo(db.Model, BaseModel):
    """ФГОС ВО (Федеральный государственный образовательный стандарт высшего образования)"""
    __tablename__ = 'competencies_fgos_vo'
    
    # Основные поля
    number = db.Column(db.String(50), nullable=False, comment='Номер приказа')
    date = db.Column(db.Date, nullable=False, comment='Дата утверждения')
    direction_code = db.Column(db.String(10), nullable=False, comment='Код направления, например 09.03.01')
    direction_name = db.Column(db.String(255), nullable=False, comment='Название направления')
    education_level = db.Column(db.String(50), nullable=False, comment='Уровень образования (бакалавриат/магистратура/аспирантура)')
    generation = db.Column(db.String(10), nullable=False, comment='Поколение ФГОС (3+, 3++)')
    
    # PDF файл ФГОС (опционально)
    file_path = db.Column(db.String(255), nullable=True, comment='Путь к PDF файлу')
    
    # Связи
    educational_programs = relationship('EducationalProgram', back_populates='fgos')
    recommended_ps_assoc = relationship('FgosRecommendedPs', back_populates='fgos')

    def __repr__(self):
        return f"<ФГОС {self.direction_code} ({self.generation})>"


class EducationalProgram(db.Model, BaseModel):
    """Образовательная программа (направление подготовки)"""
    __tablename__ = 'competencies_educational_program'
    
    title = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=False, comment='Код направления, например 09.03.01')
    profile = db.Column(db.String(255), nullable=True)
    qualification = db.Column(db.String(50), nullable=True)
    form_of_education = db.Column(db.String(50), nullable=True)
    enrollment_year = db.Column(db.Integer, nullable=True, comment='Год набора')
    fgos_vo_id = db.Column(db.Integer, db.ForeignKey('competencies_fgos_vo.id'), nullable=True)
    
    # Relationships
    fgos = relationship('FgosVo', back_populates='educational_programs')
    aup_assoc = relationship('EducationalProgramAup', back_populates='educational_program')
    selected_ps_assoc = relationship('EducationalProgramPs', back_populates='educational_program')
    
    def __repr__(self):
        return f"<EducationalProgram {self.code} {self.title}>"


class EducationalProgramAup(db.Model, BaseModel):
    """Связь Образовательной программы и АУП"""
    __tablename__ = 'competencies_educational_program_aup'
    
    educational_program_id = db.Column(db.Integer, db.ForeignKey('competencies_educational_program.id'), nullable=False)
    aup_id = db.Column(db.Integer, db.ForeignKey('tbl_aup.id_aup'), nullable=False)
    # Дополнительные мета-данные о связи (приоритет, основной АУП и т.д.)
    is_primary = db.Column(db.Boolean, default=False, comment='Является ли этот АУП основным для программы')
    
    # Определяем отношения
    educational_program = relationship('EducationalProgram', back_populates='aup_assoc')
    aup = relationship('AupInfo', backref='education_programs_assoc')  # Предполагаем, что AupInfo импортирована
    
    __table_args__ = (
        db.UniqueConstraint('educational_program_id', 'aup_id', name='uq_educational_program_aup'),
    )


# === Модели для профстандартов ===

class ProfStandard(db.Model, BaseModel):
    """Профессиональный стандарт"""
    __tablename__ = 'competencies_prof_standard'
    
    # Основные поля
    code = db.Column(db.String(50), nullable=False, comment='Код профстандарта, например 06.001')
    name = db.Column(db.String(255), nullable=False, comment='Название профстандарта')
    order_number = db.Column(db.String(50), nullable=True, comment='Номер приказа')
    order_date = db.Column(db.Date, nullable=True, comment='Дата приказа')
    registration_number = db.Column(db.String(50), nullable=True, comment='Рег. номер Минюста')
    registration_date = db.Column(db.Date, nullable=True, comment='Дата регистрации в Минюсте')
    
    # Хранение разобранного содержимого
    parsed_content = db.Column(db.Text, nullable=True, comment='Содержимое стандарта в Markdown')
    
    # Связи
    generalized_labor_functions = relationship('GeneralizedLaborFunction', back_populates='prof_standard')
    fgos_assoc = relationship('FgosRecommendedPs', back_populates='prof_standard')
    educational_program_assoc = relationship('EducationalProgramPs', back_populates='prof_standard')
    
    def __repr__(self):
        return f"<ПС {self.code} {self.name[:30]}...>"


class FgosRecommendedPs(db.Model, BaseModel):
    """Связь между ФГОС и рекомендованными в нем профстандартами"""
    __tablename__ = 'competencies_fgos_recommended_ps'
    
    fgos_vo_id = db.Column(db.Integer, db.ForeignKey('competencies_fgos_vo.id'), nullable=False)
    prof_standard_id = db.Column(db.Integer, db.ForeignKey('competencies_prof_standard.id'), nullable=False)
    
    # Флаг, указывающий что это за ПС - обязательный или рекомендованный
    is_mandatory = db.Column(db.Boolean, default=False, comment='Обязательный ПС или рекомендованный')
    
    # Дополнительные мета-данные
    description = db.Column(db.String(255), nullable=True, comment='Примечание к связи')
    
    # Определяем отношения
    fgos = relationship('FgosVo', back_populates='recommended_ps_assoc')
    prof_standard = relationship('ProfStandard', back_populates='fgos_assoc')
    
    __table_args__ = (
        db.UniqueConstraint('fgos_vo_id', 'prof_standard_id', name='uq_fgos_ps'),
    )


class EducationalProgramPs(db.Model, BaseModel):
    """Связь между Образовательной программой и выбранными профстандартами"""
    __tablename__ = 'competencies_educational_program_ps'
    
    educational_program_id = db.Column(db.Integer, db.ForeignKey('competencies_educational_program.id'), nullable=False)
    prof_standard_id = db.Column(db.Integer, db.ForeignKey('competencies_prof_standard.id'), nullable=False)
    
    # Дополнительные мета-данные
    priority = db.Column(db.Integer, default=0, comment='Приоритет ПС в рамках ОП')
    
    # Определяем отношения
    educational_program = relationship('EducationalProgram', back_populates='selected_ps_assoc')
    prof_standard = relationship('ProfStandard', back_populates='educational_program_assoc')
    
    __table_args__ = (
        db.UniqueConstraint('educational_program_id', 'prof_standard_id', name='uq_educational_program_ps'),
    )


class GeneralizedLaborFunction(db.Model, BaseModel):
    """Обобщенная трудовая функция (ОТФ)"""
    __tablename__ = 'competencies_generalized_labor_function'
    
    # Связь с ПС
    prof_standard_id = db.Column(db.Integer, db.ForeignKey('competencies_prof_standard.id'), nullable=False)
    prof_standard = relationship('ProfStandard', back_populates='generalized_labor_functions')
    
    # Основные поля
    code = db.Column(db.String(10), nullable=False, comment='Код ОТФ, например A')
    name = db.Column(db.String(255), nullable=False, comment='Название ОТФ')
    qualification_level = db.Column(db.String(10), nullable=True, comment='Уровень квалификации')
    
    # Связь с ТФ
    labor_functions = relationship('LaborFunction', back_populates='generalized_labor_function')
    
    def __repr__(self):
        return f"<ОТФ {self.code} {self.name[:30]}...>"


class LaborFunction(db.Model, BaseModel):
    """Трудовая функция (ТФ)"""
    __tablename__ = 'competencies_labor_function'
    
    # Связь с ОТФ
    generalized_labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_generalized_labor_function.id'), nullable=False)
    generalized_labor_function = relationship('GeneralizedLaborFunction', back_populates='labor_functions')
    
    # Основные поля
    code = db.Column(db.String(10), nullable=False, comment='Код ТФ, например A/01.6')
    name = db.Column(db.String(255), nullable=False, comment='Название ТФ')
    qualification_level = db.Column(db.String(10), nullable=True, comment='Уровень квалификации')
    
    # Связи с другими сущностями
    labor_actions = relationship('LaborAction', back_populates='labor_function')
    required_skills = relationship('RequiredSkill', back_populates='labor_function')
    required_knowledge = relationship('RequiredKnowledge', back_populates='labor_function')
    
    # Индикаторы, связанные с этой ТФ (например, для оценки соответствия)
    indicators = relationship('Indicator', secondary='competencies_indicator_ps_link', back_populates='labor_functions')
    
    # Компетенции, созданные на основе этой ТФ
    competencies = relationship('Competency', back_populates='based_on_labor_function', primaryjoin="LaborFunction.id==Competency.based_on_labor_function_id")
    
    def __repr__(self):
        return f"<ТФ {self.code} {self.name[:30]}...>"


class LaborAction(db.Model, BaseModel):
    """Трудовое действие"""
    __tablename__ = 'competencies_labor_action'
    
    # Связь с ТФ
    labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_labor_function.id'), nullable=False)
    labor_function = relationship('LaborFunction', back_populates='labor_actions')
    
    # Основные поля
    description = db.Column(db.Text, nullable=False, comment='Описание трудового действия')
    order = db.Column(db.Integer, default=0, comment='Порядок в списке')
    
    def __repr__(self):
        return f"<ТД {self.description[:50]}...>"


class RequiredSkill(db.Model, BaseModel):
    """Необходимое умение"""
    __tablename__ = 'competencies_required_skill'
    
    # Связь с ТФ
    labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_labor_function.id'), nullable=False)
    labor_function = relationship('LaborFunction', back_populates='required_skills')
    
    # Основные поля
    description = db.Column(db.Text, nullable=False, comment='Описание необходимого умения')
    order = db.Column(db.Integer, default=0, comment='Порядок в списке')
    
    def __repr__(self):
        return f"<Умение {self.description[:50]}...>"


class RequiredKnowledge(db.Model, BaseModel):
    """Необходимое знание"""
    __tablename__ = 'competencies_required_knowledge'
    
    # Связь с ТФ
    labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_labor_function.id'), nullable=False)
    labor_function = relationship('LaborFunction', back_populates='required_knowledge')
    
    # Основные поля
    description = db.Column(db.Text, nullable=False, comment='Описание необходимого знания')
    order = db.Column(db.Integer, default=0, comment='Порядок в списке')
    
    def __repr__(self):
        return f"<Знание {self.description[:50]}...>"


# === Модели для компетенций и индикаторов ===

class CompetencyType(db.Model, BaseModel):
    """Тип компетенции (УК, ОПК, ПК)"""
    __tablename__ = 'competencies_competency_type'
    
    name = db.Column(db.String(100), nullable=False, comment='Название типа компетенции')
    code = db.Column(db.String(10), nullable=False, unique=True, comment='Код типа (УК, ОПК, ПК)')
    description = db.Column(db.Text, nullable=True, comment='Описание типа компетенции')
    
    # Связь
    competencies = relationship('Competency', back_populates='competency_type')
    
    def __repr__(self):
        return f"<Тип {self.code} {self.name}>"


class Competency(db.Model, BaseModel):
    """Компетенция (УК, ОПК, ПК)"""
    __tablename__ = 'competencies_competency'
    
    # Тип компетенции (УК, ОПК, ПК)
    competency_type_id = db.Column(db.Integer, db.ForeignKey('competencies_competency_type.id'), nullable=False)
    competency_type = relationship('CompetencyType', back_populates='competencies')
    
    # Связь с ФГОС (для УК, ОПК)
    fgos_vo_id = db.Column(db.Integer, db.ForeignKey('competencies_fgos_vo.id'), nullable=True)
    fgos = relationship('FgosVo', backref='competencies')
    
    # Связь с ТФ (для ПК)
    based_on_labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_labor_function.id'), nullable=True)
    based_on_labor_function = relationship('LaborFunction', back_populates='competencies', foreign_keys=[based_on_labor_function_id])
    
    # Основные поля
    code = db.Column(db.String(20), nullable=False, comment='Код компетенции (УК-1, ОПК-2, ПК-3...)')
    name = db.Column(db.Text, nullable=False, comment='Формулировка компетенции')
    description = db.Column(db.Text, nullable=True, comment='Дополнительное описание компетенции')
    
    # Индикаторы компетенции
    indicators = relationship('Indicator', back_populates='competency')
    
    __table_args__ = (
        db.UniqueConstraint('code', 'fgos_vo_id', name='uq_competency_code_fgos'),
    )
    
    def __repr__(self):
        return f"<{self.code} {self.name[:30]}...>"


class Indicator(db.Model, BaseModel):
    """Индикатор достижения компетенции (ИДК)"""
    __tablename__ = 'competencies_indicator'
    
    # Связь с компетенцией
    competency_id = db.Column(db.Integer, db.ForeignKey('competencies_competency.id'), nullable=False)
    competency = relationship('Competency', back_populates='indicators')
    
    # Основные поля
    code = db.Column(db.String(20), nullable=False, comment='Код индикатора (ИУК-1.1, ИОПК-2.3, ИПК-3.2...)')
    formulation = db.Column(db.Text, nullable=False, comment='Формулировка индикатора')
    source = db.Column(db.String(255), nullable=True, comment='Источник (ФГОС, ПООП, ВУЗ, ПС...)')
    
    # Связь с ТФ в профстандартах (многие-ко-многим)
    labor_functions = relationship('LaborFunction', secondary='competencies_indicator_ps_link', back_populates='indicators')
    
    # Связь с матрицей компетенций - ИСПРАВЛЕНО: убираем прямую связь с AupData
    matrix_entries = relationship('CompetencyMatrix', back_populates='indicator', cascade="all, delete-orphan")
    
    __table_args__ = (
        db.UniqueConstraint('code', 'competency_id', name='uq_indicator_code_competency'),
    )
    
    def __repr__(self):
        return f"<{self.code} {self.formulation[:30]}...>"


class IndicatorPsLink(db.Model, BaseModel):
    """Связь между индикатором компетенции и трудовой функцией"""
    __tablename__ = 'competencies_indicator_ps_link'
    
    indicator_id = db.Column(db.Integer, db.ForeignKey('competencies_indicator.id'), nullable=False)
    labor_function_id = db.Column(db.Integer, db.ForeignKey('competencies_labor_function.id'), nullable=False)
    
    # Мета-данные связи
    relevance_score = db.Column(db.Float, nullable=True, comment='Оценка релевантности (от 0 до 1)')
    is_manual = db.Column(db.Boolean, default=False, comment='Связь установлена вручную')
    
    __table_args__ = (
        db.UniqueConstraint('indicator_id', 'labor_function_id', name='uq_indicator_tf'),
    )


class CompetencyMatrix(db.Model, BaseModel):
    """Матрица компетенций - связь между дисциплиной (AupData) и индикатором компетенции"""
    __tablename__ = 'competencies_matrix'
    
    aup_data_id = db.Column(db.Integer, db.ForeignKey('aup_data.id'), nullable=False)
    indicator_id = db.Column(db.Integer, db.ForeignKey('competencies_indicator.id'), nullable=False)
    
    # Мета-данные связи
    relevance_score = db.Column(db.Float, nullable=True, comment='Оценка релевантности (от 0 до 1)')
    is_manual = db.Column(db.Boolean, default=False, comment='Связь установлена вручную')
    created_by = db.Column(db.Integer, nullable=True, comment='ID пользователя, создавшего связь')
    
    # Отношения
    indicator = relationship('Indicator', back_populates='matrix_entries')
    aup_data_entry = relationship('AupData', back_populates='matrix_entries')
    
    __table_args__ = (
        db.UniqueConstraint('aup_data_id', 'indicator_id', name='uq_matrix_aup_indicator'),
    )
    
    def __repr__(self):
        return f"<Связь AupData({self.aup_data_id})<->Indicator({self.indicator_id})>"

# Определяем отношения для моделей AupData из maps.models
# Добавляем атрибут matrix_entries в модель AupData
from maps.models import AupData

# Используем event listener для добавления relationship к существующей модели AupData
@db.event.listens_for(AupData, 'mapper_configured', once=True)
def add_aupdata_relationships(mapper, class_):
    if not hasattr(class_, 'matrix_entries'):
        class_.matrix_entries = relationship(
            'CompetencyMatrix', 
            back_populates='aup_data_entry',
            cascade="all, delete-orphan",
            lazy='dynamic'
        )
        print(f"Dynamically added 'matrix_entries' relationship to AupData")
    
    # Remove the old indicators relationship if it exists
    if hasattr(class_, 'indicators'):
        delattr(class_, 'indicators')
        print(f"Removed 'indicators' relationship from AupData")