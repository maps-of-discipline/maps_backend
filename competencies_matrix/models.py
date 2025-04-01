# competencies_matrix/models.py
from maps.models import db # Импортируем db из основного модуля карт
from sqlalchemy_serializer import SerializerMixin
import datetime

# --- Модели для Образовательных Программ и Стандартов ---
class FgosVo(db.Model, SerializerMixin):
    __tablename__ = 'fgos_vo'
    # ... поля таблицы fgos_vo ...
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.Text, nullable=False)
    level = db.Column(db.Enum('бакалавриат', 'специалитет', 'магистратура'), nullable=False)
    approval_order_number = db.Column(db.String(100))
    approval_order_date = db.Column(db.Date)
    # ... другие поля и связи (например, с EducationalPrograms)
    educational_programs = db.relationship('EducationalProgram', back_populates='fgos')
    recommended_ps_assoc = db.relationship('FgosRecommendedPs', back_populates='fgos')

class EducationalProgram(db.Model, SerializerMixin):
    __tablename__ = 'educational_programs'
    serialize_rules = ('-fgos.educational_programs', '-selected_ps_assoc.educational_program', '-aup_assoc.educational_program') # Предотвращение циклов
    # ... поля таблицы educational_programs ...
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(500), nullable=False)
    fgos_vo_id = db.Column(db.Integer, db.ForeignKey('fgos_vo.id'), nullable=False)
    enrollment_year = db.Column(db.Integer)
    # ... другие поля ...
    fgos = db.relationship('FgosVo', back_populates='educational_programs')
    selected_ps_assoc = db.relationship('EducationalProgramPs', back_populates='educational_program')
    aup_assoc = db.relationship('EducationalProgramAup', back_populates='educational_program')

class ProfStandard(db.Model, SerializerMixin):
    __tablename__ = 'prof_standards'
    # ... поля таблицы prof_standards ...
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.Text, nullable=False)
    # ... остальные поля ПС ...
    parsed_content = db.Column(db.Text) # Для хранения Markdown
    generalized_labor_functions = db.relationship('GeneralizedLaborFunction', back_populates='prof_standard')
    # Связи для M:N
    recommended_for_fgos_assoc = db.relationship('FgosRecommendedPs', back_populates='prof_standard')
    selected_for_ep_assoc = db.relationship('EducationalProgramPs', back_populates='prof_standard')


# --- Ассоциативные таблицы ---
class FgosRecommendedPs(db.Model):
    __tablename__ = 'fgos_recommended_ps'
    fgos_vo_id = db.Column(db.Integer, db.ForeignKey('fgos_vo.id'), primary_key=True)
    prof_standard_id = db.Column(db.Integer, db.ForeignKey('prof_standards.id'), primary_key=True)
    fgos = db.relationship('FgosVo', back_populates='recommended_ps_assoc')
    prof_standard = db.relationship('ProfStandard', back_populates='recommended_for_fgos_assoc')

class EducationalProgramPs(db.Model):
    __tablename__ = 'educational_program_ps'
    serialize_rules=('-educational_program', '-prof_standard.selected_for_ep_assoc') # Предотвращение циклов
    educational_program_id = db.Column(db.Integer, db.ForeignKey('educational_programs.id'), primary_key=True)
    prof_standard_id = db.Column(db.Integer, db.ForeignKey('prof_standards.id'), primary_key=True)
    educational_program = db.relationship('EducationalProgram', back_populates='selected_ps_assoc')
    prof_standard = db.relationship('ProfStandard', back_populates='selected_for_ep_assoc')


# --- Модели для Компетенций и Индикаторов ---
class CompetencyType(db.Model, SerializerMixin):
    __tablename__ = 'competency_types'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)

class Competency(db.Model, SerializerMixin):
    __tablename__ = 'competencies'
    serialize_rules = ('-competency_type', '-indicators.competency') # Предотвращение циклов
    id = db.Column(db.Integer, primary_key=True)
    competency_type_id = db.Column(db.Integer, db.ForeignKey('competency_types.id'), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.Text, nullable=False)
    # ... based_on_labor_function_id и другие поля ...
    competency_type = db.relationship('CompetencyType')
    indicators = db.relationship('Indicator', back_populates='competency', cascade="all, delete-orphan")
    # Связь с матрицей (если нужно быстро найти все связи компетенции)
    matrix_links = db.relationship('CompetencyMatrix', secondary='indicators', back_populates='competency', viewonly=True)

class Indicator(db.Model, SerializerMixin):
    __tablename__ = 'indicators'
    serialize_rules = ('-competency.indicators', '-matrix_links.indicator') # Предотвращение циклов
    id = db.Column(db.Integer, primary_key=True)
    competency_id = db.Column(db.Integer, db.ForeignKey('competencies.id'), nullable=False)
    code = db.Column(db.String(30), nullable=False)
    formulation = db.Column(db.Text, nullable=False)
    source_description = db.Column(db.String(500))
    # ... другие поля ...
    competency = db.relationship('Competency', back_populates='indicators')
    # Связь с матрицей
    matrix_links = db.relationship('CompetencyMatrix', back_populates='indicator', cascade="all, delete-orphan")
    # Связь с элементами ПС (если нужна навигация от ИДК)
    ps_links = db.relationship('IndicatorPsLink', back_populates='indicator', cascade="all, delete-orphan")


# --- Модели для Матрицы ---
# Важно: Используем модели AupData и SprDiscipline из maps.models
# Если их там нет, их нужно либо перенести в общее место, либо импортировать/определить здесь

# Ассоциативная таблица для связи ОП и АУП
class EducationalProgramAup(db.Model):
    __tablename__ = 'educational_program_aup'
    educational_program_id = db.Column(db.Integer, db.ForeignKey('educational_programs.id'), primary_key=True)
    aup_id = db.Column(db.Integer, db.ForeignKey('tbl_aup.id_aup'), primary_key=True) # Используем имя таблицы из maps.models
    educational_program = db.relationship('EducationalProgram', back_populates='aup_assoc')
    aup = db.relationship('AupInfo') # Используем имя класса из maps.models

class CompetencyMatrix(db.Model, SerializerMixin):
    __tablename__ = 'competency_matrix'
    # Убрали serialize_rules, т.к. связи в Indicator/Competency уже их имеют
    id = db.Column(db.Integer, primary_key=True)
    # Связь НЕ с rpd_id, а с конкретной строкой в структуре АУП (aup_data)
    aup_data_id = db.Column(db.Integer, db.ForeignKey('aup_data.id'), nullable=False) # Используем имя таблицы из maps.models
    indicator_id = db.Column(db.Integer, db.ForeignKey('indicators.id'), nullable=False)
    # --- Опциональные поля ---
    # match_type = db.Column(db.Enum('manual', 'auto', 'mixed'), default='manual')
    # match_level = db.Column(db.Enum('high', 'medium', 'low'))
    # confidence_score = db.Column(db.Float) # Уверенность NLP

    # Связи для удобства навигации
    aup_data_entry = db.relationship('AupData') # Имя класса из maps.models
    indicator = db.relationship('Indicator', back_populates='matrix_links')
    # Косвенная связь с компетенцией через индикатор
    competency = db.relationship('Competency', secondary='indicators', back_populates='matrix_links', viewonly=True)

# --- Модели для структуры ПС (пример) ---
class GeneralizedLaborFunction(db.Model, SerializerMixin):
     __tablename__ = 'generalized_labor_functions'
     id = db.Column(db.Integer, primary_key=True)
     prof_standard_id = db.Column(db.Integer, db.ForeignKey('prof_standards.id'), nullable=False)
     code = db.Column(db.String(20))
     name = db.Column(db.Text, nullable=False)
     qualification_level = db.Column(db.Integer)
     prof_standard = db.relationship('ProfStandard', back_populates='generalized_labor_functions')
     labor_functions = db.relationship('LaborFunction', back_populates='generalized_labor_function')

class LaborFunction(db.Model, SerializerMixin):
     __tablename__ = 'labor_functions'
     id = db.Column(db.Integer, primary_key=True)
     generalized_labor_function_id = db.Column(db.Integer, db.ForeignKey('generalized_labor_functions.id'), nullable=False)
     code = db.Column(db.String(20))
     name = db.Column(db.Text, nullable=False)
     generalized_labor_function = db.relationship('GeneralizedLaborFunction', back_populates='labor_functions')
     # Связи с действиями, знаниями, умениями
     labor_actions = db.relationship('LaborAction', back_populates='labor_function')
     required_skills = db.relationship('RequiredSkill', back_populates='labor_function')
     required_knowledge = db.relationship('RequiredKnowledge', back_populates='labor_function')
     # Связь с компетенциями ПК (если нужно)
     based_competencies = db.relationship('Competency', backref='based_on_labor_function', foreign_keys='Competency.based_on_labor_function_id')


class LaborAction(db.Model, SerializerMixin):
    __tablename__ = 'labor_actions'
    id = db.Column(db.Integer, primary_key=True)
    labor_function_id = db.Column(db.Integer, db.ForeignKey('labor_functions.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    labor_function = db.relationship('LaborFunction', back_populates='labor_actions')


class RequiredSkill(db.Model, SerializerMixin):
    __tablename__ = 'required_skills'
    id = db.Column(db.Integer, primary_key=True)
    labor_function_id = db.Column(db.Integer, db.ForeignKey('labor_functions.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    labor_function = db.relationship('LaborFunction', back_populates='required_skills')


class RequiredKnowledge(db.Model, SerializerMixin):
    __tablename__ = 'required_knowledge'
    id = db.Column(db.Integer, primary_key=True)
    labor_function_id = db.Column(db.Integer, db.ForeignKey('labor_functions.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    labor_function = db.relationship('LaborFunction', back_populates='required_knowledge')

# --- Связь ИДК с элементами ПС ---
class IndicatorPsLink(db.Model, SerializerMixin):
    __tablename__ = 'indicator_ps_link'
    id = db.Column(db.Integer, primary_key=True)
    indicator_id = db.Column(db.Integer, db.ForeignKey('indicators.id'), nullable=False)
    link_type = db.Column(db.Enum('labor_action', 'skill', 'knowledge'), nullable=False)
    element_id = db.Column(db.Integer, nullable=False) # ID из соответствующей таблицы (labor_actions, required_skills, required_knowledge)
    indicator = db.relationship('Indicator', back_populates='ps_links')
    # Можно добавить property для получения связанного объекта (но сложнее из-за разных таблиц)

# ... Другие модели по мере необходимости ...