# filepath: /home/me/ВКР/maps_backend/cli_commands/db_unseed.py
import click
from flask.cli import with_appcontext
import traceback
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload 

from maps.models import (
    db, SprDiscipline, AupInfo, AupData, SprFaculty, Department,
    SprDegreeEducation, SprFormEducation, SprRop, NameOP, Groups, SprOKCO,
    D_Blocks, D_Part, D_TypeRecord, D_ControlType, D_EdIzmereniya, D_Period, SprBranch, D_Modules,
    Weeks, Revision 
)
from auth.models import Roles, Users, user_roles_table, users_faculty_table, permissions_table 
from competencies_matrix.models import (
    CompetencyType, FgosVo, EducationalProgram, Competency, Indicator,
    CompetencyMatrix, EducationalProgramAup, EducationalProgramPs,
    ProfStandard, FgosRecommendedPs, IndicatorPsLink, LaborFunction,
    RequiredKnowledge, 
    LaborAction, RequiredSkill, GeneralizedLaborFunction 
)

from unification.models import (
    UnificationDiscipline, DisciplinePeriodAssoc, faculty_discipline_period_assoc as FacultyDisciplinePeriod,
    UnificationLoad, unification_okso_assoc as UnificationOksoAssoc
)

from cabinet.models import (
    StudyGroups, SprPlace, SprBells, DisciplineTable,
    GradeType, Topics, Students, Tutors, Grade, GradeColumn,
    TutorsOrder, TutorsOrderRow
)

# Assuming Mode model exists in maps.models or other general config/base models file
# from maps.models import Mode 

@click.command(name='unseed_db')
@with_appcontext
def unseed_command():
    """Удаляет из базы данных тестовые данные, добавленные командой seed_db (Идемпотентно)."""
    print("Starting database unseeding...")
    try:
        print("Unseeding Cabinet Models...")
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

        DisciplineTable.query.delete() 
        db.session.commit()
        print("  - Deleted all DisciplineTable records.")

        TutorsOrderRow.query.delete() 
        db.session.commit()
        print("  - Deleted all TutorsOrderRow records.")

        TutorsOrder.query.delete() 
        db.session.commit()
        print("  - Deleted all TutorsOrder records.")

        Students.query.delete() 
        db.session.commit()
        print("  - Deleted all Students records.")

        StudyGroups.query.delete() 
        db.session.commit()
        print("  - Deleted all StudyGroups records.")

        Tutors.query.delete() 
        db.session.commit()
        print("  - Deleted all Tutors records.")

        SprPlace.query.delete() 
        db.session.commit()
        print("  - Deleted all SprPlace records.")

        SprBells.query.delete() 
        db.session.commit()
        print("  - Deleted all SprBells records.")

        print("Cabinet models unseeded.")

        print("Unseeding Competencies & Indicators...")

        CompetencyMatrix.query.delete()
        db.session.commit()
        print("  - Deleted all CompetencyMatrix records.")

        IndicatorPsLink.query.delete()
        db.session.commit()
        print("  - Deleted all IndicatorPsLink records.")

        try:
            LaborAction.query.delete() 
            db.session.commit()
            print("  - Deleted all LaborAction records.")
        except NameError:
            print("  - Skipping LaborAction deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting LaborAction: {e}")
            db.session.rollback()

        try:
            RequiredSkill.query.delete() 
            db.session.commit()
            print("  - Deleted all RequiredSkill records.")
        except NameError:
            print("  - Skipping RequiredSkill deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting RequiredSkill: {e}")
            db.session.rollback()

        RequiredKnowledge.query.delete() 
        db.session.commit()
        print("  - Deleted all RequiredKnowledge records.")

        LaborFunction.query.delete() 
        db.session.commit()
        print("  - Deleted all LaborFunction records.")

        try:
            GeneralizedLaborFunction.query.delete() 
            db.session.commit()
            print("  - Deleted all GeneralizedLaborFunction records.")
        except NameError:
            print("  - Skipping GeneralizedLaborFunction deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting GeneralizedLaborFunction: {e}")
            db.session.rollback()

        Indicator.query.delete() 
        db.session.commit()
        print("  - Deleted all Indicator records.")

        Competency.query.delete() 
        db.session.commit()
        print("  - Deleted all Competency records.")

        ProfStandard.query.delete() 
        db.session.commit()
        print("  - Deleted all ProfStandard records.")

        FgosRecommendedPs.query.delete() 
        db.session.commit()
        print("  - Deleted all FgosRecommendedPs records.")

        EducationalProgramPs.query.delete() 
        db.session.commit()
        print("  - Deleted all EducationalProgramPs records.")

        EducationalProgramAup.query.delete() 
        db.session.commit()
        print("  - Deleted all EducationalProgramAup records.")

        print("Competencies & Indicators unseeded.") 

        print("Unseeding AUP and structure...")

        deleted_aup_count = AupInfo.query.delete(synchronize_session=False)
        db.session.commit()
        print(f"  - Deleted {deleted_aup_count} records from AupInfo table (cascading to AupData, DisciplineTable, etc.).")

        Weeks.query.delete()
        db.session.commit()
        print("  - Deleted all Weeks records (redundant if cascade worked).")

        print("AUP and structure unseeded.") 

        print("Unseeding Educational Program and FGOS...")

        EducationalProgram.query.delete() 
        db.session.commit()
        print("  - Deleted all EducationalProgram records.")

        FgosVo.query.delete() 
        db.session.commit()
        print("  - Deleted all FgosVo records.")

        print("FGOS and Educational Program unseeded.")

        print("Unseeding Core Lookups...")

        CompetencyType.query.delete() 
        db.session.commit()
        print("  - Deleted all CompetencyType records.")

        SprDegreeEducation.query.delete() 
        db.session.commit()
        print("  - Deleted all SprDegreeEducation records.")

        SprFormEducation.query.delete() 
        db.session.commit()
        print("  - Deleted all SprFormEducation records.")

        SprRop.query.delete() 
        db.session.commit()
        print("  - Deleted all SprRop records.")

        SprOKCO.query.delete() 
        db.session.commit()
        print("  - Deleted all SprOKCO records.")

        NameOP.query.delete() 
        db.session.commit()
        print("  - Deleted all NameOP records.")

        SprDiscipline.query.delete() 
        db.session.commit()
        print("  - Deleted all SprDiscipline records.")

        D_Blocks.query.delete() 
        db.session.commit()
        print("  - Deleted all D_Blocks records.")

        D_Part.query.delete() 
        db.session.commit()
        print("  - Deleted all D_Part records.")

        D_Modules.query.delete() 
        db.session.commit()
        print("  - Deleted all D_Modules records.")

        Groups.query.delete() 
        db.session.commit()
        print("  - Deleted all Groups records.")

        D_Period.query.delete() 
        db.session.commit()
        print("  - Deleted all D_Period records.")

        D_ControlType.query.delete() 
        db.session.commit()
        print("  - Deleted all D_ControlType records.")

        D_EdIzmereniya.query.delete() 
        db.session.commit()
        print("  - Deleted all D_EdIzmereniya records.")

        SprFaculty.query.delete() 
        db.session.commit()
        print("  - Deleted all SprFaculty records.")

        SprBranch.query.delete() 
        db.session.commit()
        print("  - Deleted all SprBranch records.")

        Department.query.delete() 
        db.session.commit()
        print("  - Deleted all Department records.")

        try:
            db.session.execute(db.delete(user_roles_table))
            db.session.commit()
            print("  - Deleted all records from user_roles association table.")
        except Exception as e:
            print(f"  - Error deleting from user_roles table: {e}")
            db.session.rollback()

        try:
            db.session.execute(db.delete(users_faculty_table))
            db.session.commit()
            print("  - Deleted all records from users_faculty association table.")
        except Exception as e:
            print(f"  - Error deleting from users_faculty table: {e}")
            db.session.rollback()

        Users.query.delete() 
        db.session.commit()
        print("  - Deleted all Users records.")

        Roles.query.delete() 
        db.session.commit()
        print("  - Deleted all Roles records.")

        try:
            Mode.query.delete()
            db.session.commit()
            print("  - Deleted all Mode records.")
        except NameError:
            print("  - Skipping Mode deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting Mode: {e}")
            db.session.rollback()

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

        try:
            db.session.execute(db.delete(FacultyDisciplinePeriod))
            db.session.commit()
            print("  - Deleted all records from faculty_discipline_period association table.")
        except Exception as e:
            print(f"  - Error deleting from faculty_discipline_period table: {e}")
            db.session.rollback()

        try:
            UnificationLoad.query.delete() 
            db.session.commit()
            print("  - Deleted all UnificationLoad records.")
        except NameError:
            print("  - Skipping UnificationLoad deletion (Model not found/imported).")
        except Exception as e:
            print(f"  - Error deleting UnificationLoad: {e}")
            db.session.rollback()

        try:
            db.session.execute(db.delete(UnificationOksoAssoc))
            db.session.commit()
            print("  - Deleted all records from unification_okso_assoc association table.")
        except Exception as e:
            print(f"  - Error deleting from unification_okso_assoc table: {e}")
            db.session.rollback()

        try:
            DisciplinePeriodAssoc.query.delete() 
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

    except (IntegrityError, SQLAlchemyError) as e: 
        db.session.rollback()
        print(f"\n!!! DATABASE ERROR during unseeding: {e} !!!")
        print("!!! Unseeding stopped. Check foreign key constraints and data order. !!!")
        traceback.print_exc()
    except Exception as e: 
        db.session.rollback()
        print(f"\n!!! UNEXPECTED ERROR during unseeding: {e} !!!")
        traceback.print_exc()