# app.py
import requests
from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate # Убедись, что Flask-Migrate установлен
from sqlalchemy import MetaData
from sqlalchemy.exc import IntegrityError, SQLAlchemyError # Для обработки ошибок в сидере
# from flask_mail import Mail # Закомментировано, если не используется сейчас
from dotenv import load_dotenv
import os
import click
from flask.cli import with_appcontext
import datetime
import traceback # Для вывода трейсбека в сидере

# --- Импорты моделей для seed_command и приложения ---
from maps.models import (
    db, SprDiscipline, AupInfo, AupData, SprFaculty, Department,
    SprDegreeEducation, SprFormEducation, SprRop, NameOP, Groups, SprOKCO, 
    D_Blocks, D_Part, D_TypeRecord, D_ControlType, D_EdIzmereniya, D_Period, SprBranch, D_Modules  # Добавлены все нужные
    # SprBells, SprPlace # Добавь, если используются в сидере
)
from auth.models import Roles, Users # Добавлен Users, если понадобится
from competencies_matrix.models import (
    CompetencyType, FgosVo, EducationalProgram, Competency, Indicator,
    CompetencyMatrix, EducationalProgramAup, EducationalProgramPs,
    ProfStandard, FgosRecommendedPs
    # Модели структуры ПС пока не сидим, импорт можно добавить позже
    # GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge, IndicatorPsLink
)

# --- Импорты блюпринтов ---
from cabinet.cabinet import cabinet
# from maps.routes import maps as maps_blueprint # Убедись, что этот импорт и блюпринт действительно нужны
from unification import unification_blueprint
from auth.routes import auth as auth_blueprint
from administration.routes import admin as admin_blueprint
from competencies_matrix import competencies_matrix_bp
from utils.handlers import handle_exception # Убедись, что путь верный

# Загрузка переменных окружения
load_dotenv()

# Создание экземпляра приложения Flask
app = Flask(__name__)
application = app # Для совместимости с некоторыми WSGI серверами

# Загрузка конфигурации
app.config.from_pyfile('config.py')
app.json.sort_keys = False # Отключаем сортировку ключей в JSON ответах

# Настройка CORS
# Разрешает запросы со всех доменов - будь осторожен в production!
cors = CORS(app, resources={r"*": {"origins": "*"}}, supports_credentials=True)

# Настройки SQLAlchemy (перечитываем из переменных окружения на случай, если они там переопределены)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', app.config.get('SQLALCHEMY_DATABASE_URI'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация расширений
# mail = Mail(app) # Раскомментируй, если Flask-Mail используется

# --- Инициализация SQLAlchemy и Migrate ---
# Конвенция именования для индексов и ключей Alembic
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}
metadata = MetaData(naming_convention=convention)

# Инициализируем SQLAlchemy с нашим приложением и конвенцией
db.init_app(app)
# Инициализируем Flask-Migrate ПОСЛЕ db.init_app()
# Указываем metadata для правильной работы с конвенцией именования
migrate = Migrate(app, db, render_as_batch=True, compare_type=True, naming_convention=convention) # render_as_batch=True полезен для SQLite

# --- Регистрация blueprints ---
# Используем app.config.get для безопасного доступа к ключам конфигурации
app.register_blueprint(cabinet, url_prefix=app.config.get('URL_PREFIX_CABINET', '/api/cabinet')) # Добавлен default prefix
app.register_blueprint(auth_blueprint, url_prefix='/api/auth')
app.register_blueprint(admin_blueprint, url_prefix='/api/admin')
app.register_blueprint(unification_blueprint, url_prefix='/api/unification')
app.register_blueprint(competencies_matrix_bp, url_prefix=app.config.get('URL_PREFIX_COMPETENCIES', '/api/competencies')) # Добавлен default prefix

# --- Обработка ошибок ---
# Регистрируем обработчик только если не в режиме отладки
if not app.config.get('DEBUG'):
    app.register_error_handler(Exception, handle_exception)

# --- Базовый маршрут ---
@app.route('/')
def index():
    """Простой GET эндпоинт для проверки, что API работает."""
    return jsonify({'message': 'Maps and Competencies API is running'}), 200

# --- Команда для наполнения БД тестовыми данными ---
@click.command(name='seed_db')
@with_appcontext
def seed_command():
    """Заполняет базу данных начальными/тестовыми данными (Идемпотентно)."""
    print("Starting database seeding...")
    try:
        # === БЛОК 1: Основные Справочники (Первоочередные) ===
        print("Seeding Core Lookups...")

        # Используем merge для идемпотентности - он вставит или обновит по PK
        # Сначала справочники без зависимостей
        db.session.merge(CompetencyType(id=1, code='УК', name='Универсальная'))
        db.session.merge(CompetencyType(id=2, code='ОПК', name='Общепрофессиональная'))
        db.session.merge(CompetencyType(id=3, code='ПК', name='Профессиональная'))

        db.session.merge(Roles(id_role=1, name_role='admin'))
        db.session.merge(Roles(id_role=2, name_role='methodologist'))
        db.session.merge(Roles(id_role=3, name_role='teacher'))
        db.session.merge(Roles(id_role=4, name_role='tutor'))
        db.session.merge(Roles(id_role=5, name_role='student'))

        # Справочники для АУП (ID как в сидере)
        db.session.merge(SprBranch(id_branch=1, city='Москва', location='Основное подразделение')) # Исправлено поле name_branch
        db.session.merge(SprDegreeEducation(id_degree=1, name_deg="Высшее образование - бакалавриат")) # Убедись, что поле name_deg, а не name_degree
        db.session.merge(SprFormEducation(id_form=1, form="Очная")) # Убедись, что поле form, а не name_form
        db.session.merge(SprRop(id_rop=1, last_name='Иванов', first_name='Иван', middle_name='Иванович', email='rop@example.com', telephone='+70000000000')) # Пример для РОП
        # Замени на реальные данные для SprOKCO и NameOP если они используются как FK
        db.session.merge(SprOKCO(program_code='09.03.01', name_okco='Информатика и ВТ')) # Пример ОКСО
        db.session.merge(NameOP(id_spec=1, program_code='09.03.01', num_profile='01', name_spec='Веб-технологии')) # Пример NameOP

        # Добавляем факультет и кафедру (департамент) - обязательно перед АУП
        faculty_1 = db.session.merge(SprFaculty(id_faculty=1, name_faculty='Факультет информатики', id_branch=1))
        department_1 = db.session.merge(Department(id_department=1, name_department='Кафедра веб-технологий', faculty_id=1))
        db.session.commit()  # Коммитим факультет и кафедру

        # Справочники для AupData (ID как в сидере)
        db.session.merge(D_Blocks(id=1, title="Блок 1. Дисциплины (модули)"))
        db.session.merge(D_Part(id=1, title="Обязательная часть"))
        # Add D_Modules entry (required for AupData foreign key constraint)
        db.session.merge(D_Modules(id=1, title="Базовый модуль", color="#FFFFFF"))
        db.session.merge(Groups(id_group=1, name_group="Основные", color="#FFFFFF", weight=1)) # name_group, а не title
        db.session.merge(D_TypeRecord(id=1, title="Дисциплина"))
        db.session.merge(D_ControlType(id=1, title="Экзамен", shortname="Экз")) # Добавил shortname
        db.session.merge(D_ControlType(id=5, title="Зачет", shortname="Зач"))
        db.session.merge(D_EdIzmereniya(id=1, title="Академ. час"))
        db.session.merge(D_Period(id=1, title="Семестр 1"))
        db.session.merge(D_Period(id=2, title="Семестр 2"))

        # Справочники Дисциплин
        db.session.merge(SprDiscipline(id=1001, title='Основы программирования'))
        db.session.merge(SprDiscipline(id=1002, title='Базы данных'))
        db.session.merge(SprDiscipline(id=1003, title='История России'))

        # Коммитим все справочники ПЕРЕД созданием зависимых сущностей
        db.session.commit()
        print("  - Core lookups seeded/merged.")

        # === БЛОК 2: ФГОС и Образовательные Программы ===
        print("Seeding FGOS...")
        # merge вернет объект, который есть в сессии (или новый)
        fgos1 = db.session.merge(FgosVo(id=1, number='929', date=datetime.date(2017, 9, 19), direction_code='09.03.01',
                                       direction_name='Информатика и вычислительная техника', education_level='бакалавриат', generation='3++'))
        db.session.commit()
        print("  - FGOS 09.03.01 checked/merged.")

        print("Seeding Educational Program...")
        # ИСПРАВЛЕНО: Используем 'title' вместо 'name'
        program1 = db.session.merge(EducationalProgram(id=1, fgos_vo_id=1, code='09.03.01', title='Веб-технологии (09.03.01)',
                                                     profile='Веб-технологии', qualification='Бакалавр', form_of_education='очная', enrollment_year=2024))
        db.session.commit()
        print("  - Educational Program 'Веб-технологии' checked/merged.")

        # === БЛОК 3: АУП и его структура ===
        print("Seeding AUP...")
        # merge вернет объект AupInfo
        aup101 = db.session.merge(AupInfo(id_aup=101, num_aup='B093011451', file='example.xlsx', base='11 классов',
                                          id_faculty=1, id_rop=1, type_educ='Высшее', qualification='Бакалавр',
                                          type_standard='ФГОС 3++', id_department=1, period_educ='4 года',
                                          id_degree=1, id_form=1, years=4, months=0, id_spec=1,
                                          year_beg=2024, year_end=2028, is_actual=1))
        db.session.commit()
        print("  - AUP 101 checked/merged.")

        print("Seeding AUP-Program Link...")
        # Для ассоциативных лучше проверка + add
        link_ep_aup = EducationalProgramAup.query.filter_by(educational_program_id=1, aup_id=101).first()
        if not link_ep_aup:
            link_ep_aup = EducationalProgramAup(educational_program_id=1, aup_id=101, is_primary=True)
            db.session.add(link_ep_aup)
            db.session.commit()
            print("  - Linked Program 1 and AUP 101.")
        else:
            print("  - Link Program 1 - AUP 101 already exists.")

        print("Seeding AupData entries...")
        # merge вернет объекты AupData - добавляем discipline (строковое имя дисциплины)
        ad501 = db.session.merge(AupData(
            id=501, id_aup=101, id_discipline=1001, discipline='Основы программирования',
            id_block=1, shifr='Б1.1.07', id_part=1, id_module=1, id_group=1, 
            id_type_record=1, id_period=1, num_row=7, id_type_control=1, 
            amount=14400, id_edizm=1, zet=4
        ))
        ad502 = db.session.merge(AupData(
            id=502, id_aup=101, id_discipline=1002, discipline='Базы данных',
            id_block=1, shifr='Б1.1.10', id_part=1, id_module=1, id_group=1, 
            id_type_record=1, id_period=1, num_row=10, id_type_control=5, 
            amount=10800, id_edizm=1, zet=3
        ))
        ad503 = db.session.merge(AupData(
            id=503, id_aup=101, id_discipline=1003, discipline='История России',
            id_block=1, shifr='Б1.1.01', id_part=1, id_module=1, id_group=1, 
            id_type_record=1, id_period=1, num_row=1, id_type_control=5, 
            amount=7200, id_edizm=1, zet=2
        ))
        db.session.commit()
        print("  - AupData entries checked/merged.")

        # === БЛОК 4: Компетенции и Индикаторы ===
        print("Seeding Competencies & Indicators...")
        # Используем merge
        comp_uk1 = db.session.merge(Competency(id=1, competency_type_id=1, fgos_vo_id=1, code='УК-1', name='Способен осуществлять поиск, критический анализ и синтез информации, применять системный подход для решения поставленных задач'))
        comp_uk5 = db.session.merge(Competency(id=5, competency_type_id=1, fgos_vo_id=1, code='УК-5', name='Способен воспринимать межкультурное разнообразие общества...'))
        comp_opk7 = db.session.merge(Competency(id=107, competency_type_id=2, fgos_vo_id=1, code='ОПК-7', name='Способен участвовать в настройке и наладке программно-аппаратных комплексов'))
        comp_pk1 = db.session.merge(Competency(id=201, competency_type_id=3, fgos_vo_id=None, code='ПК-1', name='Способен выполнять работы по созданию (модификации) и сопровождению ИС...'))

        # Индикаторы - тоже через merge
        # Для УК-1
        db.session.merge(Indicator(id=10, competency_id=1, code='ИУК-1.1', formulation='Анализирует задачу, выделяя ее базовые составляющие', source='Распоряжение 505-Р / ОП Веб-технологии'))
        db.session.merge(Indicator(id=11, competency_id=1, code='ИУК-1.2', formulation='Осуществляет поиск, критически оценивает, обобщает...', source='Распоряжение 505-Р / ОП Веб-технологии'))
        db.session.merge(Indicator(id=12, competency_id=1, code='ИУК-1.3', formulation='Рассматривает и предлагает рациональные варианты...', source='Распоряжение 505-Р / ОП Веб-технологии'))
        # Для УК-5
        db.session.merge(Indicator(id=50, competency_id=5, code='ИУК-5.1', formulation='Анализирует и интерпретирует события...', source='Распоряжение 505-Р / ОП Веб-технологии'))
        # Для ОПК-7
        db.session.merge(Indicator(id=170, competency_id=107, code='ИОПК-7.1', formulation='Знает основные языки программирования...', source='ОП Веб-технологии'))
        # Для ПК-1
        db.session.merge(Indicator(id=210, competency_id=201, code='ИПК-1.1', formulation='Знает: методологию и технологии проектирования...', source='ОП Веб-технологии / ПС 06.015'))

        db.session.commit() # Коммитим компетенции и индикаторы
        print("  - Competencies & Indicators checked/merged.")

        # === БЛОК 5: Связи Матрицы Компетенций ===
        print("Seeding Competency Matrix links...")
        # Используем проверку + add для ассоциативной таблицы
        def add_link_if_not_exists(aup_data_id, indicator_id):
            # Сначала проверяем, существуют ли родительские записи, иначе FK сработает
            aup_data_rec = AupData.query.get(aup_data_id)
            indicator_rec = Indicator.query.get(indicator_id)
            if not aup_data_rec or not indicator_rec:
                 print(f"    - SKIPPED link ({aup_data_id} <-> {indicator_id}): AupData or Indicator missing!")
                 return False # Возвращаем False, если не смогли добавить

            # Проверяем саму связь
            exists = CompetencyMatrix.query.filter_by(aup_data_id=aup_data_id, indicator_id=indicator_id).first()
            if not exists:
                link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
                db.session.add(link)
                print(f"    - Added link ({aup_data_id} <-> {indicator_id})")
                return True # Возвращаем True, если добавили
            # else: # Не будем выводить сообщение о существующей связи
            #    pass
            return True # Возвращаем True, если связь уже есть

        # Основы программирования (501) -> ИУК-1.1(10), ИУК-1.2(11), ИУК-1.3(12), ИОПК-7.1(170)
        add_link_if_not_exists(501, 10)
        add_link_if_not_exists(501, 11)
        add_link_if_not_exists(501, 12)
        add_link_if_not_exists(501, 170)
        # История России (503) -> ИУК-5.1(50)
        add_link_if_not_exists(503, 50)
        # Базы данных (502) -> ИПК-1.1(210)
        add_link_if_not_exists(502, 210)

        db.session.commit() # Коммитим связи
        print("  - Matrix links checked/added based on Excel example.")

        print("Database seeding finished successfully.")

    except (IntegrityError, SQLAlchemyError) as e: # Ловим конкретные ошибки БД
        db.session.rollback()
        print(f"\n!!! DATABASE ERROR during seeding: {e} !!!")
        print("!!! Seeding stopped. Check foreign key constraints and data order. !!!")
        traceback.print_exc()
    except Exception as e: # Ловим все остальные ошибки
        db.session.rollback()
        print(f"\n!!! UNEXPECTED ERROR during seeding: {e} !!!")
        traceback.print_exc()

# Регистрируем команду сидера
app.cli.add_command(seed_command)

# Точка входа для запуска через `python app.py`
if __name__ == '__main__':
    # Рекомендуется использовать Gunicorn или Waitress для production,
    # но для разработки встроенный сервер Flask подходит.
    # host='0.0.0.0' делает сервер доступным извне (например, из Docker контейнера)
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=5000)