# filepath: cli_commands/db_seed.py
import click
from flask.cli import with_appcontext
import datetime
import traceback
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

from maps.models import (
    db, SprFaculty, Department, SprBranch, SprDegreeEducation, SprFormEducation,
    SprRop, SprOKCO, NameOP
)
from competencies_matrix.models import (
    CompetencyType, FgosVo, EducationalProgram, Competency, Indicator,
    EducationalProgramAup
)
from auth.models import Roles, Users, user_roles_table

def find_or_create(session: Session, model, defaults=None, **kwargs):
    """Находит объект по kwargs или создает новый с defaults."""
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        logger.debug(f"Found existing {model.__name__}: {kwargs}")
        if defaults:
             for key, value in defaults.items():
                  if hasattr(instance, key) and getattr(instance, key) != value:
                       setattr(instance, key, value)
        return instance, False
    else:
        valid_keys = {key for key in model.__table__.columns.keys()}
        valid_kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}
        valid_defaults = {k: v for k, v in (defaults or {}).items() if k in valid_keys}
        valid_kwargs.update(valid_defaults)

        instance = model(**valid_kwargs)
        try:
            session.add(instance)
            session.flush()
            logger.debug(f"Created new {model.__name__}: {valid_kwargs}")
            return instance, True
        except (IntegrityError, SQLAlchemyError) as e:
            session.rollback()
            logger.error(f"Error creating {model.__name__} with {valid_kwargs}: {e}. Trying to find again...")
            pk_keys = {c.key for c in model.__table__.primary_key.columns}
            unique_keys = {k for u in model.__table__.unique_constraints for k in u.columns.keys()}
            find_criteria = {k: v for k, v in valid_kwargs.items() if k in pk_keys or k in unique_keys}
            instance = session.query(model).filter_by(**find_criteria).first()

            if instance:
                   logger.warning(f"Found {model.__name__} on second attempt after error: {find_criteria}")
                   return instance, False
            else:
                   logger.error(f"Could not find or create {model.__name__} after error: {find_criteria}")
                   raise e

def link_if_not_exists(session: Session, association_model, defaults=None, **kwargs):
    """Создает связь в ассоциативной таблице, если ее еще нет."""
    exists = session.query(association_model).filter_by(**kwargs).first()
    if not exists:
        kwargs.update(defaults or {})
        link = association_model(**kwargs)
        session.add(link)
        logger.debug(f"Created link in {association_model.__tablename__}: {kwargs}")
        return True
    else:
        logger.debug(f"Link already exists in {association_model.__tablename__}: {kwargs}")
        return False

@click.command(name='seed_db')
@with_appcontext
def seed_command():
    """Заполняет БД данными для MVP (Фокус UI + КД)."""
    logger.info("Starting database seeding (MVP: UI Focus + KD Integration)...")
    session: Session = db.session
    try:
        logger.info("Seeding Core Lookups...")
        comp_type_uk, _ = find_or_create(session, CompetencyType, id=1, defaults={'code':'УК', 'name':'Универсальная'})
        comp_type_opk, _ = find_or_create(session, CompetencyType, id=2, defaults={'code':'ОПК', 'name':'Общепрофессиональная'})
        comp_type_pk, _ = find_or_create(session, CompetencyType, id=3, defaults={'code':'ПК', 'name':'Профессиональная'})
        role_admin, _ = find_or_create(session, Roles, id_role=1, defaults={'name_role':'admin'})
        role_methodologist, _ = find_or_create(session, Roles, id_role=2, defaults={'name_role':'methodologist'})
        role_teacher, _ = find_or_create(session, Roles, id_role=3, defaults={'name_role':'teacher'})
        role_tutor, _ = find_or_create(session, Roles, id_role=4, defaults={'name_role':'tutor'})
        role_student, _ = find_or_create(session, Roles, id_role=5, defaults={'name_role':'student'})

        branch_main, _ = find_or_create(session, SprBranch, id_branch=1, defaults={'city':'Москва', 'location':'Основное подразделение'})
        degree_bach, _ = find_or_create(session, SprDegreeEducation, id_degree=1, defaults={'name_deg':"Высшее образование - бакалавриат"})
        form_och, _ = find_or_create(session, SprFormEducation, id_form=1, defaults={'form':"Очная"})
        faculty_inf, _ = find_or_create(session, SprFaculty, id_faculty=1, defaults={'name_faculty':'Факультет информатики', 'id_branch': branch_main.id_branch})
        dept_web, _ = find_or_create(session, Department, id_department=1, defaults={'name_department':'Кафедра веб-технологий'})
        nameop_web, _ = find_or_create(session, NameOP, program_code='09.03.01', num_profile='01', defaults={'id_spec': 1, 'name_spec':'Веб-технологии'})

        session.commit()
        logger.info("Core lookups seeded.")

        logger.info("Seeding Example FGOS...")
        fgos_090301, _ = find_or_create(session, FgosVo,
            number='929', date=datetime.date(2017, 9, 19), direction_code='09.03.01', education_level='бакалавриат',
            defaults={'id': 1, 'direction_name':'Информатика и вычислительная техника', 'generation':'3++'}
        )
        logger.info("Seeding Example Educational Program...")
        program_web, _ = find_or_create(session, EducationalProgram,
            code='09.03.01', profile='Веб-технологии', enrollment_year=2024, form_of_education='очная',
            defaults={'id': 1, 'fgos_vo_id': fgos_090301.id, 'title':'Веб-технологии (09.03.01)', 'qualification':'Бакалавр'}
        )
        session.commit()
        logger.info("Example FGOS & Educational Program seeded.")

        logger.info("Seeding Example AupInfo (for linking EP to AUP number)...")
        aup101_example, _ = find_or_create(session, AupInfo,
            num_aup='B093011451',
            defaults={'id_aup': 101, 'id_faculty': faculty_inf.id_faculty, 'id_degree': degree_bach.id_degree,
                      'id_form': form_och.id_form, 'id_spec': nameop_web.id_spec, 'year_beg':2024, 'is_actual':1}
        )
        logger.info("Seeding AUP-Program Link...")
        link_if_not_exists(session, EducationalProgramAup,
                           educational_program_id=program_web.id,
                           aup_id=aup101_example.id_aup,
                           defaults={'is_primary':True})
        session.commit()
        logger.info("Example AupInfo and Link seeded.")

        logger.info("Seeding Competencies & Indicators (Local Data)...")
        comp_uk1, _ = find_or_create(session, Competency, code='УК-1', fgos_vo_id=fgos_090301.id,
            defaults={'id': 1, 'competency_type_id':comp_type_uk.id, 'name':'Способен осуществлять поиск, критический анализ и синтез информации...'})
        comp_uk5, _ = find_or_create(session, Competency, code='УК-5', fgos_vo_id=fgos_090301.id,
            defaults={'id': 5, 'competency_type_id':comp_type_uk.id, 'name':'Способен воспринимать межкультурное разнообразие общества...'})
        comp_opk7, _ = find_or_create(session, Competency, code='ОПК-7', fgos_vo_id=fgos_090301.id,
            defaults={'id': 107, 'competency_type_id':comp_type_opk.id, 'name':'Способен участвовать в настройке и наладке программно-аппаратных комплексов'})
        comp_pk1, _ = find_or_create(session, Competency, code='ПК-1', competency_type_id=comp_type_pk.id,
            defaults={'id': 201, 'fgos_vo_id':None, 'name':'Способен выполнять работы по созданию (модификации) и сопровождению ИС...'})
        comp_pk2, _ = find_or_create(session, Competency, code='ПК-2', competency_type_id=comp_type_pk.id,
            defaults={'id': 202, 'fgos_vo_id':None, 'name':'Способен осуществлять управление проектами в области ИТ...'})

        ind_1_1, _ = find_or_create(session, Indicator, code='ИУК-1.1', competency_id=comp_uk1.id, defaults={'id': 10, 'formulation':'Анализирует задачу, выделяя ее базовые составляющие', 'source':'Распоряжение 505-Р'})
        ind_1_2, _ = find_or_create(session, Indicator, code='ИУК-1.2', competency_id=comp_uk1.id, defaults={'id': 11, 'formulation':'Осуществляет поиск, критически оценивает...', 'source':'Распоряжение 505-Р'})
        ind_1_3, _ = find_or_create(session, Indicator, code='ИУК-1.3', competency_id=comp_uk1.id, defaults={'id': 12, 'formulation':'Рассматривает и предлагает рациональные варианты...', 'source':'Распоряжение 505-Р'})
        ind_5_1, _ = find_or_create(session, Indicator, code='ИУК-5.1', competency_id=comp_uk5.id, defaults={'id': 50, 'formulation':'Анализирует и интерпретирует события...', 'source':'Распоряжение 505-Р'})
        ind_7_1, _ = find_or_create(session, Indicator, code='ИОПК-7.1', competency_id=comp_opk7.id, defaults={'id': 170, 'formulation':'Знает основные языки программирования...', 'source':'ОП Веб-технологии'})
        ind_pk1_1, _ = find_or_create(session, Indicator, code='ИПК-1.1', competency_id=comp_pk1.id, defaults={'id': 210, 'formulation':'Знает: методологию и технологии проектирования...', 'source':'ОП Веб-технологии / ПС 06.015'})
        ind_pk1_2, _ = find_or_create(session, Indicator, code='ИПК-1.2', competency_id=comp_pk1.id, defaults={'id': 211, 'formulation':'Умеет: создавать, модифицировать и сопровождать ИС...', 'source':'ОП Веб-технологии / ПС 06.015'})
        ind_pk2_1, _ = find_or_create(session, Indicator, code='ИПК-2.1', competency_id=comp_pk2.id, defaults={'id': 220, 'formulation':'Знает: принципы и методологии управления проектами...', 'source':'ОП Веб-технологии / ПС 06.016'})

        session.commit()
        logger.info("Competencies & Indicators seeded.")

        logger.info("Skipping Competency Matrix links seeding (will be created manually via UI for MVP).")

        logger.info("Seeding Test Users...")
        # For production, remove or comment out default user creation for security.
        # Users should be created through a secure registration process or admin interface.
        # test_user, _ = find_or_create(session, Users, login='testuser',
        #     defaults={'password_hash': generate_password_hash('password', method='pbkdf2:sha256'),
        #               'name': 'Тестовый Методист', 'email': 'testuser@example.com',
        #               'approved_lk': True, 'id_department': dept_web.id_department}
        # )
        # if role_methodologist and test_user and role_methodologist not in test_user.roles:
        #     test_user.roles.append(role_methodologist)
        #     logger.debug(f"Linking testuser ({test_user.id_user}) with role {role_methodologist.name_role}")

        # admin_user, _ = find_or_create(session, Users, login='admin',
        #     defaults={'password_hash': generate_password_hash('admin', method='pbkdf2:sha256'),
        #               'name': 'Admin User', 'email': 'admin@example.com',
        #               'approved_lk': True, 'id_department': dept_web.id_department}
        # )
        # if role_admin and admin_user and role_admin not in admin_user.roles:
        #     admin_user.roles.append(role_admin)
        #     logger.debug(f"Linking admin ({admin_user.id_user}) with role {role_admin.name_role}")

        session.commit()
        logger.info("Test users seeded.")

        logger.info("Skipping seeding for 'cabinet' models (not required for competencies MVP).")

        logger.info("Database seeding finished successfully.")

    except (IntegrityError, SQLAlchemyError) as e:
        session.rollback()
        logger.error(f"DATABASE ERROR during seeding: {e}", exc_info=True)
        logger.error("Seeding stopped. Check constraints and data.")
    except Exception as e:
        session.rollback()
        logger.error(f"UNEXPECTED ERROR during seeding: {e}", exc_info=True)