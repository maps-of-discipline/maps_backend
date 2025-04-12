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