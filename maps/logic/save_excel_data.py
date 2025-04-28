import datetime
from typing import Dict, Any, List

import pandas
from pandas import DataFrame
from sqlalchemy.exc import SQLAlchemyError, IntegrityError # Добавим IntegrityError
from sqlalchemy import exists
import traceback

from maps.logic.excel_check import ExcelValidator
from maps.logic.read_excel import read_excel
from maps.logic.tools import timeit
from utils.logging import logger

from maps.models import (
    db, # Убедитесь, что db импортируется
    D_Blocks,
    D_ControlType,
    D_EdIzmereniya,
    D_Modules,
    D_Part,
    D_Period,
    D_TypeRecord,
    SprDegreeEducation,
    SprDiscipline,
    SprFaculty,
    SprFormEducation,
    SprOKCO,
    AupData,
    AupInfo,
    Groups,
    Department,
    NameOP,
    SprRop, # Added SprRop
    SprBranch, # Added SprBranch
    Weeks, # Added Weeks
    # ... другие модели maps ...
)

# --- Импорт моделей из модуля competencies_matrix ---
# Убедитесь, что все необходимые модели импортированы
from competencies_matrix.models import (
    EducationalProgram, EducationalProgramAup, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramPs,
    CompetencyType, Indicator, IndicatorPsLink, GeneralizedLaborFunction,
    LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
)
# --- Импорт моделей из модуля cabinet ---
# Убедитесь, что все необходимые модели импортированы
from cabinet.models import (
    DisciplineTable, StudyGroups, SprPlace, SprBells,
    GradeType, Topics, Students, Tutors, Grade, GradeColumn,
    TutorsOrder, TutorsOrderRow
)
# ... другие импорты ...


@timeit
def save_excel_files(files, options):
    files = files.getlist("file")
    logger.info(f"Processing {len(files)} files...")
    all_files_check_result = []
    for file in files:
        logger.info(f"Processing file: {file.filename}")
        try:
            header, data = read_excel(file)
        except Exception as e:
            res = {
                "aup": "-",
                "filename": file.filename,
                "errors": [{"message": f"Некорректная структура выгрузки: {e}"}], # Include exception message
            }
            all_files_check_result.append(res)
            logger.warning(f"Structure error in excel file '{file.filename}': {res['errors']}")
            continue

        aup = header["Содержание"][0]

        res = {
            "aup": aup if not pandas.isna(aup) else "-",
            "filename": file.filename,
            "errors": ExcelValidator.validate(options, header, data),
        }
        all_files_check_result.append(res)

        if res["errors"]:
            logger.warning(f"Validation errors in file '{file.filename}': {res['errors']}")
            continue
        else:
             logger.info(f"Excel file '{file.filename}' is valid. Starting database transaction.")

        # --- Вызов save_excel_data в рамках транзакции ---
        try:
            # Используем db.session напрямую
            save_excel_data(
                file.filename,
                header,
                data,
                use_other_modules=options.get("checkboxFillNullModulesModel", False),
                session=db.session # Передаем сессию
            )
            db.session.commit() # Финальный коммит здесь
            logger.info(f"Successfully processed and saved data for {file.filename}.")
        except Exception as e:
            # db.session.rollback() # Rollback happens in save_excel_data or implicitly
            logger.error(f"Import failed for {file.filename} after validation: {e}")
            # Добавляем сообщение об ошибке к результату для этого файла
            res["errors"].append({"message": f"Ошибка при сохранении данных: {e}"})
            # Не прерываем цикл, обрабатываем следующий файл
            continue # Переходим к следующему файлу

    logger.debug("All AUPs have been processed")
    return all_files_check_result


def _delete_aup_dependencies(aup_id: int, session: db.Session) -> None:
    """
    Удаляет все данные, зависящие от AUP, КРОМЕ САМОГО AupInfo.
    Используется перед удалением или заменой AUP.
    Полагается на CASCADE DELETE для многих связей,
    но некоторые ассоциативные таблицы удаляем явно.

    Args:
        aup_id: ID Академического учебного плана.
        session: Сессия базы данных.
    """
    logger.debug(f"Deleting dependencies for AUP ID: {aup_id}")

    # 1. Удаление связей в матрице компетенций
    # Находим ID AupData, связанных с этим AUP
    aup_data_ids = [ad.id for ad in session.query(AupData.id).filter_by(id_aup=aup_id).all()]
    if aup_data_ids:
        # Удаляем записи в CompetencyMatrix
        deleted_matrix_count = session.query(CompetencyMatrix).filter(CompetencyMatrix.aup_data_id.in_(aup_data_ids)).delete(synchronize_session='fetch')
        logger.debug(f"   - Deleted {deleted_matrix_count} entries in CompetencyMatrix.")

    # 2. Удаление связей AUP с Образовательными Программами
    deleted_ep_aup_count = session.query(EducationalProgramAup).filter_by(aup_id=aup_id).delete(synchronize_session='fetch')
    logger.debug(f"   - Deleted {deleted_ep_aup_count} entries in EducationalProgramAup.")

    # 3. Удаление таблиц DisciplineTable (модуль cabinet)
    # CASCADE удаление должно сработать для зависимых таблиц кабинета
    deleted_dt_count = session.query(DisciplineTable).filter_by(id_aup=aup_id).delete(synchronize_session='fetch')
    logger.debug(f"   - Deleted {deleted_dt_count} entries in DisciplineTable (cascades to Cabinet grades/topics).")

    # 4. Удаление AupData записей
    # Явное удаление здесь гарантирует порядок
    deleted_ad_count = session.query(AupData).filter_by(id_aup=aup_id).delete(synchronize_session='fetch')
    logger.debug(f"   - Deleted {deleted_ad_count} entries in AupData.")

    # 5. Удаление записей из таблицы Weeks (если используется)
    # Check if Weeks model exists before querying
    if 'Weeks' in globals():
        deleted_weeks_count = session.query(Weeks).filter_by(aup_id=aup_id).delete(synchronize_session='fetch')
        logger.debug(f"   - Deleted {deleted_weeks_count} entries in Weeks.")
    else:
        logger.debug("   - Weeks model not found, skipping deletion.")


    logger.debug(f"Deletion of dependencies for AUP ID {aup_id} completed.")


def delete_aup_by_num(aup_num: str, session: db.Session) -> bool:
    """
    Централизованная функция для удаления AUP по его номеру, включая все зависимые данные.

    Args:
        aup_num: Номер АУП (например, '000020763').
        session: Сессия базы данных.

    Returns:
        bool: True, если AUP найден и удален, False, если не найден.
    """
    logger.info(f"Attempting to delete AUP with number: {aup_num}")
    aup_info = session.query(AupInfo).filter_by(num_aup=aup_num).first()

    if not aup_info:
        logger.warning(f"AUP with number {aup_num} not found for deletion.")
        return False

    try:
        aup_id = aup_info.id_aup

        # 1. Удаляем зависимые данные
        _delete_aup_dependencies(aup_id, session)

        # 2. Удаляем сам AupInfo
        session.delete(aup_info)

        # 3. Коммит происходит в вызывающей функции (CLI/API)
        logger.info(f"Successfully marked AUP with number: {aup_num} (ID: {aup_id}) and its dependencies for deletion.")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting AUP with number {aup_num}: {e}")
        traceback.print_exc()
        raise e # Перебрасываем исключение для обработки вызывающей стороной


@timeit
def save_excel_data(
    filename, header: DataFrame, data: DataFrame, use_other_modules: bool = True, session: db.Session = db.session
):
    """
    Сохраняет данные одного Excel файла АУП в базу данных.
    (Версия с исправленной логикой создания Department)
    """
    logger.debug(f"Saving excel file: {filename}")
    # Используем .iloc[0] для получения первой строки как Series, затем to_dict()
    header_dict = header.set_index("Наименование")["Содержание"].to_dict()
    aup_num = header_dict.get("Номер АУП")
    if not aup_num:
         raise ValueError("Номер АУП не найден в заголовке Excel.")

    # Проверка и удаление существующего AUP - ОСТАВЛЯЕМ как есть
    existing_aup = session.query(AupInfo).filter_by(num_aup=aup_num).first()
    if existing_aup:
        logger.warning(f"AUP {aup_num} still exists. Deleting dependencies before re-importing.")
        _delete_aup_dependencies(existing_aup.id_aup, session)
        session.delete(existing_aup)
        session.flush() # Ensure deletion is processed before adding new one

    try:
        # --- Создание/поиск связанных сущностей ПЕРЕД созданием AupInfo ---

        # 1. NameOP (Профиль/Специализация)
        name_op_instance = create_name_op(header_dict, session=session)
        if name_op_instance not in session.new and name_op_instance not in session.dirty:
             # Если объект уже существует и не изменен, мержим его с сессией,
             # чтобы избежать detached instance error при использовании в AupInfo
             name_op_instance = session.merge(name_op_instance, load=True)
        elif name_op_instance not in session:
            # Только что созданный объект добавляем в сессию
            session.add(name_op_instance)
            session.flush() # Получаем id_spec

        # 2. Faculty (Факультет)
        faculty_name = header_dict.get("Факультет")
        faculty_instance = session.query(SprFaculty).filter_by(name_faculty=faculty_name).first()
        if not faculty_instance and faculty_name:
            logger.debug(f"   - Creating new Faculty: {faculty_name}")
            faculty_instance = SprFaculty(name_faculty=faculty_name, id_branch=1) # Assuming default branch ID 1
            session.add(faculty_instance)
            session.flush() # Получаем id_faculty
        elif faculty_instance and faculty_instance not in session:
             faculty_instance = session.merge(faculty_instance, load=True)


        # 3. Department (Кафедра)
        department_name = header_dict.get("Выпускающая кафедра")
        department_instance = None # Инициализируем
        if department_name: # Только если название кафедры указано
            department_instance = session.query(Department).filter_by(name_department=department_name).first()
            if not department_instance:
                logger.debug(f"   - Creating new Department: {department_name}")
                # !!! ИСПРАВЛЕНО: Создаем Department БЕЗ передачи faculty !!!
                department_instance = Department(name_department=department_name)
                session.add(department_instance)
                try:
                    session.flush() # Получаем id_department
                    logger.debug(f"     - Department '{department_name}' created with ID {department_instance.id_department}.")
                except IntegrityError as ie:
                    logger.error(f"     - Integrity error while flushing new department '{department_name}': {ie}")
                    session.rollback()
                    department_instance = session.query(Department).filter_by(name_department=department_name).first()
                    if not department_instance:
                         raise ValueError(f"Could not create or find department: {department_name}") from ie
                except Exception as e:
                    logger.error(f"     - Error flushing new department '{department_name}': {e}")
                    session.rollback()
                    raise e
            elif department_instance not in session:
                 department_instance = session.merge(department_instance, load=True)

        # 4. Degree (Уровень образования)
        degree_name = header_dict.get("Уровень образования")
        degree_instance = session.query(SprDegreeEducation).filter_by(name_deg=degree_name).first()
        if not degree_instance and degree_name:
            degree_instance = SprDegreeEducation(name_deg=degree_name)
            session.add(degree_instance)
            session.flush() # Получаем id_degree
        elif degree_instance and degree_instance not in session:
            degree_instance = session.merge(degree_instance, load=True)


        # 5. Form (Форма обучения)
        form_name = header_dict.get("Форма обучения")
        form_instance = session.query(SprFormEducation).filter_by(form=form_name).first()
        if not form_instance and form_name:
            form_instance = SprFormEducation(form=form_name)
            session.add(form_instance)
            session.flush() # Получаем id_form
        elif form_instance and form_instance not in session:
             form_instance = session.merge(form_instance, load=True)

        # 6. ROP (Руководитель ОП)
        # Пока используем дефолтный ID 1
        rop_instance = session.query(SprRop).get(1)
        if not rop_instance:
             logger.warning("   - Default ROP with ID 1 not found. Creating default.")
             # TODO: Создать дефолтный ROP
             rop_instance = SprRop(id_rop=1, last_name='Дефолтный', first_name='РОП', middle_name='', email='rop@example.com', telephone='')
             session.add(rop_instance)
             session.flush() # Получаем id_rop
        elif rop_instance not in session:
             rop_instance = session.merge(rop_instance, load=True)

        # --- Создание AupInfo с использованием найденных/созданных ID ---
        years, months = get_education_duration(header_dict.get("Фактический срок обучения"))
        period_educ = header_dict.get("Период обучения")
        period_parts = period_educ.split(" - ") if period_educ else [None, None]
        year_beg_str = period_parts[0]
        year_end_str = period_parts[1]

        year_beg = int(year_beg_str) if year_beg_str and year_beg_str.isdigit() else None
        year_end = int(year_end_str) if year_end_str and year_end_str.isdigit() else None

        is_actual = datetime.datetime.today().year < year_end if year_end else False

        aup_info = AupInfo(
            file=filename,
            num_aup=aup_num,
            base=header_dict.get("На базе"),
            # --- ИСПРАВЛЕНО: Используем ID ---
            id_faculty=faculty_instance.id_faculty if faculty_instance else None,
            id_rop=rop_instance.id_rop if rop_instance else None,
            id_department=department_instance.id_department if department_instance else None, # <-- ID кафедры
            id_degree=degree_instance.id_degree if degree_instance else None,
            id_form=form_instance.id_form if form_instance else None,
            id_spec=name_op_instance.id_spec if name_op_instance else None,
            # --- Остальные поля ---
            type_educ=header_dict.get("Вид образования"),
            qualification=header_dict.get("Квалификация"),
            type_standard=header_dict.get("Тип стандарта"),
            period_educ=period_educ,
            years=int(years) if years else None,
            months=int(months) if months else None,
            year_beg=year_beg,
            year_end=year_end,
            is_actual=is_actual,
            is_delete=False,
            date_delete=None
        )

        session.add(aup_info)
        session.flush() # Получаем id_aup для нового AupInfo

        # --- Связывание AupInfo с EducationalProgram (ОСТАВЛЯЕМ как есть) ---
        logger.debug(f"Attempting to link AUP {aup_info.num_aup} to an Educational Program...")
        program_code = header_dict.get("Код специальности")
        program_profile = header_dict.get("Профиль (специализация)")
        enrollment_year_str = header_dict.get("Год набора")
        enrollment_year = int(enrollment_year_str) if enrollment_year_str and str(enrollment_year_str).isdigit() else None

        educational_program = session.query(EducationalProgram).filter_by(
             code=program_code,
             profile=program_profile,
             enrollment_year=enrollment_year
        ).first()

        if educational_program:
            if educational_program not in session: # Merge if not in session
                 educational_program = session.merge(educational_program, load=True)

            link_exists = session.query(EducationalProgramAup).filter_by(
                educational_program_id=educational_program.id,
                aup_id=aup_info.id_aup
            ).first()

            if not link_exists:
                new_link = EducationalProgramAup(
                    educational_program_id=educational_program.id,
                    aup_id=aup_info.id_aup,
                    is_primary=True
                )
                session.add(new_link)
                logger.info(f"   - Linked AUP {aup_info.num_aup} to Educational Program {educational_program.title} (ID: {educational_program.id}).")
            else:
                logger.debug(f"   - Link for AUP {aup_info.num_aup} and Program {educational_program.title} already exists.")
        else:
             logger.warning(f"   - Could not find matching Educational Program for AUP {aup_info.num_aup} (Code: {program_code}, Profile: {program_profile}, Year: {enrollment_year}). Link not created. Manual linking required.")
        # --- Конец связывания ---

        # --- Подготовка AupData (ОСТАВЛЯЕМ как есть) ---
        aup_data_instances = prepare_aup_data(
            data, aup_info, use_other_modules=use_other_modules, session=session
        )
        if aup_data_instances:
            session.bulk_save_objects(aup_data_instances)
            logger.debug(f"   - Prepared {len(aup_data_instances)} AupData entries for bulk save.")
        else:
            logger.warning(f"   - No AupData instances were generated for AUP {aup_num}.")

        # Коммит происходит в вызывающей функции (save_excel_files или CLI)

    except Exception as e:
        session.rollback() # Откат при ЛЮБОЙ ошибке внутри транзакции
        logger.error(f"Error during AUP import transaction for {filename}: {e}")
        traceback.print_exc()
        raise e

# Renamed from save_aup_data to prepare_aup_data
@timeit
def prepare_aup_data(
    data: DataFrame,
    aup_info: AupInfo,
    # saved_groups: dict | None = None, # Parameter removed as it was unused
    use_other_modules: bool = True,
    session: db.Session = db.session
) -> list[AupData]:
    """Подготавливает список объектов AupData для сохранения в БД."""
    logger.debug(f"   Preparing AupData for AUP ID: {aup_info.id_aup}")
    get_group_from_module = (
        lambda module: str(module)[8:-1].strip() if isinstance(module, str) and "Модуль" in module else str(module)
    )

    # Получаем справочники, передавая сессию
    blocks = fill_spr_from_aup_data_values(data["Блок"], D_Blocks, session=session)
    parts = fill_spr_from_aup_data_values(data["Часть"], D_Part, session=session)
    record_types = fill_spr_from_aup_data_values(data["Тип записи"], D_TypeRecord, session=session)
    disciplines_spr = fill_spr_from_aup_data_values(data["Дисциплина"], SprDiscipline, session=session)
    periods = fill_spr_from_aup_data_values(data["Период контроля"], D_Period, session=session)
    control_types = fill_spr_from_aup_data_values(data["Нагрузка"], D_ControlType, session=session)
    measures = fill_spr_from_aup_data_values(data["Ед. изм."], D_EdIzmereniya, session=session)

    modules_mapping = {}
    if use_other_modules:
        modules_mapping = get_discipline_module_mapper(session=session)

    modules_spr = fill_spr_from_aup_data_values(data["Модуль"], D_Modules, session=session, color="#5f60ec")

    group_names = [get_group_from_module(str(el)) for el in data["Модуль"]]
    groups_spr = fill_groups_from_aup_data_values(group_names, session=session)

    num_rows = get_num_rows(data)

    session.flush() # Убеждаемся, что все созданные справочники имеют ID

    instances = []
    for _, row in data.iterrows():
        # Используем словарь id по названию дисциплины для быстрого поиска
        discipline_title = str(row["Дисциплина"]).strip()
        discipline_spr = disciplines_spr.get(discipline_title)
        if not discipline_spr:
             logger.warning(f"     - Discipline '{discipline_title}' not found in lookup. Skipping row.")
             continue

        id_discipline = discipline_spr.id

        module_title = str(row["Модуль"]).strip()
        module_spr = modules_spr.get(module_title)
        if module_spr is None:
             logger.warning(f"     - Module '{module_title}' not found for discipline '{discipline_title}'.")
             # Пытаемся найти "Без названия" или использовать дефолтный ID 19
             module_spr = modules_spr.get("Без названия")
             if not module_spr:
                 try:
                     module_spr = session.query(D_Modules).get(19) # Try fetching default ID 19
                 except Exception:
                     module_spr = None

             if module_spr:
                 logger.warning(f"       - Using fallback module '{module_spr.title}' (ID: {module_spr.id}).")
             else:
                 logger.error(f"       - No fallback module found for discipline '{discipline_title}', skipping row.")
                 continue

        module_to_use_id = module_spr.id

        # Попытка переопределить модуль "Без названия" на основе маппинга
        if module_spr.title == "Без названия" and use_other_modules and id_discipline in modules_mapping:
            mapped_module_id = modules_mapping[id_discipline]
            mapped_module = session.query(D_Modules).get(mapped_module_id)
            if mapped_module:
                 logger.debug(f"       - Overriding module 'Без названия' with '{mapped_module.title}' (ID: {mapped_module_id}) for discipline ID {id_discipline}.")
                 module_to_use_id = mapped_module_id
                 # module_spr = mapped_module # Обновляем объект, если он нужен дальше
            else:
                 logger.warning(f"       - Mapped module ID {mapped_module_id} not found for discipline ID {id_discipline}. Using '{module_spr.title}'.")


        group_title = get_group_from_module(str(row["Модуль"]))
        group_spr = groups_spr.get(group_title)
        if group_spr is None:
             logger.warning(f"     - Group '{group_title}' not found for discipline '{discipline_title}'.")
             # Пытаемся найти "Основные" или использовать дефолтный ID 1
             group_spr = groups_spr.get("Основные")
             if not group_spr:
                 try:
                     group_spr = session.query(Groups).get(1) # Try fetching default ID 1
                 except Exception:
                     group_spr = None

             if group_spr:
                 logger.warning(f"       - Using fallback group '{group_spr.name_group}' (ID: {group_spr.id_group}).")
             else:
                 logger.error(f"       - No fallback group found for discipline '{discipline_title}', skipping row.")
                 continue

        group_to_use_id = group_spr.id_group

        # Получение ID из справочников с проверкой
        type_record_spr = record_types.get(str(row["Тип записи"]).strip())
        if not type_record_spr:
             logger.warning(f"     - Type Record '{row['Тип записи']}' not found. Skipping row.")
             continue

        period_spr = periods.get(str(row["Период контроля"]).strip())
        if not period_spr:
             logger.warning(f"     - Period '{row['Период контроля']}' not found. Skipping row.")
             continue

        control_type_spr = control_types.get(str(row["Нагрузка"]).strip())
        if not control_type_spr:
             logger.warning(f"     - Control Type '{row['Нагрузка']}' not found. Skipping row.")
             continue

        measure_spr = measures.get(str(row["Ед. изм."]).strip())
        if not measure_spr:
             logger.warning(f"     - Measure '{row['Ед. изм.']}' not found. Skipping row.")
             continue

        block_spr = blocks.get(str(row["Блок"]).strip())
        if not block_spr:
             logger.warning(f"     - Block '{row['Блок']}' not found. Skipping row.")
             continue

        part_spr = parts.get(str(row["Часть"]).strip()) # Может быть None
        part_id = part_spr.id if part_spr else None

        # Обработка числовых значений с проверкой
        try:
            amount_val = float(row["Количество"])
            amount = int(round(amount_val * 100)) if not pandas.isna(amount_val) else 0
        except (ValueError, TypeError):
            logger.warning(f"     - Invalid value for 'Количество': {row['Количество']}. Setting amount to 0.")
            amount = 0

        try:
            zet_val = float(row["ЗЕТ"])
            zet = int(round(zet_val * 100)) if not pandas.isna(zet_val) else 0
        except (ValueError, TypeError):
            logger.warning(f"     - Invalid value for 'ЗЕТ': {row['ЗЕТ']}. Setting ZET to 0.")
            zet = 0

        aup_data = AupData(
            id_aup=aup_info.id_aup,
            id_block=block_spr.id,
            shifr=str(row["Шифр"]),
            id_part=part_id,
            id_module=module_to_use_id,
            id_group=group_to_use_id,
            id_type_record=type_record_spr.id,
            id_discipline=id_discipline,
            _discipline=discipline_title, # Сохраняем оригинальное название
            id_period=period_spr.id,
            num_row=num_rows.get((str(row["Период контроля"]).strip(), discipline_title)), # Используем очищенные названия
            id_type_control=control_type_spr.id,
            amount=amount,
            id_edizm=measure_spr.id,
            zet=zet,
            used_for_report=False # По умолчанию
        )
        instances.append(aup_data)

    return instances


def get_education_duration(duration: str | None) -> tuple[int | None, int | None]:
    """Парсит строку срока обучения, возвращает кортеж (годы, месяцы)."""
    if not duration or pandas.isna(duration):
        return None, None
    duration_str = str(duration)
    years, months = None, None
    parts = duration_str.split()
    try:
        i = 0
        while i < len(parts):
            if parts[i].isdigit():
                num = int(parts[i])
                if i + 1 < len(parts):
                    unit = parts[i+1].lower().strip('.,')
                    if unit in ["г", "год", "года", "лет"]:
                        years = num
                        i += 2
                    elif unit in ["м", "мес", "месяц", "месяца", "месяцев"]:
                        months = num
                        i += 2
                    else:
                        i += 1 # Skip number if unit is unknown
                else:
                    i += 1 # Skip number if no unit follows
            else:
                i += 1 # Skip non-digit parts
    except (ValueError, IndexError):
        logger.warning(f"Could not parse education duration: '{duration_str}'. Returning (None, None).")
        return None, None

    return years, months


# Изменение в create_name_op для использования сессии
def create_name_op(header_dict: Dict[str, Any], session: db.Session = db.session) -> NameOP:
    """Находит или создает запись NameOP (профиль/специализация)."""
    program_code = header_dict.get("Код специальности")
    profile_name = header_dict.get("Профиль (специализация)")

    if not program_code or not profile_name:
        raise ValueError("Missing 'Код специальности' or 'Профиль (специализация)' in header for NameOP creation.")

    # Ищем существующий NameOP по code и name_spec
    existing_name_op = session.query(NameOP).filter_by(
         program_code=program_code,
         name_spec=profile_name
    ).first()

    if existing_name_op:
        logger.debug(f"   - Found existing NameOP: {profile_name} ({program_code})")
        return existing_name_op

    # Если не нашли, ищем или создаем OKCO (направление/специальность)
    okso: SprOKCO = session.query(SprOKCO).filter_by(
        program_code=program_code
    ).first()

    if not okso:
        okso_name = header_dict.get("Направление (специальность)", f"Направление {program_code}") # Default name
        logger.debug(f"   - Creating new SprOKCO: {okso_name} ({program_code})")
        okso = SprOKCO(
            program_code=program_code,
            name_okco=okso_name
        )
        session.add(okso)
        session.flush() # Получаем id_spec для связывания с NameOP
    else:
        logger.debug(f"   - Found existing SprOKCO: {okso.name_okco} ({program_code})")


    # Создаем новый профиль (NameOP)
    # Определяем следующий номер профиля для данного кода программы
    last_profile = session.query(NameOP.num_profile).filter_by(program_code=okso.program_code).order_by(NameOP.num_profile.desc()).first()
    next_num = int(last_profile[0]) + 1 if last_profile else 1
    logger.debug(f"   - Creating new NameOP: {profile_name} ({program_code}), num_profile: {next_num:02}")

    new_name_op = NameOP(
        program_code=okso.program_code,
        num_profile=f"{next_num:02}", # Форматируем с ведущим нулем
        name_spec=profile_name,
    )
    # Добавление происходит в вызывающей функции save_excel_data
    return new_name_op


@timeit
def fill_spr_from_aup_data_values(values, model, session: db.Session = db.session, **kwargs) -> Dict[str, Any]:
    """
    Наполняет справочную таблицу `model` значениями из `values`.
    Возвращает словарь {название: объект_модели} для найденных и созданных записей.
    """
    model_name = model.__name__
    # logger.debug(f"   Filling {model_name}...")

    # Определяем поле названия (title, name или name_*)
    title_field_attr, title_field_name = None, None
    possible_fields = ['title', 'name'] + [c.name for c in model.__table__.columns if c.name.startswith('name_')]

    for field_name in possible_fields:
        if hasattr(model, field_name):
            title_field_attr = getattr(model, field_name)
            title_field_name = field_name
            break
    else:
        raise AttributeError(f"Model {model_name} does not have a 'title', 'name', or 'name_*' field.")

    # Очищаем и уникализируем значения
    cleaned_values = [str(el).strip() for el in values if pandas.notna(el) and str(el).strip()]
    unique_values = list(set(cleaned_values))

    if not unique_values:
        logger.debug(f"     - No unique non-empty values found for {model_name}.")
        return {}

    # Получаем существующие экземпляры
    existing_instances_q = session.query(model).filter(title_field_attr.in_(unique_values)).all()
    existing_instances = {getattr(el, title_field_name): el for el in existing_instances_q}
    logger.debug(f"     - Found {len(existing_instances)} existing entries in {model_name}.")

    # Определяем, какие нужно создать
    created_instances_data = []
    for val in unique_values:
        if val not in existing_instances:
            instance_data = {title_field_name: val, **kwargs} # Включаем доп. аргументы (e.g., color)
            created_instances_data.append(instance_data)

    # Создаем новые экземпляры через bulk_insert_mappings
    if created_instances_data:
        logger.debug(f"     - Adding {len(created_instances_data)} new entries to {model_name}.")
        try:
            session.bulk_insert_mappings(model, created_instances_data)
            session.flush() # Важно для получения ID и обновления словаря
            # Обновляем словарь existing_instances только что созданными объектами
            newly_created_instances = session.query(model).filter(title_field_attr.in_([data[title_field_name] for data in created_instances_data])).all()
            for el in newly_created_instances:
                 existing_instances[getattr(el, title_field_name)] = el
            logger.debug(f"     - Successfully added and flushed {len(newly_created_instances)} new entries for {model_name}.")

        except IntegrityError as e:
            session.rollback() # Откатываем bulk_insert
            logger.error(f"Integrity error during bulk insert for {model_name}: {e}. Attempting insert one by one.")
            # Пытаемся добавить по одному
            failed_inserts = 0
            for data in created_instances_data:
                try:
                    # Проверяем еще раз перед вставкой
                    if data[title_field_name] not in existing_instances:
                        instance = model(**data)
                        session.add(instance)
                        session.flush()
                        existing_instances[data[title_field_name]] = instance
                except IntegrityError:
                    logger.warning(f"     - Duplicate entry skipped on single insert for {model_name}: {data[title_field_name]}")
                    session.rollback() # Откатываем неудачную вставку
                    # Пытаемся получить существующую запись
                    conflicting_instance = session.query(model).filter(title_field_attr == data[title_field_name]).first()
                    if conflicting_instance:
                        existing_instances[data[title_field_name]] = conflicting_instance
                    else:
                         failed_inserts += 1
                         logger.error(f"     - Could not retrieve conflicting instance for {model_name}: {data[title_field_name]}")
                except Exception as single_e:
                    logger.error(f"     - Error during single insert for {model_name} ({data[title_field_name]}): {single_e}")
                    session.rollback()
                    failed_inserts += 1
            if failed_inserts > 0:
                 logger.error(f"     - Failed to insert {failed_inserts} entries for {model_name} even one by one.")

        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error during bulk insert for {model_name}: {e}")
            traceback.print_exc()

    # Возвращаем словарь {title: instance} для всех
    return existing_instances


@timeit
def fill_groups_from_aup_data_values(values: List[str], session: db.Session = db.session) -> Dict[str, Groups]:
    """Наполняет справочник Groups и возвращает словарь {name_group: group_instance}."""
    model_name = "Groups"
    title_field_name = "name_group"
    title_field_attr = Groups.name_group
    # logger.debug(f"   Filling {model_name}...")

    cleaned_values = [str(el).strip() for el in values if pandas.notna(el) and str(el).strip()]
    unique_values = list(set(cleaned_values))

    if not unique_values:
        logger.debug(f"     - No unique non-empty values found for {model_name}.")
        return {}

    existing_instances_q = session.query(Groups).filter(title_field_attr.in_(unique_values)).all()
    existing_instances = {getattr(el, title_field_name): el for el in existing_instances_q}
    logger.debug(f"     - Found {len(existing_instances)} existing entries in {model_name}.")

    created_instances_data = []
    for val in unique_values:
        if val not in existing_instances:
             # Указываем все обязательные поля (name_group, color, weight)
             created_instances_data.append({title_field_name: val, "color": "#5f60ec", "weight": 5}) # Default color and weight

    if created_instances_data:
        logger.debug(f"     - Adding {len(created_instances_data)} new entries to {model_name}.")
        try:
            session.bulk_insert_mappings(Groups, created_instances_data)
            session.flush() # Важно для получения ID
            newly_created_instances = session.query(Groups).filter(title_field_attr.in_([data[title_field_name] for data in created_instances_data])).all()
            for el in newly_created_instances:
                 existing_instances[getattr(el, title_field_name)] = el
            logger.debug(f"     - Successfully added and flushed {len(newly_created_instances)} new entries for {model_name}.")

        except IntegrityError as e:
            session.rollback()
            logger.error(f"Integrity error during bulk insert for {model_name}: {e}. Attempting insert one by one.")
            failed_inserts = 0
            for data in created_instances_data:
                try:
                    if data[title_field_name] not in existing_instances:
                        instance = Groups(**data)
                        session.add(instance)
                        session.flush()
                        existing_instances[data[title_field_name]] = instance
                except IntegrityError:
                    logger.warning(f"     - Duplicate entry skipped on single insert for {model_name}: {data[title_field_name]}")
                    session.rollback()
                    conflicting_instance = session.query(Groups).filter(title_field_attr == data[title_field_name]).first()
                    if conflicting_instance:
                        existing_instances[data[title_field_name]] = conflicting_instance
                    else:
                        failed_inserts += 1
                        logger.error(f"     - Could not retrieve conflicting instance for {model_name}: {data[title_field_name]}")
                except Exception as single_e:
                    logger.error(f"     - Error during single insert for {model_name} ({data[title_field_name]}): {single_e}")
                    session.rollback()
                    failed_inserts += 1
            if failed_inserts > 0:
                 logger.error(f"     - Failed to insert {failed_inserts} entries for {model_name} even one by one.")

        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error during bulk insert for {model_name}: {e}")
            traceback.print_exc()

    return existing_instances


@timeit
def get_num_rows(data: DataFrame) -> dict[tuple[str, str], int]:
    """Определяет порядок строк дисциплин внутри каждого периода контроля."""
    default_weight = 5
    # Веса для сортировки дисциплин (больший вес = выше в списке)
    weights = {
        "Проектная деятельность": 10,
        "Введение в проектную деятельность": 10,
        "Управление проектами": 10,
        "Иностранный язык": 1,
    }

    periods = {}

    for _, row in data.iterrows():
        # Обработка NaN и приведение к строке
        period = str(row["Период контроля"]).strip() if pandas.notna(row["Период контроля"]) else "N/A"
        discipline = str(row["Дисциплина"]).strip() if pandas.notna(row["Дисциплина"]) else "N/A"

        if period == "N/A" or discipline == "N/A":
            continue # Пропускаем строки с отсутствующими данными

        weight = weights.get(discipline, default_weight)
        value = (discipline, weight) # Кортеж (название, вес)

        if period not in periods:
            periods[period] = [value]
        else:
            # Избегаем дублирования дисциплины в одном периоде
            if value not in periods[period]:
                 periods[period].append(value)

    res = {}
    for period, disciplines_with_weights in periods.items():
        # Сортировка: сначала по весу (убывание), потом по названию (возрастание)
        disciplines_with_weights.sort(key=lambda x: (-x[1], x[0]))
        # Нумерация от 1
        for i, (discipline, _) in enumerate(disciplines_with_weights, start=1):
            res[(period, discipline)] = i # Ключ - кортеж (период, дисциплина)

    return res


@timeit
def get_discipline_module_mapper(session: db.Session = db.session) -> dict[int, int]:
    """
    Создает маппинг {id_discipline: id_module} на основе наиболее часто встречающегося
    модуля для каждой дисциплины в существующих данных AupData.
    Используется для заполнения пустых модулей.
    """
    from collections import defaultdict, Counter
    logger.debug("   Generating discipline-module mapping...")

    # Запрос AupData, соединение с D_Modules, фильтрация по названию модуля
    # Выбираем только id дисциплины и id модуля
    query_result = (
        session.query(AupData.id_discipline, AupData.id_module)
        .join(D_Modules, AupData.id_module == D_Modules.id)
        # .filter(D_Modules.title.ilike('%модуль%')) # Можно убрать фильтр по названию, если нужно учитывать все модули
        .filter(AupData.id_discipline.isnot(None), AupData.id_module.isnot(None)) # Исключаем строки без ID
        .distinct() # Уникальные пары (id_discipline, id_module)
        .all()
    )
    logger.debug(f"     - Found {len(query_result)} potential discipline-module links.")

    # Группируем id_module по id_discipline
    grouped_modules = defaultdict(list)
    for id_discipline, id_module in query_result:
        grouped_modules[id_discipline].append(id_module)

    # Определяем наиболее частый модуль для каждой дисциплины
    result_mapping = {}
    for id_discipline, module_ids in grouped_modules.items():
        if not module_ids:
            continue
        # Считаем частоту каждого id_module
        count = Counter(module_ids)
        # Находим id_module с максимальной частотой
        most_frequent_module_id = max(count.items(), key=lambda item: item[1])[0]
        result_mapping[id_discipline] = most_frequent_module_id

    logger.debug(f"   - Generated mapping for {len(result_mapping)} disciplines.")
    return result_mapping