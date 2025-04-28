# filepath: /home/me/ВКР/maps_backend/cli_commands/db_unseed.py
import click
from flask.cli import with_appcontext
import traceback
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload # Import if needed for deletion logic

# --- Import all necessary models ---
# You need to import 'db' and all models used within the unseed_command function
from maps.models import (
    db, SprDiscipline, AupInfo, AupData, SprFaculty, Department,
    SprDegreeEducation, SprFormEducation, SprRop, NameOP, Groups, SprOKCO,
    D_Blocks, D_Part, D_TypeRecord, D_ControlType, D_EdIzmereniya, D_Period, SprBranch, D_Modules,
    Weeks, Revision # Added Weeks and Revision
)
# Import models and association tables from auth.models
from auth.models import Roles, Users, user_roles_table, users_faculty_table, permissions_table # Using the table variables instead of class names
from competencies_matrix.models import (
    CompetencyType, FgosVo, EducationalProgram, Competency, Indicator,
    CompetencyMatrix, EducationalProgramAup, EducationalProgramPs,
    ProfStandard, FgosRecommendedPs, IndicatorPsLink, LaborFunction,
    RequiredKnowledge, # Added import for completeness, though not used in current unseed logic
    LaborAction, RequiredSkill, GeneralizedLaborFunction # Added missing imports
)

# Import unification models from the correct module
from unification.models import (
    UnificationDiscipline, DisciplinePeriodAssoc, faculty_discipline_period_assoc as FacultyDisciplinePeriod,
    UnificationLoad, unification_okso_assoc as UnificationOksoAssoc
)

from cabinet.models import (
    StudyGroups, SprPlace, SprBells, DisciplineTable,
    GradeType, Topics, Students, Tutors, Grade, GradeColumn,
    TutorsOrder, TutorsOrderRow
)

# Assuming Mode model exists, potentially in a general config or base models file
# If it's elsewhere, adjust the import accordingly
# from some_module import Mode # Placeholder for Mode import

@click.command(name='unseed_db')
@with_appcontext
def unseed_command():
    """Удаляет из базы данных тестовые данные, добавленные командой seed_db (Идемпотентно)."""
    print("Starting database unseeding...")
    try:
        # === БЛОК 8: Cabinet Models (удаление зависимых от AUP) ===
        # Эти модели зависят от AupData, StudyGroups, Users, SprPlace, SprBells
        print("Unseeding Cabinet Models (dependent on AUP/Users/Lookups)...")

        # Удаляем записи, которые зависят от AupData или StudyGroup, не каскадируются напрямую от AupInfo/StudyGroup
        # GradeColumns и GradeTypes зависят от DisciplineTable, которая зависит от AupInfo/StudyGroup
        # Grades зависят от GradeColumn и Students
        # Students зависят от StudyGroup
        # Topics зависят от DisciplineTable и StudyGroup
        # TutorsOrderRow зависит от TutorsOrder, Department, StudyGroups
        # TutorsOrder зависит от Faculty, SprFormEducation

        # Удаляем все записи из этих таблиц, которые потенциально могут быть созданы сидом
        # или иметь FK на сущности, которые мы будем удалять дальше.
        # Полагаемся на CASCADE DELETE для многих связей DisciplineTable <-> Topics/Grades
        Grade.query.delete()
        db.session.commit()
        print("  - Deleted all Grade records.")

        GradeColumn.query.delete()
        db.session.commit()
        print("  - Deleted all GradeColumn records.")

        Topics.query.delete()
        db.session.commit()
        print("  - Deleted all Topic records.")

        GradeType.query.delete()
        db.session.commit()
        print("  - Deleted all GradeType records.")

        DisciplineTable.query.delete() # Зависит от AupInfo, StudyGroups, SprDiscipline
        db.session.commit()
        print("  - Deleted all DisciplineTable records.")

        # Удаляем записи в таблицах, которые связывают Cabinet с другими модулями
        TutorsOrderRow.query.delete() # Зависит от TutorsOrder, Department, StudyGroups, Tutors
        db.session.commit()
        print("  - Deleted all TutorsOrderRow records.")

        TutorsOrder.query.delete() # Зависит от Faculty, SprFormEducation, SprFormEducation
        db.session.commit()
        print("  - Deleted all TutorsOrder records.")

        Students.query.delete() # Зависит от StudyGroups
        db.session.commit()
        print("  - Deleted all Students records.")

        StudyGroups.query.delete() # Зависит от Tutors, AupInfo
        db.session.commit()
        print("  - Deleted all StudyGroups records.")

        Tutors.query.delete() # Зависит от Department
        db.session.commit()
        print("  - Deleted all Tutors records.")

        SprPlace.query.delete() # Не зависит от других seeded сущностей
        db.session.commit()
        print("  - Deleted all SprPlace records.")

        SprBells.query.delete() # Не зависит от других seeded сущностей
        db.session.commit()
        print("  - Deleted all SprBells records.")

        print("Cabinet models unseeded.")


        # === БЛОК 4: Компетенции и Индикаторы (удаление зависимых от AUP/ProfStandard/Lookups) ===
        print("Unseeding Competencies & Indicators (dependent on AUP/ProfStandard/Lookups)...")

        # Удаляем записи в таблицах, которые связывают Comp/Indicator с другими модулями/сущностями
        # CompetencyMatrix зависит от AupData и Indicator
        CompetencyMatrix.query.delete()
        db.session.commit()
        print("  - Deleted all CompetencyMatrix records.")

        # IndicatorPsLink зависит от Indicator и LaborFunction
        IndicatorPsLink.query.delete()
        db.session.commit()
        print("  - Deleted all IndicatorPsLink records.")

        # Удаляем записи в таблицах структуры профстандартов
        # Assuming LaborAction exists and is imported
        try:
            LaborAction.query.delete() # Зависит от LaborFunction
            db.session.commit()
            print("  - Deleted all LaborAction records.")
        except NameError:
            print("  - Skipping LaborAction deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting LaborAction: {e}")
            db.session.rollback()

        # Assuming RequiredSkill exists and is imported
        try:
            RequiredSkill.query.delete() # Зависит от LaborFunction
            db.session.commit()
            print("  - Deleted all RequiredSkill records.")
        except NameError:
            print("  - Skipping RequiredSkill deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting RequiredSkill: {e}")
            db.session.rollback()

        RequiredKnowledge.query.delete() # Зависит от LaborFunction
        db.session.commit()
        print("  - Deleted all RequiredKnowledge records.")

        LaborFunction.query.delete() # Зависит от GeneralizedLaborFunction
        db.session.commit()
        print("  - Deleted all LaborFunction records.")

        # Assuming GeneralizedLaborFunction exists and is imported
        try:
            GeneralizedLaborFunction.query.delete() # Зависит от ProfStandard
            db.session.commit()
            print("  - Deleted all GeneralizedLaborFunction records.")
        except NameError:
            print("  - Skipping GeneralizedLaborFunction deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting GeneralizedLaborFunction: {e}")
            db.session.rollback()


        # Удаляем записи в таблицах компетенций и индикаторов
        Indicator.query.delete() # Зависит от Competency
        db.session.commit()
        print("  - Deleted all Indicator records.")

        Competency.query.delete() # Зависит от CompetencyType, FgosVo, LaborFunction
        db.session.commit()
        print("  - Deleted all Competency records.")

        ProfStandard.query.delete() # Зависит от FgosRecommendedPs, EducationalProgramPs, GenLaborFunction
        db.session.commit()
        print("  - Deleted all ProfStandard records.")

        FgosRecommendedPs.query.delete() # Зависит от FgosVo, ProfStandard
        db.session.commit()
        print("  - Deleted all FgosRecommendedPs records.")

        EducationalProgramPs.query.delete() # Зависит от EducationalProgram, ProfStandard
        db.session.commit()
        print("  - Deleted all EducationalProgramPs records.")

        EducationalProgramAup.query.delete() # Зависит от EducationalProgram, AupInfo
        db.session.commit()
        print("  - Deleted all EducationalProgramAup records.")

        print("Competencies & Indicators unseeded.") # <-- Log after completion


        # === БЛОК 3: АУП и его структура ===
        print("Unseeding AUP and structure...")
        # Благодаря ON DELETE CASCADE на FK в tbl_aup, удаление AupInfo
        # должно каскадно удалить AupData, DisciplineTable, EducationalProgramAup, Weeks
        # Но мы уже удалили их явно выше, чтобы быть уверенными в порядке для всех зависимостей.

        # Удаляем записи AupInfo - это триггернет каскады на AupData, DisciplineTable и др.
        deleted_aup_count = AupInfo.query.delete(synchronize_session=False)
        db.session.commit()
        print(f"  - Deleted {deleted_aup_count} records from AupInfo table (cascading to AupData, DisciplineTable, etc.).")

        # Удаляем записи Weeks (если не сработало каскадом от AupInfo)
        Weeks.query.delete()
        db.session.commit()
        print("  - Deleted all Weeks records (redundant if cascade worked).")

        print("AUP and structure unseeded.") # <-- Log after completion


        # === БЛОК 2: ФГОС и Образовательные Программы ===
        print("Unseeding Educational Program and FGOS...")

        # Удаляем записи EducationalProgram
        EducationalProgram.query.delete() # Зависит от FgosVo, EducationalProgramAup, EducationalProgramPs
        db.session.commit()
        print("  - Deleted all EducationalProgram records.")

        # Удаляем записи FgosVo
        FgosVo.query.delete() # Зависит от EducationalProgram, Competency, FgosRecommendedPs
        db.session.commit()
        print("  - Deleted all FgosVo records.")

        print("FGOS and Educational Program unseeded.")


        # === БЛОК 1: Основные Справочники (Reverse Order) ===
        print("Unseeding Core Lookups...")

        # Удаляем записи в справочных таблицах
        # Удаление должно работать, т.к. все ссылающиеся на них таблицы (AupInfo, AupData, Competency, ...)
        # должны быть уже пусты или удалены выше.

        CompetencyType.query.delete() # Зависит от Competency
        db.session.commit()
        print("  - Deleted all CompetencyType records.")

        SprDegreeEducation.query.delete() # Зависит от AupInfo
        db.session.commit()
        print("  - Deleted all SprDegreeEducation records.")

        SprFormEducation.query.delete() # Зависит от AupInfo, TutorsOrder, UnificationLoad
        db.session.commit()
        print("  - Deleted all SprFormEducation records.")

        SprRop.query.delete() # Зависит от AupInfo
        db.session.commit()
        print("  - Deleted all SprRop records.")

        SprOKCO.query.delete() # Зависит от NameOP, SprVolumeDegreeZET, UnificationOksoAssoc
        db.session.commit()
        print("  - Deleted all SprOKCO records.")

        NameOP.query.delete() # Зависит от AupInfo
        db.session.commit()
        print("  - Deleted all NameOP records.")

        SprDiscipline.query.delete() # Зависит от AupData, DisciplineTable, GradeTable, UnificationDiscipline
        db.session.commit()
        print("  - Deleted all SprDiscipline records.")

        D_Blocks.query.delete() # Зависит от AupData
        db.session.commit()
        print("  - Deleted all D_Blocks records.")

        D_Part.query.delete() # Зависит от AupData
        db.session.commit()
        print("  - Deleted all D_Part records.")

        D_Modules.query.delete() # Зависит от AupData
        db.session.commit()
        print("  - Deleted all D_Modules records.")

        Groups.query.delete() # Зависит от AupData, StudyGroups
        db.session.commit()
        print("  - Deleted all Groups records.")

        D_Period.query.delete() # Зависит от AupData, Weeks, DisciplinePeriodAssoc
        db.session.commit()
        print("  - Deleted all D_Period records.")

        D_ControlType.query.delete() # Зависит от AupData, DisciplineTable, Topic, GradeColumn, GradeType, ControlTypeShortName, UnificationLoad
        db.session.commit()
        print("  - Deleted all D_ControlType records.")

        D_EdIzmereniya.query.delete() # Зависит от AupData, UnificationDiscipline
        db.session.commit()
        print("  - Deleted all D_EdIzmereniya records.")

        # Correct order: first delete SprFaculty, then SprBranch (because SprFaculty depends on SprBranch)
        SprFaculty.query.delete() # Зависит от AupInfo, Department, TutorsOrder, UsersFaculty
        db.session.commit()
        print("  - Deleted all SprFaculty records.")

        SprBranch.query.delete() # Зависит от SprFaculty
        db.session.commit()
        print("  - Deleted all SprBranch records.")

        Department.query.delete() # Зависит от AupInfo, Tutors, TutorsOrderRow, TutorsOrder, Users
        db.session.commit()
        print("  - Deleted all Department records.")


        # Удаление Users и Roles - должно быть в конце, т.к. на них много ссылок
        # Удаление ссылочных таблиц Users <-> Roles/Faculty (если не каскадом)
        # Delete records from user_roles_table (association table)
        try:
            db.session.execute(db.delete(user_roles_table))
            db.session.commit()
            print("  - Deleted all records from user_roles association table.")
        except Exception as e:
            print(f"  - Error deleting from user_roles table: {e}")
            db.session.rollback()

        # Delete records from users_faculty_table (association table)
        try:
            db.session.execute(db.delete(users_faculty_table))
            db.session.commit()
            print("  - Deleted all records from users_faculty association table.")
        except Exception as e:
            print(f"  - Error deleting from users_faculty table: {e}")
            db.session.rollback()


        Users.query.delete() # Зависит от Revision, TblToken, UserRoles, UsersFaculty, Students, Tutors
        db.session.commit()
        print("  - Deleted all Users records.")

        Roles.query.delete() # Зависит от UserRoles, Permissions
        db.session.commit()
        print("  - Deleted all Roles records.")

        # Удаление оставшихся таблиц, которые могут быть не связаны или связаны сложно
        # Assuming Mode exists and is imported
        try:
            Mode.query.delete()
            db.session.commit()
            print("  - Deleted all Mode records.")
        except NameError:
            print("  - Skipping Mode deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting Mode: {e}")
            db.session.rollback()

        # Delete records from permissions_table (association table)
        try:
            db.session.execute(db.delete(permissions_table))
            db.session.commit()
            print("  - Deleted all records from permissions association table.")
        except Exception as e:
            print(f"  - Error deleting from permissions table: {e}")
            db.session.rollback()


        Revision.query.delete()
        db.session.commit()
        print("  - Deleted all Revision records.")

        # TblToken каскадом от Users
        # TblToken.query.delete()
        # db.session.commit()
        # print("  - Deleted all TblToken records (redundant if cascade worked).")

        # Удаление Unification таблиц (если они не связаны с остальным деревом удаления)
        # Delete records from faculty_discipline_period_assoc (association table)
        try:
            db.session.execute(db.delete(FacultyDisciplinePeriod))
            db.session.commit()
            print("  - Deleted all records from faculty_discipline_period association table.")
        except Exception as e:
            print(f"  - Error deleting from faculty_discipline_period table: {e}")
            db.session.rollback()

        try:
            UnificationLoad.query.delete() # Зависит от DisciplinePeriodAssoc, SprFormEducation, D_ControlType
            db.session.commit()
            print("  - Deleted all UnificationLoad records.")
        except NameError:
            print("  - Skipping UnificationLoad deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting UnificationLoad: {e}")
            db.session.rollback()

        # Delete records from unification_okso_assoc (association table)
        try:
            db.session.execute(db.delete(UnificationOksoAssoc))
            db.session.commit()
            print("  - Deleted all records from unification_okso_assoc association table.")
        except Exception as e:
            print(f"  - Error deleting from unification_okso_assoc table: {e}")
            db.session.rollback()

        try:
            DisciplinePeriodAssoc.query.delete() # Зависит от UnificationDiscipline, D_Period
            db.session.commit()
            print("  - Deleted all DisciplinePeriodAssoc records.")
        except NameError:
            print("  - Skipping DisciplinePeriodAssoc deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting DisciplinePeriodAssoc: {e}")
            db.session.rollback()

        try:
            UnificationDiscipline.query.delete()
            db.session.commit()
            print("  - Deleted all UnificationDiscipline records.")
        except NameError:
            print("  - Skipping UnificationDiscipline deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting UnificationDiscipline: {e}")
            db.session.rollback()


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
