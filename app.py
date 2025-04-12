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
from werkzeug.security import generate_password_hash # Для хеширования пароля тестового пользователя
from sqlalchemy.orm import joinedload # Import for eager loading if needed for deletion

# --- Импорты моделей для seed_command и приложения ---
# Основные модели из maps
from maps.models import (
    db, SprDiscipline, AupInfo, AupData, SprFaculty, Department,
    SprDegreeEducation, SprFormEducation, SprRop, NameOP, Groups, SprOKCO,
    D_Blocks, D_Part, D_TypeRecord, D_ControlType, D_EdIzmereniya, D_Period, SprBranch, D_Modules
)

from auth.models import Roles, Users
# Модели из competencies_matrix
from competencies_matrix.models import (
    CompetencyType, FgosVo, EducationalProgram, Competency, Indicator,
    CompetencyMatrix, EducationalProgramAup, EducationalProgramPs,
    ProfStandard, FgosRecommendedPs, IndicatorPsLink, LaborFunction
    # Модели структуры ПС пока не сидим, импорт можно добавить позже
    # GeneralizedLaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
)

# Модели Cabinet
from cabinet.models import (
    StudyGroups, SprPlace, SprBells, DisciplineTable, 
    GradeType, Topics, Students, Tutors, Grade, GradeColumn,
    TutorsOrder, TutorsOrderRow
)

# --- Импорты блюпринтов ---
from cabinet.cabinet import cabinet
from maps.routes import maps as maps_blueprint  # Now importing the maps blueprint
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
cors = CORS(app, 
    resources={r"/*": {"origins": "*"}}, 
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin", "Aup"],
    automatic_options=True
)

# Специальная обработка для OPTIONS запросов
@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def options_handler(path):
    # Обрабатываем OPTIONS запросы для всех маршрутов
    response = app.make_default_options_response()
    return response

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
app.register_blueprint(cabinet, url_prefix=app.config.get('URL_PREFIX_CABINET', '/api'))  # Cabinet routes at /api
app.register_blueprint(maps_blueprint, url_prefix=app.config.get('URL_PREFIX_MAPS', '/api/maps'))  # Maps routes at /api/maps
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
        db.session.merge(SprBranch(id_branch=1, city='Москва', location='Основное подразделение')) # Имя поля уточнено
        db.session.merge(SprDegreeEducation(id_degree=1, name_deg="Высшее образование - бакалавриат")) # Имя поля уточнено
        db.session.merge(SprFormEducation(id_form=1, form="Очная")) # Имя поля уточнено
        db.session.merge(SprRop(id_rop=1, last_name='Иванов', first_name='Иван', middle_name='Иванович', email='rop@example.com', telephone='+70000000000'))
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
        db.session.merge(D_Modules(id=1, title="Базовый модуль", color="#FFFFFF")) # Добавлен цвет
        db.session.merge(Groups(id_group=1, name_group="Основные", color="#FFFFFF", weight=1)) # Имя поля уточнено
        db.session.merge(D_TypeRecord(id=1, title="Дисциплина"))
        db.session.merge(D_ControlType(id=1, title="Экзамен", shortname="Экз"))
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
        # ИСПОЛЬЗУЕМ title
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
        # ВАЖНО: Убедись, что поле fgos_vo_id добавлено в модель Competency и миграцию!
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
        # Используем функцию для проверки и добавления
        def add_link_if_not_exists(aup_data_id, indicator_id):
            aup_data_rec = AupData.query.get(aup_data_id)
            indicator_rec = Indicator.query.get(indicator_id)
            if not aup_data_rec or not indicator_rec:
                 print(f"    - SKIPPED link ({aup_data_id} <-> {indicator_id}): AupData or Indicator missing!")
                 return False

            exists = CompetencyMatrix.query.filter_by(aup_data_id=aup_data_id, indicator_id=indicator_id).first()
            if not exists:
                link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
                db.session.add(link)
                print(f"    - Added link ({aup_data_id} <-> {indicator_id})")
                return True
            return True

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

        # === БЛОК 6: Тестовый Пользователь ===
        print("Seeding Test User...")
        test_user = Users.query.filter_by(login='testuser').first()
        if not test_user:
            test_user = Users(
                # id_user=999, # Позволим БД самой назначить ID через auto-increment
                login='testuser',
                # Устанавливаем хеш пароля 'password'
                password_hash=generate_password_hash('password', method='pbkdf2:sha256'),
                name='Тестовый Методист',
                email='testuser@example.com',
                approved_lk=True # Предполагаем, что для тестов одобрение ЛК не нужно
                # Добавь department_id, если оно обязательно
            )
            db.session.add(test_user)
            db.session.commit() # Коммитим пользователя ПЕРЕД назначением роли
            print(f"  - Added test user 'testuser' with id {test_user.id_user}.")

            # Назначаем роль methodologist (ID=2)
            methodologist_role = Roles.query.get(2)
            if methodologist_role:
                # if not user_role_link:
                #     user_role_link = UserRoles(user_id=test_user.id_user, role_id=methodologist_role.id_role)
                #     db.session.add(user_role_link)
                #     db.session.commit()
                #     print("  - Assigned 'methodologist' role to 'testuser'.")
                if methodologist_role not in test_user.roles:
                    test_user.roles.append(methodologist_role)
                    db.session.commit()
                    print("  - Assigned 'methodologist' role to 'testuser'.")
                else:
                    print("  - Role 'methodologist' already assigned to 'testuser'.")
            else:
                print("  - WARNING: Role 'methodologist' (ID=2) not found, skipping role assignment.")
        else:
            print("  - Test user 'testuser' already exists.")

        # === BLOCK 7: Admin User ===
        print("Seeding Admin User...")
        admin_user = Users.query.filter_by(login='admin').first()
        if not admin_user:
            admin_user = Users(
                login='admin',
                password_hash=generate_password_hash('admin', method='pbkdf2:sha256'),
                name='Admin User',
                email='admin@example.com',
                approved_lk=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print(f"  - Added admin user 'admin' with id {admin_user.id_user}")

            # Assign admin role (ID=1)
            admin_role = Roles.query.get(1)
            if admin_role:
                if admin_role not in admin_user.roles:
                    admin_user.roles.append(admin_role)
                    db.session.commit()
                    print("  - Assigned 'admin' role to admin user")
                else:
                    print("  - Role 'admin' already assigned to admin user")
            else:
                print("  - WARNING: Role 'admin' (ID=1) not found, skipping role assignment")
        else:
            print("  - Admin user 'admin' already exists")

        # === BLOCK 8: Cabinet Models (Academic Cabinet) ===
        print("Seeding Cabinet Models...")
        
        # Add classroom locations (SprPlace)
        places = [
            SprPlace(id=1, name="Аудитория", prefix="А", is_online=False),
            SprPlace(id=2, name="Online", prefix="", is_online=True),
            SprPlace(id=3, name="Лаборатория", prefix="Л", is_online=False),
            SprPlace(id=4, name="Компьютерный класс", prefix="КК", is_online=False)
        ]
        for place in places:
            db.session.merge(place)
        db.session.commit()
        print("  - Classroom locations seeded.")
        
        # Add bell schedule (SprBells)
        bells = [
            SprBells(id=1, order=1, name="9:00 - 10:30"),
            SprBells(id=2, order=2, name="10:40 - 12:10"),
            SprBells(id=3, order=3, name="12:20 - 13:50"),
            SprBells(id=4, order=4, name="14:30 - 16:00"),
            SprBells(id=5, order=5, name="16:10 - 17:40"),
            SprBells(id=6, order=6, name="17:50 - 19:20")
        ]
        for bell in bells:
            db.session.merge(bell)
        db.session.commit()
        print("  - Bell schedule seeded.")
        
        # Add study groups (StudyGroups)
        test_group = StudyGroups.query.filter_by(title="211-321").first()
        if not test_group:
            # Remove the explicit ID to allow auto-increment
            test_group = StudyGroups(
                # Remove id=1 to avoid primary key conflicts
                title="211-321", 
                num_aup="B093011451"
            )
            db.session.add(test_group)
            db.session.commit()
            print("  - Study group 211-321 added.")
        else:
            # Update the existing record if needed
            test_group.num_aup = "B093011451"
            db.session.commit()
            print("  - Study group 211-321 already exists, updated if needed.")

        # Add a test student
        test_student = Students.query.filter_by(name="Иванов Иван Иванович").first()
        if not test_student:
            test_student = Students(
                name="Иванов Иван Иванович", 
                study_group_id=test_group.id, 
                lk_id=1001
            )
            db.session.add(test_student)
            db.session.commit()
            print("  - Test student added.")
        else:
            print("  - Test student already exists.")
            
        # Add a test tutor
        test_tutor = Tutors.query.filter_by(name="Петров Петр Петрович").first()
        if not test_tutor:
            test_tutor = Tutors(
                name="Петров Петр Петрович",
                lk_id=2001,
                post="Доцент",
                id_department=1  # Using the department added earlier
            )
            db.session.add(test_tutor)
            db.session.commit()
            print("  - Test tutor added.")
        else:
            print("  - Test tutor already exists.")
            
        # Create DisciplineTable entry for the test AUP and group
        discipline_table = DisciplineTable.query.filter_by(
            id_aup=101, 
            id_unique_discipline=1001, 
            study_group_id=test_group.id,
            semester=1
        ).first()
        
        if not discipline_table:
            discipline_table = DisciplineTable(
                id=1,
                id_aup=101,  # From seeded AUP
                id_unique_discipline=1001,  # From seeded SprDiscipline
                study_group_id=test_group.id,
                semester=1
            )
            db.session.add(discipline_table)
            db.session.commit()
            print("  - Discipline table created.")
        else:
            print("  - Discipline table already exists.")
            
        # Add grade types (GradeType)
        grade_types_data = [
            {"id": 1, "name": "Посещаемость", "type": "attendance", "binary": True, "discipline_table_id": discipline_table.id},
            {"id": 2, "name": "Активность", "type": "activity", "binary": False, "discipline_table_id": discipline_table.id},
            {"id": 3, "name": "Задания", "type": "tasks", "binary": False, "discipline_table_id": discipline_table.id}
        ]
        
        for grade_type_data in grade_types_data:
            grade_type = GradeType.query.filter_by(id=grade_type_data["id"]).first()
            if not grade_type:
                grade_type = GradeType(**grade_type_data)
                db.session.add(grade_type)
        db.session.commit()
        print("  - Grade types created.")
        
        # Add a couple of topics to the discipline table
        topics_data = [
            {
                "id": 1,
                "discipline_table_id": discipline_table.id,
                "topic": "Введение в предмет",
                "chapter": "Глава 1",
                "id_type_control": 1,  # Lecture (from D_ControlType)
                "task_link": "https://example.com/task1",
                "task_link_name": "Задание 1",
                "study_group_id": test_group.id,
                "spr_place_id": 1,  # Classroom
                "lesson_order": 1
            },
            {
                "id": 2,
                "discipline_table_id": discipline_table.id,
                "topic": "Основные понятия",
                "chapter": "Глава 1",
                "id_type_control": 1,  # Lecture
                "task_link": "https://example.com/task2",
                "task_link_name": "Задание 2",
                "study_group_id": test_group.id,
                "spr_place_id": 1,  # Classroom
                "lesson_order": 2
            }
        ]
        
        for topic_data in topics_data:
            topic = Topics.query.filter_by(id=topic_data["id"]).first()
            if not topic:
                topic = Topics(**topic_data)
                db.session.add(topic)
        db.session.commit()
        print("  - Topics created.")
        
        # Add grade columns for the topics and grade types
        for topic in Topics.query.all():
            for grade_type in GradeType.query.all():
                grade_column = GradeColumn.query.filter_by(
                    discipline_table_id=discipline_table.id,
                    grade_type_id=grade_type.id,
                    topic_id=topic.id
                ).first()
                
                if not grade_column:
                    grade_column = GradeColumn(
                        discipline_table_id=discipline_table.id,
                        grade_type_id=grade_type.id,
                        topic_id=topic.id
                    )
                    db.session.add(grade_column)
        db.session.commit()
        print("  - Grade columns created.")
        
        # Add some sample grades for the student
        for grade_column in GradeColumn.query.all():
            grade = Grade.query.filter_by(
                student_id=test_student.id,
                grade_column_id=grade_column.id
            ).first()
            
            if not grade:
                # Random grades between 3 and 5
                import random
                value = random.randint(3, 5)
                
                # For attendance (binary), use 1 for present
                if grade_column.grade_type.type == 'attendance':
                    value = 1
                    
                grade = Grade(
                    student_id=test_student.id,
                    grade_column_id=grade_column.id,
                    value=value
                )
                db.session.add(grade)
        db.session.commit()
        print("  - Sample grades created.")
        
        print("Cabinet models seeded successfully.")
        print("\nDatabase seeding finished successfully.")

    except (IntegrityError, SQLAlchemyError) as e: # Ловим конкретные ошибки БД
        db.session.rollback()
        print(f"\n!!! DATABASE ERROR during seeding: {e} !!!")
        print("!!! Seeding stopped. Check foreign key constraints and data order. !!!")
        traceback.print_exc()
    except Exception as e: # Ловим все остальные ошибки
        db.session.rollback()
        print(f"\n!!! UNEXPECTED ERROR during seeding: {e} !!!")
        traceback.print_exc()

# --- Команда для удаления тестовых данных из БД ---
@click.command(name='unseed_db')
@with_appcontext
def unseed_command():
    """Удаляет из базы данных тестовые данные, добавленные командой seed_db (Идемпотентно)."""
    print("Starting database unseeding...")
    try:
        # === БЛОК 8: Cabinet Models (Reverse Order) ===
        print("Unseeding Cabinet Models...")

        # Delete Grades first (depends on GradeColumn and Students)
        print("  - Deleting sample grades...")
        # Find the test student first
        test_student = Students.query.filter_by(name="Иванов Иван Иванович").first()
        if test_student:
            Grade.query.filter_by(student_id=test_student.id).delete()
            db.session.commit()
            print(f"    - Deleted grades for student ID {test_student.id}.")
        else:
            print("    - Test student not found, skipping grade deletion.")

        # Delete Grade Columns (depends on GradeType and Topics) - BEFORE Topics
        print("  - Deleting grade columns...")
        # Find the discipline table first
        test_group = StudyGroups.query.filter_by(title="211-321").first()
        discipline_table = None
        if test_group:
             discipline_table = DisciplineTable.query.filter_by(
                id_aup=101,
                id_unique_discipline=1001,
                study_group_id=test_group.id,
                semester=1
            ).first()

        if discipline_table:
            # Delete GradeColumns associated with the specific discipline_table
            GradeColumn.query.filter_by(discipline_table_id=discipline_table.id).delete()
            db.session.commit()
            print(f"    - Deleted grade columns for discipline table ID {discipline_table.id}.")
        else:
             # If discipline_table not found, try deleting based on seeded topic IDs if possible
             # This might be necessary if the discipline_table was already deleted or not found
             seeded_topic_ids = [1, 2] # Assuming these were the seeded topic IDs
             grade_columns_to_delete = GradeColumn.query.filter(GradeColumn.topic_id.in_(seeded_topic_ids)).all()
             if grade_columns_to_delete:
                 gc_ids_deleted = [gc.id for gc in grade_columns_to_delete]
                 GradeColumn.query.filter(GradeColumn.id.in_(gc_ids_deleted)).delete(synchronize_session=False)
                 db.session.commit()
                 print(f"    - Deleted grade columns linked to seeded topics (IDs: {gc_ids_deleted}).")
             else:
                 print("    - Discipline table not found and no grade columns found linked to seeded topics.")


        # Delete Topics (depends on DisciplineTable, SprPlace, D_ControlType) - AFTER GradeColumn
        print("  - Deleting topics...")
        if discipline_table:
            # Ensure GradeColumns are deleted first (handled above)
            Topics.query.filter_by(discipline_table_id=discipline_table.id).delete()
            db.session.commit()
            print(f"    - Deleted topics for discipline table ID {discipline_table.id}.")
        else:
            # Attempt to delete topics even if discipline_table is not found,
            # as they might exist independently or linked differently.
            # We need to be careful here not to delete unrelated topics.
            # Let's find topics linked to the specific seeded places if possible.
            place_ids_for_topics = [1] # Assuming seeded topics only used place ID 1
            seeded_topic_ids = [1, 2] # Explicitly list seeded topic IDs
            # Ensure GradeColumns referencing these topics are deleted first (handled above)
            topics_to_delete = Topics.query.filter(Topics.id.in_(seeded_topic_ids)).all()
            if topics_to_delete:
                topic_ids_deleted = [t.id for t in topics_to_delete]
                # Double check grade columns are gone for these topics
                GradeColumn.query.filter(GradeColumn.topic_id.in_(topic_ids_deleted)).delete(synchronize_session=False)
                db.session.commit()
                # Now delete topics
                Topics.query.filter(Topics.id.in_(topic_ids_deleted)).delete(synchronize_session=False)
                db.session.commit()
                print(f"    - Deleted seeded topics (IDs: {topic_ids_deleted}).")
            else:
                print("    - No seeded topics found linked to seeded places or discipline table.")


        # Delete Grade Types (depends on DisciplineTable) - AFTER GradeColumn
        print("  - Deleting grade types...")
        if discipline_table:
            # Ensure GradeColumns referencing these types are deleted first (handled above)
            GradeType.query.filter_by(discipline_table_id=discipline_table.id).delete()
            db.session.commit()
            print(f"    - Deleted grade types for discipline table ID {discipline_table.id}.")
        else:
            # If discipline_table not found, try deleting based on seeded IDs if possible
            seeded_grade_type_ids = [1, 2, 3] # Assuming these were the seeded grade type IDs
            # Ensure GradeColumns referencing these types are deleted first (handled above)
            grade_types_to_delete = GradeType.query.filter(GradeType.id.in_(seeded_grade_type_ids)).all()
            if grade_types_to_delete:
                gt_ids_deleted = [gt.id for gt in grade_types_to_delete]
                # Double check grade columns are gone for these types
                GradeColumn.query.filter(GradeColumn.grade_type_id.in_(gt_ids_deleted)).delete(synchronize_session=False)
                db.session.commit()
                # Now delete grade types
                GradeType.query.filter(GradeType.id.in_(gt_ids_deleted)).delete(synchronize_session=False)
                db.session.commit()
                print(f"    - Deleted seeded grade types (IDs: {gt_ids_deleted}).")
            else:
                print("    - Discipline table not found and no seeded grade types found.")

        # Delete DisciplineTable entry - AFTER Topics, GradeTypes, GradeColumns
        print("  - Deleting discipline table entry...")
        if discipline_table:
            # Ensure dependent entities are deleted (handled above)
            db.session.delete(discipline_table)
            db.session.commit()
            print(f"    - Deleted discipline table entry with ID {discipline_table.id}.")
        else:
            print("    - Discipline table entry not found, skipping deletion.")

        # Delete Test Tutor
        print("  - Deleting test tutor...")
        test_tutor = Tutors.query.filter_by(name="Петров Петр Петрович").first()
        if test_tutor:
            # Delete dependent TutorsOrderRow first if necessary
            TutorsOrderRow.query.filter_by(tutor_id=test_tutor.id).delete()
            db.session.commit()
            db.session.delete(test_tutor)
            db.session.commit()
            print(f"    - Deleted tutor '{test_tutor.name}'.")
        else:
            print("    - Test tutor not found.")

        # Delete Test Student - AFTER Grades
        print("  - Deleting test student...")
        # Re-query in case it was deleted above somehow
        test_student = Students.query.filter_by(name="Иванов Иван Иванович").first()
        if test_student:
            # Ensure Grades are deleted first (handled above)
            db.session.delete(test_student)
            db.session.commit()
            print(f"    - Deleted student '{test_student.name}'.")
        else:
            print("    - Test student not found.")

        # Delete Study Group - AFTER Students, Topics, DisciplineTable, TutorsOrderRow
        print("  - Deleting study group...")
        # Re-query in case it was deleted above somehow
        test_group = StudyGroups.query.filter_by(title="211-321").first()
        if test_group:
            # Delete dependent entities first
            Students.query.filter_by(study_group_id=test_group.id).delete()
            Topics.query.filter_by(study_group_id=test_group.id).delete()
            DisciplineTable.query.filter_by(study_group_id=test_group.id).delete()
            TutorsOrderRow.query.filter_by(study_group_id=test_group.id).delete()
            db.session.commit()
            db.session.delete(test_group)
            db.session.commit()
            print(f"    - Deleted study group '{test_group.title}'.")
        else:
            print("    - Test study group not found.")

        # Delete Bell Schedule - AFTER Topics
        print("  - Deleting bell schedule...")
        bell_ids = [1, 2, 3, 4, 5, 6]
        # Ensure Topics referencing these bells are deleted first (handled above)
        SprBells.query.filter(SprBells.id.in_(bell_ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f"    - Deleted bell schedule entries with IDs {bell_ids}.")

        # Delete Classroom Locations (SprPlace) - AFTER deleting dependent Topics
        print("  - Deleting classroom locations...")
        place_ids = [1, 2, 3, 4]
        # Ensure Topics referencing these places are deleted first (handled above)
        SprPlace.query.filter(SprPlace.id.in_(place_ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f"    - Deleted classroom location entries with IDs {place_ids}.")

        print("Cabinet models unseeded.")

        # === БЛОК 7 & 6: Users and Roles ===
        print("Unseeding Users and Roles...")

        # Remove roles from users first
        print("  - Removing roles from test/admin users...")
        admin_user = Users.query.filter_by(login='admin').first()
        test_user = Users.query.filter_by(login='testuser').first()

        if admin_user:
            admin_role = Roles.query.get(1)
            if admin_role and admin_role in admin_user.roles:
                admin_user.roles.remove(admin_role)
                print("    - Removed 'admin' role from 'admin' user.")
        if test_user:
            methodologist_role = Roles.query.get(2)
            if methodologist_role and methodologist_role in test_user.roles:
                test_user.roles.remove(methodologist_role)
                print("    - Removed 'methodologist' role from 'testuser' user.")
        db.session.commit() # Commit role removals

        # Delete Users
        print("  - Deleting test/admin users...")
        if admin_user:
            db.session.delete(admin_user)
            print("    - Deleted 'admin' user.")
        else:
            print("    - Admin user 'admin' not found.")
        if test_user:
            db.session.delete(test_user)
            print("    - Deleted 'testuser' user.")
        else:
            print("    - Test user 'testuser' not found.")
        db.session.commit() # Commit user deletions

        # Delete Roles (only those added by seeder)
        print("  - Deleting seeded roles...")
        role_ids = [1, 2, 3, 4, 5]
        Roles.query.filter(Roles.id_role.in_(role_ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f"    - Deleted roles with IDs {role_ids}.")

        print("Users and Roles unseeded.")

        # === БЛОК 4: Компетенции и Индикаторы ===
        print("Unseeding Competencies & Indicators...")

        # First handle all competencies related to the competency types we want to delete
        competency_type_ids = [1, 2, 3]  # The types we want to delete eventually

        # 1. Find ALL competencies linked to these types (not just our seeded ones)
        all_competencies = Competency.query.filter(
            Competency.competency_type_id.in_(competency_type_ids)
        ).all()

        all_competency_ids = [comp.id for comp in all_competencies]
        print(f"  - Found {len(all_competency_ids)} competencies linked to competency types {competency_type_ids}")

        if all_competency_ids:
            # 2. Find all indicators linked to these competencies
            indicators_to_delete = Indicator.query.filter(
                Indicator.competency_id.in_(all_competency_ids)
            ).all()
            
            indicator_ids_to_delete = [ind.id for ind in indicators_to_delete]
            print(f"  - Found {len(indicator_ids_to_delete)} indicators linked to these competencies")
            
            # 3. Delete CompetencyMatrix entries linked to these indicators
            if indicator_ids_to_delete:
                print("  - Deleting CompetencyMatrix entries linked to indicators...")
                deleted_matrix_count = CompetencyMatrix.query.filter(
                    CompetencyMatrix.indicator_id.in_(indicator_ids_to_delete)
                ).delete(synchronize_session='fetch')
                db.session.commit()
                print(f"    - Deleted {deleted_matrix_count} CompetencyMatrix entries")
            
            # 4. Delete IndicatorPsLink entries linked to these indicators
            if indicator_ids_to_delete:
                print("  - Deleting IndicatorPsLink entries...")
                deleted_link_count = IndicatorPsLink.query.filter(
                    IndicatorPsLink.indicator_id.in_(indicator_ids_to_delete)
                ).delete(synchronize_session='fetch')
                db.session.commit()
                print(f"    - Deleted {deleted_link_count} IndicatorPsLink entries")
            
            # 5. Delete all indicators linked to these competencies
            if indicator_ids_to_delete:
                print("  - Deleting indicators...")
                deleted_indicator_count = Indicator.query.filter(
                    Indicator.id.in_(indicator_ids_to_delete)
                ).delete(synchronize_session='fetch')
                db.session.commit()
                print(f"    - Deleted {deleted_indicator_count} indicators")
            
            # 6. Now it's safe to delete all competencies linked to these types
            print("  - Deleting all competencies linked to competency types...")
            deleted_comp_count = Competency.query.filter(
                Competency.competency_type_id.in_(competency_type_ids)
            ).delete(synchronize_session='fetch')
            db.session.commit()
            print(f"    - Deleted {deleted_comp_count} competencies")

        # Finally delete the specific seeded competencies (in case they weren't linked to the types)
        seeded_competency_ids = [1, 5, 107, 201]
        Competency.query.filter(Competency.id.in_(seeded_competency_ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f"  - Deleted any remaining seeded competencies with IDs {seeded_competency_ids}")

        # Now we can safely delete the competency types
        print("  - Deleting competency types...")
        CompetencyType.query.filter(CompetencyType.id.in_(competency_type_ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f"  - Deleted competency types with IDs {competency_type_ids}")

        # === БЛОК 3: АУП и его структура ===
        print("Unseeding AUP and structure...")
        # First check for and delete ANY discipline tables referencing this AUP
        discipline_tables_for_aup = DisciplineTable.query.filter_by(id_aup=101).all()
        if discipline_tables_for_aup:
            dt_ids = [dt.id for dt in discipline_tables_for_aup]
            print(f"  - Found {len(dt_ids)} discipline tables still referencing AUP 101")
            
            # Delete any grade columns linked to these discipline tables
            for dt in discipline_tables_for_aup:
                GradeColumn.query.filter_by(discipline_table_id=dt.id).delete()
            db.session.commit()
            print("    - Deleted grade columns for these discipline tables")
            
            # Delete any topics linked to these discipline tables
            for dt in discipline_tables_for_aup:
                Topics.query.filter_by(discipline_table_id=dt.id).delete()
            db.session.commit()
            print("    - Deleted topics for these discipline tables")
            
            # Delete any grade types linked to these discipline tables
            for dt in discipline_tables_for_aup:
                GradeType.query.filter_by(discipline_table_id=dt.id).delete()
            db.session.commit()
            print("    - Deleted grade types for these discipline tables")
            
            # Now delete the discipline tables themselves
            DisciplineTable.query.filter(DisciplineTable.id.in_(dt_ids)).delete(synchronize_session=False)
            db.session.commit()
            print(f"    - Deleted {len(dt_ids)} discipline tables with IDs {dt_ids}")

        # Delete AupData entries
        aup_data_ids = [501, 502, 503]
        AupData.query.filter(AupData.id.in_(aup_data_ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f"  - Deleted AupData entries with IDs {aup_data_ids}.")

        # Delete AUP-Program Link
        link_ep_aup = EducationalProgramAup.query.filter_by(educational_program_id=1, aup_id=101).first()
        if link_ep_aup:
            db.session.delete(link_ep_aup)
            db.session.commit()
            print("  - Deleted link between Program 1 and AUP 101.")
        else:
            print("  - Link Program 1 - AUP 101 not found.")

        # Delete AupInfo
        aup101 = AupInfo.query.get(101)
        if aup101:
            db.session.delete(aup101)
            db.session.commit()
            print("  - Deleted AUP 101.")
        else:
            print("  - AUP 101 not found.")

        # === БЛОК 2: ФГОС и Образовательные Программы ===
        print("Unseeding Educational Program and FGOS...")

        # First delete all links between programs and other entities
        print("  - Deleting Educational Program links...")
        EducationalProgramAup.query.filter_by(educational_program_id=1).delete()
        EducationalProgramPs.query.filter_by(educational_program_id=1).delete()
        db.session.commit()
        print("    - Deleted program links.")

        # Delete FGOS-related entities in correct order
        print("  - Deleting FGOS-related entities...")
        # First delete competencies that reference this FGOS
        Competency.query.filter_by(fgos_vo_id=1).delete()
        # Then delete PS recommendations
        FgosRecommendedPs.query.filter_by(fgos_vo_id=1).delete()
        db.session.commit()
        print("    - Deleted FGOS-related links.")

        # Now delete the Educational Program
        program1 = EducationalProgram.query.get(1)
        if program1:
            db.session.delete(program1)
            db.session.commit()
            print("  - Deleted Educational Program 'Веб-технологии'.")
        else:
            print("  - Educational Program 'Веб-технологии' not found.")

        # Finally delete the FGOS
        fgos1 = FgosVo.query.get(1)
        if fgos1:
            db.session.delete(fgos1)
            db.session.commit()
            print("  - Deleted FGOS 09.03.01.")
        else:
            print("  - FGOS 09.03.01 not found.")

        print("FGOS and Educational Program unseeded.")

        # === БЛОК 1: Основные Справочники (Reverse Order) ===
        print("Unseeding Core Lookups...")

        # Delete Disciplines
        discipline_ids = [1001, 1002, 1003]
        SprDiscipline.query.filter(SprDiscipline.id.in_(discipline_ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f"  - Deleted disciplines with IDs {discipline_ids}.")

        # Delete AupData related lookups
        D_Period.query.filter(D_Period.id.in_([1, 2])).delete(synchronize_session=False)
        D_EdIzmereniya.query.filter_by(id=1).delete()
        D_ControlType.query.filter(D_ControlType.id.in_([1, 5])).delete(synchronize_session=False)
        D_TypeRecord.query.filter_by(id=1).delete()
        Groups.query.filter_by(id_group=1).delete()
        D_Modules.query.filter_by(id=1).delete()
        D_Part.query.filter_by(id=1).delete()
        D_Blocks.query.filter_by(id=1).delete()
        db.session.commit()
        print("  - Deleted AupData related lookups.")

        # Delete Department and Faculty (Department depends on Faculty)
        department_1 = Department.query.get(1)
        if department_1:
            # Delete dependent entities first if necessary (e.g., Tutors linked to department)
            Tutors.query.filter_by(id_department=1).delete()
            AupInfo.query.filter_by(id_department=1).delete() # AUP linked to department
            db.session.commit()
            db.session.delete(department_1)
            db.session.commit()
            print("  - Deleted Department 'Кафедра веб-технологий'.")
        else:
            print("  - Department 'Кафедра веб-технологий' not found.")

        faculty_1 = SprFaculty.query.get(1)
        if faculty_1:
            # Delete dependent entities first if necessary (e.g., Departments linked to faculty)
            # Department deletion handled above
            AupInfo.query.filter_by(id_faculty=1).delete() # AUP linked to faculty
            db.session.commit()
            db.session.delete(faculty_1)
            db.session.commit()
            print("  - Deleted Faculty 'Факультет информатики'.")
        else:
            print("  - Faculty 'Факультет информатики' not found.")

        # Delete other core lookups
        NameOP.query.filter_by(id_spec=1).delete()
        SprOKCO.query.filter_by(program_code='09.03.01').delete()
        SprRop.query.filter_by(id_rop=1).delete()
        SprFormEducation.query.filter_by(id_form=1).delete()
        SprDegreeEducation.query.filter_by(id_degree=1).delete()
        SprBranch.query.filter_by(id_branch=1).delete()
        CompetencyType.query.filter(CompetencyType.id.in_([1, 2, 3])).delete(synchronize_session=False)
        db.session.commit()
        print("  - Deleted remaining core lookups.")

        print("\nDatabase unseeding finished successfully.")

    except (IntegrityError, SQLAlchemyError) as e: # Ловим конкретные ошибки БД
        db.session.rollback()
        print(f"\n!!! DATABASE ERROR during unseeding: {e} !!!")
        print("!!! Unseeding stopped. Check foreign key constraints and data order. !!!")
        traceback.print_exc()
    except Exception as e: # Ловим все остальные ошибки
        db.session.rollback()
        print(f"\n!!! UNEXPECTED ERROR during unseeding: {e} !!!")
        traceback.print_exc()


# Регистрируем команду сидера
app.cli.add_command(seed_command)
# Регистрируем команду ансидера
app.cli.add_command(unseed_command)

# Точка входа для запуска через `python app.py`
if __name__ == '__main__':
    # Рекомендуется использовать Gunicorn или Waitress для production,
    # но для разработки встроенный сервер Flask подходит.
    # host='0.0.0.0' делает сервер доступным извне (например, из Docker контейнера)
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=5000)