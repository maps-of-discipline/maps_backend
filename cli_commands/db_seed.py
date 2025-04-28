# filepath: /home/me/ВКР/maps_backend/cli_commands/db_seed.py
import click
from flask.cli import with_appcontext
import datetime
import traceback
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import random

# --- Import all necessary models ---
# You need to import 'db' and all models used within the seed_command function
from maps.models import (
    db, SprDiscipline, AupInfo, AupData, SprFaculty, Department,
    SprDegreeEducation, SprFormEducation, SprRop, NameOP, Groups, SprOKCO,
    D_Blocks, D_Part, D_TypeRecord, D_ControlType, D_EdIzmereniya, D_Period, SprBranch, D_Modules
)
from auth.models import Roles, Users
from competencies_matrix.models import (
    CompetencyType, FgosVo, EducationalProgram, Competency, Indicator,
    CompetencyMatrix, EducationalProgramAup, EducationalProgramPs,
    ProfStandard, FgosRecommendedPs, IndicatorPsLink, LaborFunction
)
from cabinet.models import (
    StudyGroups, SprPlace, SprBells, DisciplineTable,
    GradeType, Topics, Students, Tutors, Grade, GradeColumn,
    TutorsOrder, TutorsOrderRow
)

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
        department_1 = db.session.merge(Department(id_department=1, name_department='Кафедра веб-технологий'))
        db.session.commit()  # Коммитим факультет и кафедру

        # Справочники для AupData (ID как в сидере)
        db.session.merge(D_Blocks(id=1, title="Блок 1. Дисциплины (модули)"))
        db.session.merge(D_Part(id=1, title="Обязательная часть"))
        db.session.merge(D_Modules(id=1, title="Базовый модуль", color="#FFFFFF")) # Добавлен цвет
        db.session.merge(Groups(id_group=1, name_group="Основные", color="#FFFFFF", weight=1)) # Имя поля уточнено
        db.session.merge(D_TypeRecord(id=1, title="Дисциплина"))
        db.session.merge(D_ControlType(id=1, title="Экзамен", default_shortname="Экз"))
        db.session.merge(D_ControlType(id=5, title="Зачет", default_shortname="Зач"))
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
        # merge вернет объекты AupData - используем _discipline для имени колонки
        ad501 = db.session.merge(AupData(
            id=501, id_aup=101, id_discipline=1001, _discipline='Основы программирования',
            id_block=1, shifr='Б1.1.07', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=1, num_row=7, id_type_control=1,
            amount=14400, id_edizm=1, zet=4
        ))
        ad502 = db.session.merge(AupData(
            id=502, id_aup=101, id_discipline=1002, _discipline='Базы данных',
            id_block=1, shifr='Б1.1.10', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=1, num_row=10, id_type_control=5,
            amount=10800, id_edizm=1, zet=3
        ))
        ad503 = db.session.merge(AupData(
            id=503, id_aup=101, id_discipline=1003, _discipline='История России',
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