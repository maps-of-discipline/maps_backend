# app.py
import requests
from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import MetaData
from flask_mail import Mail
from dotenv import load_dotenv
import os
import click
from flask.cli import with_appcontext
import datetime

# --- Корректные импорты моделей для seed_command ---
from maps.models import db, SprDiscipline, AupInfo, AupData, SprFaculty, Department, SprDegreeEducation, SprFormEducation, SprRop, NameOP, AupInfo # Убрал init_db, используем Alembic. Добавил AupInfo, если нужен merge
from auth.models import Users, Roles
from competencies_matrix.models import ( # <<<--- УДАЛЕНЫ MasteryLevel и IndicatorMasteryDescriptor
    CompetencyType, FgosVo, EducationalProgram, Competency, Indicator,
    CompetencyMatrix, EducationalProgramAup, EducationalProgramPs,
    ProfStandard, FgosRecommendedPs, GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge, IndicatorPsLink
)
# --- Импорты блюпринтов ---
# Убедись, что импорты верны для твоей структуры
from cabinet.cabinet import cabinet
# from maps.routes import maps as maps_blueprint # Кажется, maps_blueprint не используется, т.к. нет регистрации ниже?
from unification import unification_blueprint # Убедись, что он существует
from auth.routes import auth as auth_blueprint
from administration.routes import admin as admin_blueprint
from competencies_matrix import competencies_matrix_bp
from utils.handlers import handle_exception # Убедись, что он существует

load_dotenv()
app = Flask(__name__)
application = app
# Настройка CORS
cors = CORS(app, resources={r"*": {"origins": "*"}}, supports_credentials=True)
app.config.from_pyfile('config.py')
app.json.sort_keys = False

# Настройки SQLAlchemy (из config.py)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация расширений
mail = Mail(app)

# --- Инициализация SQLAlchemy и Migrate ---
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}
metadata = MetaData(naming_convention=convention)

db.init_app(app)
migrate = Migrate(app, db) # Инициализация здесь, после db.init_app

# --- Регистрация blueprints ---
app.register_blueprint(cabinet, url_prefix=app.config['URL_PREFIX_CABINET'])
# app.register_blueprint(maps_blueprint) # Если он нужен, раскомментируй и проверь импорт
app.register_blueprint(auth_blueprint)
app.register_blueprint(unification_blueprint) # Если он нужен
app.register_blueprint(admin_blueprint)
app.register_blueprint(competencies_matrix_bp)

# Обработка ошибок
if not app.config.get('DEBUG'): # Используй app.config.get для безопасного доступа
    app.register_error_handler(Exception, handle_exception)

# Простой маршрут
@app.route('/')
def index():
    return {'message': 'Maps and Competencies API is running'}, 200

# --- Команда seed_db ---
@click.command(name='seed_db')
@with_appcontext
def seed_command():
    """Заполняет базу данных начальными/тестовыми данными."""
    print("Starting database seeding...")
    try:
        # --- 1. Базовые справочники ---
        print("Seeding Competency Types...")
        existing_types = {ct.code for ct in CompetencyType.query.with_entities(CompetencyType.code).all()}
        types_to_add = [
            CompetencyType(id=1, code='УК', name='Универсальная') if 'УК' not in existing_types else None,
            CompetencyType(id=2, code='ОПК', name='Общепрофессиональная') if 'ОПК' not in existing_types else None,
            CompetencyType(id=3, code='ПК', name='Профессиональная') if 'ПК' not in existing_types else None
        ]
        types_to_add = [t for t in types_to_add if t is not None]
        if types_to_add:
            db.session.bulk_save_objects(types_to_add)
            db.session.commit()
            print(f"  - Added {len(types_to_add)} competency types.")
        else:
            print("  - Competency types already exist.")


        print("Seeding Roles...")
        existing_roles = {r.name_role for r in Roles.query.with_entities(Roles.name_role).all()}
        roles_to_add_data = [
            {'id_role': 1, 'name_role': 'admin'}, {'id_role': 2, 'name_role': 'methodologist'},
            {'id_role': 3, 'name_role': 'teacher'}, {'id_role': 4, 'name_role': 'tutor'},
            {'id_role': 5, 'name_role': 'student'}
        ]
        roles_to_add = [Roles(**data) for data in roles_to_add_data if data['name_role'] not in existing_roles]
        if roles_to_add:
             db.session.bulk_save_objects(roles_to_add)
             db.session.commit()
             print(f"  - Added {len(roles_to_add)} default roles.")
        else:
             print("  - Default roles already exist.")


        # --- 2. Вспомогательные справочники (из maps) ---
        print("Seeding Faculties, Departments, etc. (Example)...")
        # Используем merge для идемпотентности - он вставит или проигнорирует (или обновит, если отличается)
        db.session.merge(SprFaculty(id_faculty=1, name_faculty="Факультет Информационных Технологий", id_branch=1))
        db.session.merge(Department(id_department=1, name_department="Кафедра ИВТ", faculty_id=1))
        # TODO: Добавь сюда merge или bulk_insert_mappings (с проверкой) для других справочников
        db.session.commit()
        print("  - Faculties, Departments checked/merged.")


        # --- 3. Основные тестовые данные для competencies_matrix ---
        print("Seeding FGOS...")
        fgos = FgosVo(id=1, number='929', date=datetime.date(2017, 9, 19), direction_code='09.03.01', direction_name='Информатика и вычислительная техника', education_level='бакалавриат', generation='3++')
        db.session.merge(fgos)
        db.session.commit()
        print("  - FGOS 09.03.01 checked/merged.")

        print("Seeding Educational Program...")
        program = EducationalProgram(id=1, fgos_vo_id=1, code='09.03.01', name='Веб-технологии (09.03.01)', profile='Веб-технологии', qualification='Бакалавр', form_of_education='очная', enrollment_year=2024)
        db.session.merge(program)
        db.session.commit()
        print("  - Educational Program 'Веб-технологии' checked/merged.")

        print("Seeding AUP (if not exists)...")
        # Создаем FK сущности ПЕРЕД созданием AUP, если их нет
        # TODO: Убедись, что эти записи созданы выше или существуют
        faculty_id=1; rop_id=1; degree_id=1; form_id=1; spec_id=1; dept_id=1
        aup = AupInfo(id_aup=101, num_aup='B093011451', file='example.xlsx', base='11 классов', id_faculty=faculty_id, id_rop=rop_id, type_educ='Высшее', qualification='Бакалавр', type_standard='ФГОС 3++', id_department=dept_id, period_educ='4 года', id_degree=degree_id, id_form=form_id, years=4, id_spec=spec_id, year_beg=2024, year_end=2028, is_actual=1)
        db.session.merge(aup)
        db.session.commit()
        print("  - AUP 101 checked/merged.")

        print("Seeding AUP-Program Link...")
        ep_aup_link = EducationalProgramAup(educational_program_id=1, aup_id=101, is_primary=True)
        db.session.merge(ep_aup_link) # merge работает и для составных ключей
        db.session.commit()
        print("  - Link Program 1 - AUP 101 checked/merged.")

        print("Seeding Disciplines (if not exists)...")
        db.session.merge(SprDiscipline(id=1001, title='Основы программирования'))
        db.session.merge(SprDiscipline(id=1002, title='Базы данных'))
        db.session.commit()
        print("  - Disciplines checked/merged.")

        print("Seeding AupData entries (if not exists)...")
        # TODO: Убедись, что FK существуют (block_id, part_id, ...)
        block_id=1; part_id=1; module_id=1; group_id=1; type_rec_id=1; type_ctrl_id_exam=1; type_ctrl_id_zachet=5; edizm_id=1; period_id=1
        ad1 = AupData(id=501, id_aup=101, id_discipline=1001, semester=1, zet=400, total_hours=14400, control_type='Экзамен', id_block=block_id, shifr='Б1.O.01', id_part=part_id, id_module=module_id, id_group=group_id, id_type_record=type_rec_id, id_period=period_id, num_row=1, id_type_control=type_ctrl_id_exam, amount=14400, id_edizm=edizm_id)
        db.session.merge(ad1)
        ad2 = AupData(id=502, id_aup=101, id_discipline=1002, semester=1, zet=300, total_hours=10800, control_type='Зачет', id_block=block_id, shifr='Б1.O.02', id_part=part_id, id_module=module_id, id_group=group_id, id_type_record=type_rec_id, id_period=period_id, num_row=2, id_type_control=type_ctrl_id_zachet, amount=10800, id_edizm=edizm_id)
        db.session.merge(ad2)
        db.session.commit()
        print("  - AupData entries checked/merged.")

        print("Seeding Competencies...")
        # Используем merge, чтобы избежать ошибок при повторном запуске
        db.session.merge(Competency(id=1, competency_type_id=1, code='УК-1', fgos_vo_id=1, name='Способен осуществлять поиск...'))
        db.session.merge(Competency(id=2, competency_type_id=2, code='ОПК-1', fgos_vo_id=1, name='Способен применять ест. знания...'))
        db.session.merge(Competency(id=3, competency_type_id=3, code='ПК-1', name='Способен выполнять работы по созданию ИС...'))
        db.session.commit()
        print("  - Competencies checked/merged.")

        print("Seeding Indicators...")
        db.session.merge(Indicator(id=10, competency_id=1, code='ИУК-1.1', formulation='Анализирует задачу...', source_description='Распоряжение 505-Р'))
        db.session.merge(Indicator(id=11, competency_id=2, code='ИОПК-1.1', formulation='Знает основы высшей математики...', source_description='ФГОС ВО 09.03.01'))
        db.session.merge(Indicator(id=12, competency_id=3, code='ИПК-1.1', formulation='Знает: методологию...', source_description='ПС 06.015 / Опыт'))
        db.session.commit()
        print("  - Indicators checked/merged.")

        print("Seeding Competency Matrix link...")
        link = CompetencyMatrix(aup_data_id=501, indicator_id=11, is_manual=True)
        db.session.merge(link) # merge работает для составных ключей, если они определены как PK
        db.session.commit()
        print("  - Matrix link (501 <-> 11) checked/merged.")

        print("Database seeding finished successfully.")
    except Exception as e:
        db.session.rollback()
        print(f"ERROR during database seeding: {e}")
        # Добавим вывод traceback для детальной диагностики
        import traceback
        traceback.print_exc()


# Регистрируем команду сидера
app.cli.add_command(seed_command)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)