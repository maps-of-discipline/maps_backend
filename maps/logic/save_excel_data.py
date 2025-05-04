# maps/logic/save_excel_data.py
import datetime
from typing import Dict, Any, List, Optional, Tuple
import pandas
from pandas import DataFrame
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import exists
import traceback
import re
from sqlalchemy.orm import Session, joinedload
from werkzeug.datastructures import FileStorage # Keep this import

from maps.logic.excel_check import ExcelValidator # Keep this import
from maps.logic.read_excel import read_excel # Keep this import
from maps.logic.tools import timeit
from utils.logging import logger

# Импортируем только необходимые модели для ясности
from maps.models import (
    db, SprFaculty, Department, SprDegreeEducation, SprFormEducation, SprRop,
    SprOKCO, NameOP, AupInfo, AupData, D_Blocks, D_Part, D_TypeRecord,
    SprDiscipline, D_Period, D_ControlType, D_EdIzmereniya, D_Modules, Groups, Weeks
)
from competencies_matrix.models import (
    EducationalProgram, EducationalProgramAup, FgosVo, CompetencyMatrix # Added CompetencyMatrix
)
# Keep cabinet import if needed for deletion logic
from cabinet.models import (
    DisciplineTable,
)


# ============================================================
# НОВАЯ/ОБНОВЛЕННЫЕ Вспомогательные функции для парсинга
# ============================================================

def _parse_enrollment_year(enrollment_year_str: Optional[str]) -> Optional[int]:
    """
    Парсит строку "Год набора" из заголовка АУП (например, "2024 - 2025").
    Возвращает начальный год периода набора.
    """
    if not enrollment_year_str or pandas.isna(enrollment_year_str):
        return None
    try:
        # Очищаем строку от пробелов и потенциально других символов
        s = str(enrollment_year_str).strip()
        # Ищем первое число из 4х цифр в начале строки
        match = re.match(r'^\s*(\d{4})', s)
        if match:
            return int(match.group(1))
        else:
            logger.warning(f"Could not parse enrollment year from string: '{enrollment_year_str}'. Expected format starting with 'YYYY'.")
            return None
    except Exception as e:
        logger.warning(f"Unexpected error parsing enrollment year '{enrollment_year_str}': {e}")
        return None

def _get_education_duration(duration_str: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """Парсит строку срока обучения, возвращает кортеж (годы, месяцы)."""
    if not duration_str or pandas.isna(duration_str):
        return None, None
    years, months = None, None
    try:
        s = str(duration_str).lower().replace('ё', 'е').strip() # Приводим к нижнему регистру, заменяем ё, убираем пробелы

        # Поиск годов: ищем число, за которым следует "год", "лет"
        year_match = re.search(r'(\d+)\s*год(?:а|а|ет)?', s)
        if year_match:
            years = int(year_match.group(1))

        # Поиск месяцев: ищем число, за которым следует "мес", "месяц", "месяца"
        month_match = re.search(r'(\d+)\s*мес(?:яц|яца|ев)?', s)
        if month_match:
            months = int(month_match.group(1))

    except Exception as e:
        logger.warning(f"Could not parse education duration: '{duration_str}'. Returning (None, None). Error: {e}")
        return None, None

    # Если нашли годы, но не нашли месяцы, считаем месяцы равными 0
    if years is not None and months is None:
        months = 0

    return years, months

def _find_fgos_by_aup_header(header_dict: Dict[str, Any], session: Session) -> Optional[FgosVo]:
    """Находит запись FgosVo на основе данных заголовка АУП."""
    direction_code = str(header_dict.get("Код специальности")).strip() if pandas.notna(header_dict.get("Код специальности")) else None
    education_level_raw = header_dict.get("Уровень образования")
    standard_type_raw = header_dict.get("Тип стандарта")

    if not direction_code or not education_level_raw or not standard_type_raw:
        logger.warning("   - Missing key FGOS identification data in header. Cannot find FGOS.")
        return None

    level_mapping = {'бакалавриат': 'бакалавриат', 'магистратура': 'магистратура', 'специалитет': 'специалитет'} # Приводим к нижнему регистру
    standard_mapping = {'фгос3+': '3+', 'фгос 3+': '3+', 'фгос3++': '3++', 'фгос 3++': '3++', 'фгос во (3++)': '3++'} # Приводим к нижнему регистру

    mapped_level = level_mapping.get(str(education_level_raw).strip().lower())
    mapped_standard = standard_mapping.get(str(standard_type_raw).strip().lower())

    if not mapped_level or not mapped_standard:
        logger.warning(f"   - Cannot map FGOS level '{education_level_raw}' or standard type '{standard_type_raw}'. Cannot find FGOS.")
        return None

    fgos = session.query(FgosVo).filter_by(
        direction_code=direction_code,
        education_level=mapped_level,
        generation=mapped_standard
    ).first()

    if fgos:
        logger.debug(f"   - Found matching FgosVo ID {fgos.id}.")
    else:
        logger.warning(f"   - No matching FgosVo found for Code='{direction_code}', Level='{mapped_level}', Generation='{mapped_standard}'.")
    return fgos

# ============================================================
# НОВАЯ ФУНКЦИЯ: Обработка списка загруженных файлов АУП
# ============================================================

@timeit
def process_uploaded_aup_files(files: List[FileStorage], options: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Обрабатывает список загруженных Excel файлов АУП.
    Итерируется по каждому файлу, читает, валидирует и сохраняет данные в БД.
    Управляет транзакциями для каждого файла.

    Args:
        files: Список объектов FileStorage (загруженные файлы).
        options: Словарь с опциями импорта (например, {'checkboxForcedUploadModel': True}).

    Returns:
        Список словарей с результатами обработки каждого файла
        ({'aup': '...', 'filename': '...', 'errors': [...]}).
    """
    logger.info(f"Starting processing of {len(files)} uploaded AUP files...")
    all_files_results = []

    for file in files:
        filename = file.filename
        logger.info(f"Processing file: {filename}")

        # Каждая операция импорта файла - в своей транзакции
        session = db.session

        result = {
            "aup": "-", # Placeholder
            "filename": filename,
            "errors": [],
        }
        all_files_results.append(result)

        try:
            # 1. Чтение Excel файла
            file.stream.seek(0)
            header, data = read_excel(file.stream)
            logger.debug(f"   - Excel file '{filename}' read successfully.")

            # Получаем номер АУП для результата и логов
            header_dict_for_aup_num = header.set_index("Наименование")["Содержание"].to_dict()
            aup_num_for_log = str(header_dict_for_aup_num.get("Номер АУП")).strip() if pandas.notna(header_dict_for_aup_num.get("Номер АУП")) else "-"
            result["aup"] = aup_num_for_log

            # 2. Валидация данных
            logger.debug("   Validating data...")
            validation_errors = ExcelValidator.validate(options, header, data)

            if validation_errors:
                result["errors"] = validation_errors
                logger.warning(f"   !!! Validation failed for '{filename}'. AUP: {aup_num_for_log}")
                continue # Переходим к следующему файлу

            logger.debug("   - Validation successful.")

            # 3. Проверка на существование и удаление (если --force)
            # Проверяем существование АУП перед началом сохранения
            existing_aup_check = session.query(AupInfo.id_aup).filter_by(num_aup=aup_num_for_log).first()

            if existing_aup_check:
                if options.get("forced_upload", False): # Если опция 'forced_upload' включена
                    logger.info(f"   Force flag enabled. Attempting to delete existing AUP with number: {aup_num_for_log}")
                    try:
                        deleted = delete_aup_by_num(aup_num_for_log, session)
                        if deleted:
                            logger.info(f"     - Existing AUP marked for deletion successfully.")
                        else:
                            # Этого не должно произойти, т.к. мы только что проверили его наличие
                            logger.error(f"     - AUP {aup_num_for_log} was found but delete_aup_by_num failed to mark it.")
                            raise RuntimeError(f"Failed to delete existing AUP {aup_num_for_log} despite finding it.")
                    except Exception as e:
                        error_msg = f"Ошибка при попытке удалить существующий АУП {aup_num_for_log} (опция --force): {e}"
                        logger.error(error_msg)
                        session.rollback()
                        result["errors"].append({"message": error_msg})
                        continue # Переходим к следующему файлу
                else:
                    # АУП существует, но --force не указан
                    error_msg = f"AUP with number {aup_num_for_log} already exists in DB. Import aborted. Use --force to overwrite."
                    logger.error(error_msg)
                    result["errors"].append({"message": error_msg})
                    continue # Переходим к следующему файлу

            # 4. Сохранение данных в БД (вызывает save_excel_data)
            logger.debug("   Saving data to database...")
            save_excel_data(
                filename=filename,
                header=header,
                data=data,
                use_other_modules=options.get("checkboxFillNullModulesModel", False),
                session=session # Передаем текущую сессию
            )

            session.commit() # Коммит для этого файла
            logger.info(f"   Successfully processed and saved data for '{filename}'. AUP: {aup_num_for_log}\n")

        except Exception as e:
            # Ловим любую ошибку в процессе обработки файла (включая ошибки из save_excel_data)
            session.rollback() # Откатываем транзакцию для этого файла
            error_msg = f"Произошла ошибка при обработке файла '{filename}' (АУП: {aup_num_for_log}): {e}"
            logger.error(error_msg)
            traceback.print_exc()
            result["errors"].append({"message": error_msg})

        finally:
             # Поток закрывается автоматически при завершении запроса/контекста
             pass

    logger.info("Finished processing all uploaded AUP files.")
    return all_files_results

# ============================================================
# Вспомогательные функции для поиска/создания сущностей (улучшенные)
# ============================================================

def _find_or_create_lookup(model, filter_criteria: Dict[str, Any], defaults: Dict[str, Any], session: Session) -> Optional[Any]:
    """
    Находит или создает запись в справочной таблице. Обрабатывает None, гонки состояний.

    Args:
        model: Класс модели SQLAlchemy.
        filter_criteria: Словарь для фильтрации (None значения игнорируются).
        defaults: Словарь со значениями по умолчанию для создания (None значения игнорируются).
        session: Сессия SQLAlchemy.

    Returns:
        Найденный или созданный объект модели, или None при ошибке/невозможности.
    """
    clean_filter = {k: v for k, v in filter_criteria.items() if v is not None and (not isinstance(v, str) or v.strip())}
    clean_defaults = {k: v for k, v in defaults.items() if v is not None and (not isinstance(v, str) or v.strip())}

    instance = None
    if clean_filter:
        try:
            # Пытаемся найти с блокировкой, если возможно (зависит от БД и уровня изоляции)
            # with_for_update() может быть не всегда применим или желателен
            instance = session.query(model).filter_by(**clean_filter).first() # .with_for_update().first()
            if instance:
                logger.debug(f"   - Found existing {model.__name__}: {clean_filter}")
                return instance # Нашли существующий
        except SQLAlchemyError as e:
            logger.error(f"   - DB Error finding {model.__name__} with {clean_filter}: {e}")
            # Не прерываем, попробуем создать, но логируем ошибку
            pass # Продолжаем, чтобы попытаться создать

    # Не нашли или не было фильтра - создаем
    create_data = {**clean_defaults, **clean_filter}
    if not create_data:
        logger.warning(f"   - No valid data to lookup or create {model.__name__}. Filter: {filter_criteria}, Defaults: {defaults}")
        return None

    try:
        # Используем вложенную транзакцию (savepoint) для создания
        with session.begin_nested():
            logger.debug(f"   - Attempting to create new {model.__name__} with data: {create_data}")
            instance = model(**create_data)
            session.add(instance)
            session.flush() # Получаем ID и проверяем ограничения до коммита
            instance_id_repr = getattr(instance, 'id', getattr(instance, f'id_{model.__tablename__.split("_")[-1]}', 'N/A'))
            logger.debug(f"     - Created new {model.__name__} with ID: {instance_id_repr}")
            return instance
    except IntegrityError: # Обработка гонки - запись создана другим процессом между SELECT и INSERT
        # session.rollback() не нужен, т.к. begin_nested откатит savepoint автоматически
        logger.warning(f"   - Integrity error creating {model.__name__} (likely race condition). Attempting to refetch with {clean_filter}.")
        if clean_filter: # Ищем снова только если был фильтр
             try:
                # Повторный поиск без блокировки
                instance = session.query(model).filter_by(**clean_filter).first()
                if instance:
                    logger.debug(f"     - Refetched existing {model.__name__} after integrity error.")
                    return instance
                else: # Странная ситуация - ошибка Integrity, но запись не найдена
                    logger.error(f"     - CRITICAL: Failed to refetch {model.__name__} after integrity error with filter {clean_filter}.")
                    return None
             except SQLAlchemyError as e_refetch:
                  logger.error(f"   - DB Error refetching {model.__name__} after integrity error: {e_refetch}")
                  return None
        else: # Не было фильтра, ошибка Integrity не связана с гонкой по этому фильтру
             logger.error(f"   - Integrity error creating {model.__name__} with no filter criteria. Data: {create_data}")
             return None
    except Exception as e:
        # session.rollback() не нужен, т.к. begin_nested откатит savepoint автоматически
        logger.error(f"   - Unexpected error creating {model.__name__} with data {create_data}: {e}")
        traceback.print_exc()
        return None

def _find_or_create_name_op(program_code: Optional[str], profile_name: Optional[str], okso_name: Optional[str], session: Session) -> Optional[NameOP]:
    """Находит или создает запись NameOP (профиль) и связанный SprOKCO."""
    program_code_clean = str(program_code).strip() if program_code and not pandas.isna(program_code) else None
    if not program_code_clean:
        logger.error("Missing 'Код специальности' for NameOP lookup/creation.")
        return None

    profile_name_clean = str(profile_name).strip() if profile_name and not pandas.isna(profile_name) and str(profile_name).strip() else f"Основная ОП ({program_code_clean})"
    okso_name_clean = str(okso_name).strip() if okso_name and not pandas.isna(okso_name) and str(okso_name).strip() else f"Направление {program_code_clean}"

    # 1. OKCO
    okso = _find_or_create_lookup(SprOKCO, {'program_code': program_code_clean}, {'name_okco': okso_name_clean}, session)
    if not okso:
        logger.error(f"Failed to find/create SprOKCO for code {program_code_clean}.")
        return None

    # 2. NameOP
    name_op_filter = {'program_code': program_code_clean, 'name_spec': profile_name_clean}
    # Используем _find_or_create_lookup для NameOP, чтобы обработать гонки
    # Сначала пытаемся найти
    name_op = session.query(NameOP).filter_by(**name_op_filter).first()
    if name_op:
         logger.debug(f"   - Found existing NameOP: '{profile_name_clean}' ({program_code_clean})")
         # Убедимся, что связь с OKCO установлена (на случай старых данных)
         if not name_op.okco:
             logger.warning(f"   - Linking existing NameOP {name_op.id_spec} to OKCO {okso.program_code}")
             name_op.okco = okso
             session.add(name_op) # Добавляем в сессию для flush/commit
         return name_op

    # Не нашли, определяем номер профиля и создаем через _find_or_create_lookup
    max_num = session.query(db.func.max(NameOP.num_profile)).filter_by(program_code=program_code_clean).scalar()
    try:
        next_num_int = int(max_num) + 1 if max_num and str(max_num).isdigit() else 1
        num_profile_str = f"{next_num_int:02}"
    except Exception as e:
        logger.warning(f"Error determining next num_profile for {program_code_clean}. Using '01'. Error: {e}")
        num_profile_str = '01'

    name_op_defaults = {'num_profile': num_profile_str, 'okco': okso} # Сразу передаем okco в defaults
    new_name_op = _find_or_create_lookup(NameOP, name_op_filter, name_op_defaults, session)

    # Проверка связи с OKCO после создания (на случай, если _f_o_c вернул None или была гонка)
    if new_name_op and not new_name_op.okco:
         logger.warning(f"   - Re-linking NameOP {new_name_op.id_spec} to OKCO {okso.program_code} after creation.")
         new_name_op.okco = okso
         session.add(new_name_op) # Добавляем в сессию, если был откат

    return new_name_op


def _parse_aup_header_details(header_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Парсит детали из словаря заголовка, возвращает словарь с готовыми значениями."""
    details = {}
    # Год набора
    details['enrollment_year'] = _parse_enrollment_year(header_dict.get("Год набора"))
    # Срок обучения
    details['years'], details['months'] = _get_education_duration(header_dict.get("Фактический срок обучения"))
    # Период обучения
    period_educ_raw = header_dict.get("Период обучения")
    details['period_educ'] = str(period_educ_raw).strip() if period_educ_raw and not pandas.isna(period_educ_raw) else None
    details['year_beg'], details['year_end'] = None, None
    if details['period_educ']:
        match = re.match(r'^\s*(\d{4})\s*-\s*(\d{4})', details['period_educ'])
        if match:
            details['year_beg'] = int(match.group(1))
            details['year_end'] = int(match.group(2))
        else:
            logger.warning(f"Could not parse 'Период обучения' '{details['period_educ']}'.")
    # База
    base_raw = header_dict.get("На базе")
    details['base'] = str(base_raw).strip() if base_raw and not pandas.isna(base_raw) else None
    # Вид образования
    type_educ_raw = header_dict.get("Вид образования")
    details['type_educ'] = str(type_educ_raw).strip() if type_educ_raw and not pandas.isna(type_educ_raw) else None
    # Квалификация АУП
    qualification_raw = header_dict.get("Квалификация")
    details['qualification_aup'] = str(qualification_raw).strip() if qualification_raw and not pandas.isna(qualification_raw) else None
    # Тип стандарта
    type_standard_raw = header_dict.get("Тип стандарта")
    details['type_standard'] = str(type_standard_raw).strip() if type_standard_raw and not pandas.isna(type_standard_raw) else None

    return details

def _prepare_and_save_aup_info(
        filename: str, aup_num: str, header_dict: Dict[str, Any],
        related_entities: Dict[str, Any], session: Session
    ) -> AupInfo:
    """Создает и сохраняет запись AupInfo."""
    logger.debug("   Creating AupInfo entry...")
    header_details = _parse_aup_header_details(header_dict)

    is_actual = datetime.datetime.today().year <= (header_details['year_end'] if header_details['year_end'] is not None else 0)

    # Проверка наличия ID перед созданием AupInfo
    faculty_id = related_entities['faculty'].id_faculty if related_entities.get('faculty') else None
    rop_id = related_entities['rop'].id_rop if related_entities.get('rop') else None
    department_id = related_entities['department'].id_department if related_entities.get('department') else None # Может быть None
    degree_id = related_entities['degree'].id_degree if related_entities.get('degree') else None
    form_id = related_entities['form'].id_form if related_entities.get('form') else None
    spec_id = related_entities['name_op_spr'].id_spec if related_entities.get('name_op_spr') else None

    if not all([faculty_id, rop_id, degree_id, form_id, spec_id]):
        missing_ids = [k for k, v in {'faculty': faculty_id, 'rop': rop_id, 'degree': degree_id, 'form': form_id, 'name_op_spr': spec_id}.items() if not v]
        raise ValueError(f"Cannot create AupInfo: Missing IDs for {', '.join(missing_ids)}")

    aup_info = AupInfo(
        file=filename, num_aup=aup_num,
        base=header_details['base'],
        id_faculty=faculty_id,
        id_rop=rop_id,
        id_department=department_id,
        id_degree=degree_id,
        id_form=form_id,
        id_spec=spec_id,
        type_educ=header_details['type_educ'],
        qualification=header_details['qualification_aup'],
        type_standard=header_details['type_standard'],
        period_educ=header_details['period_educ'],
        years=header_details['years'], months=header_details['months'],
        year_beg=header_details['year_beg'], year_end=header_details['year_end'],
        is_actual=is_actual, is_delete=False, date_delete=None
    )
    session.add(aup_info)
    session.flush() # Получаем id_aup и проверяем ограничения
    logger.info(f"   AupInfo created with ID: {aup_info.id_aup} for num_aup: {aup_num}")
    return aup_info

def _find_or_create_educational_program(aup_num: str, header_dict: Dict[str, Any], name_op: NameOP, session: Session) -> Optional[EducationalProgram]:
    """Находит или создает Образовательную Программу, связанную с АУП."""
    logger.debug("   Looking up/creating Educational Program...")
    try:
        program_code = name_op.program_code
        profile_name = name_op.name_spec # Используем профиль из NameOP
        qualification = str(header_dict.get("Квалификация")).strip() if pandas.notna(header_dict.get("Квалификация")) else None
        form_of_education = str(header_dict.get("Форма обучения")).strip() if pandas.notna(header_dict.get("Форма обучения")) else None
        enrollment_year = _parse_enrollment_year(header_dict.get("Год набора"))

        if not all([program_code, profile_name, qualification, form_of_education, enrollment_year is not None]):
            # Логируем недостающие поля для диагностики
            missing_ep_fields = []
            if not program_code: missing_ep_fields.append("Program Code (from NameOP)")
            if not profile_name: missing_ep_fields.append("Profile Name (from NameOP)")
            if not qualification: missing_ep_fields.append("Qualification")
            if not form_of_education: missing_ep_fields.append("Form of Education")
            if enrollment_year is None: missing_ep_fields.append("Enrollment Year")
            raise ValueError(f"Missing key data for Educational Program lookup/creation from AUP {aup_num} header: {', '.join(missing_ep_fields)}.")

        fgos_vo = _find_fgos_by_aup_header(header_dict, session)

        program_filter = {'code': program_code, 'profile': profile_name, 'qualification': qualification,
                          'form_of_education': form_of_education, 'enrollment_year': enrollment_year}
        program_title_default = f"{profile_name} ({program_code})"
        program_defaults = {'title': program_title_default, 'fgos_vo_id': fgos_vo.id if fgos_vo else None}

        educational_program = _find_or_create_lookup(EducationalProgram, program_filter, program_defaults, session)
        if not educational_program:
            # _find_or_create_lookup вернул None, логируем детали
            logger.error(f"Failed to find or create Educational Program for AUP {aup_num} using filter {program_filter} and defaults {program_defaults}.")
            raise ValueError(f"Failed to find or create Educational Program for AUP {aup_num}.")

        logger.debug(f"   Educational Program found/created with ID: {educational_program.id}.")
        return educational_program
    except Exception as e:
        logger.error(f"   Error during Educational Program lookup/creation for AUP {aup_num}: {e}")
        raise # Перебрасываем ошибку

def _link_program_and_aup(educational_program: EducationalProgram, aup_info: AupInfo, session: Session) -> None:
    """Связывает АУП и Образовательную Программу."""
    logger.debug(f"   Linking AUP {aup_info.num_aup} to Educational Program ID {educational_program.id}...")
    try:
        # Используем вложенную транзакцию для создания связи
        with session.begin_nested():
            link_exists = session.query(EducationalProgramAup).filter_by(
                educational_program_id=educational_program.id, aup_id=aup_info.id_aup
            ).with_for_update().first() # Блокируем для предотвращения гонки

            if not link_exists:
                # Проверяем, сколько уже первичных связей у этой программы (без блокировки, т.к. мы уже внутри транзакции)
                primary_count = session.query(EducationalProgramAup).filter_by(
                    educational_program_id=educational_program.id, is_primary=True
                ).count()
                is_primary = (primary_count == 0)
                new_link = EducationalProgramAup(
                    educational_program_id=educational_program.id, aup_id=aup_info.id_aup, is_primary=is_primary
                )
                session.add(new_link)
                session.flush() # Проверяем ограничения
                logger.info(f"     - Linked AUP {aup_info.num_aup} to Program ID {educational_program.id} (is_primary={is_primary}).")
            else:
                logger.debug(f"     - Link for AUP {aup_info.num_aup} and Program ID {educational_program.id} already exists.")
                # TODO: Возможно, обновить is_primary, если нужно?
                # if not link_exists.is_primary:
                #     primary_count = session.query(EducationalProgramAup).filter(...).count()
                #     if primary_count == 0: link_exists.is_primary = True; session.add(link_exists)

    except IntegrityError:
        # session.rollback() не нужен
        logger.warning(f"   - Integrity error linking AUP {aup_info.num_aup} and Program ID {educational_program.id} (likely race condition). Link might already exist.")
        # Пробуем перечитать без блокировки
        link_exists_refetch = session.query(EducationalProgramAup).filter_by(
            educational_program_id=educational_program.id, aup_id=aup_info.id_aup
        ).first()
        if link_exists_refetch:
             logger.debug("     - Confirmed link exists after integrity error.")
        else:
             logger.error("     - CRITICAL: Integrity error on link, but link not found on refetch.")
             # Можно перебросить ошибку или продолжить с предупреждением
             # raise # Перебросить, если связь критична

    except Exception as e:
        # session.rollback() не нужен
        logger.error(f"   Error linking AUP {aup_info.num_aup} to Program ID {educational_program.id}: {e}")
        raise # Перебрасываем другие ошибки

@timeit
def _prepare_and_bulk_save_aup_data(
    data: DataFrame,
    aup_info: AupInfo,
    use_other_modules: bool,
    session: Session
) -> int:
    """Подготавливает и сохраняет записи AupData через bulk_save_objects."""
    logger.debug(f"   Preparing AupData for AUP ID: {aup_info.id_aup}")
    try:
        # Шаг 1: Подготовка всех справочников за один проход
        all_lookups = _prepare_all_lookups(data, session)

        # Шаг 2: Получение маппинга модулей и номеров строк
        modules_mapping = get_discipline_module_mapper(session) if use_other_modules else {}
        num_rows_map = get_num_rows(data) # Получаем нумерацию строк

        # Шаг 3: Итерация и создание объектов AupData
        instances = []
        skipped_rows_count = 0
        default_module_id = None # Кэшируем ID дефолтного модуля
        default_group_id = None # Кэшируем ID дефолтной группы

        for _, row in data.iterrows():
            instance, default_module_id, default_group_id = _create_aup_data_instance(
                row, aup_info.id_aup, all_lookups, modules_mapping, num_rows_map, use_other_modules,
                session, default_module_id, default_group_id # Передаем сессию и кэшированные ID
            )
            if instance:
                instances.append(instance)
            else:
                skipped_rows_count += 1

        if skipped_rows_count > 0:
            logger.warning(f"   - Skipped {skipped_rows_count} rows during AupData preparation due to missing data or errors.")

        # Шаг 4: Сохранение через bulk_save_objects
        if instances:
            session.bulk_save_objects(instances)
            # session.flush() # Не обязательно после bulk_save_objects, ID могут быть не установлены до commit
            logger.debug(f"   - Prepared {len(instances)} AupData entries for bulk save.")
            return len(instances)
        else:
            logger.warning(f"   - No valid AupData instances were generated for AUP {aup_info.num_aup}.")
            return 0

    except Exception as e:
        logger.error(f"   Error preparing/saving AupData for {aup_info.num_aup}: {e}")
        traceback.print_exc()
        raise # Перебрасываем, чтобы откатить транзакцию

def _prepare_all_lookups(data: DataFrame, session: Session) -> Dict[str, Dict[str, Any]]:
    """Подготавливает все необходимые справочники для AupData за один раз."""
    logger.debug("     Preparing all lookups for AupData...")
    lookups = {}
    get_group_name = lambda mod: str(mod)[8:-1].strip() if isinstance(mod, str) and "Модуль" in mod else str(mod)

    # Используем list comprehension для подготовки списков значений
    blocks_vals = [str(el).strip() for el in data["Блок"] if pandas.notna(el)]
    parts_vals = [str(el).strip() for el in data["Часть"] if pandas.notna(el)]
    record_types_vals = [str(el).strip() for el in data["Тип записи"] if pandas.notna(el)]
    disciplines_vals = [str(el).strip() for el in data["Дисциплина"] if pandas.notna(el)]
    periods_vals = [str(el).strip() for el in data["Период контроля"] if pandas.notna(el)]
    control_types_vals = [str(el).strip() for el in data["Нагрузка"] if pandas.notna(el)]
    measures_vals = [str(el).strip() for el in data["Ед. изм."].dropna()] # dropna здесь уместен
    modules_vals = [str(el).strip() for el in data["Модуль"] if pandas.notna(el)]
    group_names = [get_group_name(str(el)) for el in data["Модуль"] if pandas.notna(el)]

    # Вызываем fill_spr для каждого справочника
    lookups['blocks'] = fill_spr_from_aup_data_values(blocks_vals, D_Blocks, session=session)
    lookups['parts'] = fill_spr_from_aup_data_values(parts_vals, D_Part, session=session)
    lookups['record_types'] = fill_spr_from_aup_data_values(record_types_vals, D_TypeRecord, session=session)
    lookups['disciplines'] = fill_spr_from_aup_data_values(disciplines_vals, SprDiscipline, session=session)
    lookups['periods'] = fill_spr_from_aup_data_values(periods_vals, D_Period, session=session)
    lookups['control_types'] = fill_spr_from_aup_data_values(control_types_vals, D_ControlType, session=session)
    lookups['measures'] = fill_spr_from_aup_data_values(measures_vals, D_EdIzmereniya, session=session)
    lookups['modules'] = fill_spr_from_aup_data_values(modules_vals, D_Modules, session=session)
    lookups['groups'] = fill_groups_from_aup_data_values(group_names, session=session)

    logger.debug("     Finished preparing lookups.")
    return lookups

def _get_cached_default_id(cache_id: Optional[int], model, filter_criteria: Dict, fallback_id: int, session: Session) -> int:
    """Получает ID из кэша или запрашивает из БД."""
    if cache_id is not None:
        return cache_id
    try:
        found_id = session.query(model.id if hasattr(model, 'id') else model.id_group).filter_by(**filter_criteria).scalar()
        return found_id if found_id is not None else fallback_id
    except Exception as e:
        logger.warning(f"Error querying default ID for {model.__name__}: {e}. Using fallback {fallback_id}.")
        return fallback_id

def _create_aup_data_instance(
    row: pandas.Series, aup_id: int, lookups: Dict[str, Dict],
    modules_mapping: Dict[int, int], num_rows_map: Dict[Tuple[str, str], int], use_other_modules: bool,
    session: Session, # Добавлена сессия
    cached_default_module_id: Optional[int], # Кэшированный ID
    cached_default_group_id: Optional[int] # Кэшированный ID
) -> Tuple[Optional[AupData], Optional[int], Optional[int]]:
    """
    Создает один экземпляр AupData на основе строки DataFrame и подготовленных справочников.
    Возвращает кортеж (AupData | None, cached_default_module_id, cached_default_group_id).
    """
    # Извлечение и очистка данных из строки
    discipline_title = str(row.get("Дисциплина")).strip() if pandas.notna(row.get("Дисциплина")) else None
    period_title = str(row.get("Период контроля")).strip() if pandas.notna(row.get("Период контроля")) else None
    type_record_title = str(row.get("Тип записи")).strip() if pandas.notna(row.get("Тип записи")) else None
    control_type_title = str(row.get("Нагрузка")).strip() if pandas.notna(row.get("Нагрузка")) else None
    measure_title = str(row.get("Ед. изм.")).strip() if pandas.notna(row.get("Ед. изм.")) else None
    block_title = str(row.get("Блок")).strip() if pandas.notna(row.get("Блок")) else None
    part_title = str(row.get("Часть")).strip() if pandas.notna(row.get("Часть")) else None
    module_title = str(row.get("Модуль")).strip() if pandas.notna(row.get("Модуль")) else None
    group_title = (lambda mod: str(mod)[8:-1].strip() if isinstance(mod, str) and "Модуль" in mod else str(mod))(row.get("Модуль")) if pandas.notna(row.get("Модуль")) else None

    # Проверка наличия обязательных полей
    if not all([discipline_title, period_title, type_record_title, control_type_title, measure_title, block_title]):
        # logger.warning(f"     - Skipping row due to missing essential data: Discipline='{discipline_title}', Period='{period_title}', etc.")
        return None, cached_default_module_id, cached_default_group_id

    # Получение ID из справочников
    discipline_obj = lookups['disciplines'].get(discipline_title)
    type_record_obj = lookups['record_types'].get(type_record_title)
    period_obj = lookups['periods'].get(period_title)
    control_type_obj = lookups['control_types'].get(control_type_title)
    measure_obj = lookups['measures'].get(measure_title)
    block_obj = lookups['blocks'].get(block_title)
    part_obj = lookups['parts'].get(part_title) if part_title else None
    module_obj = lookups['modules'].get(module_title) if module_title else None
    group_obj = lookups['groups'].get(group_title) if group_title else None

    id_discipline_val = discipline_obj.id if discipline_obj else None
    id_type_record_val = type_record_obj.id if type_record_obj else None
    id_period_val = period_obj.id if period_obj else None
    id_control_type_val = control_type_obj.id if control_type_obj else None
    id_measure_val = measure_obj.id if measure_obj else None
    id_block_val = block_obj.id if block_obj else None
    id_part_val = part_obj.id if part_obj else None
    id_module_val = module_obj.id if module_obj else None
    id_group_val = group_obj.id_group if group_obj else None

    # Проверка, что все обязательные ID найдены
    if not all([id_discipline_val, id_type_record_val, id_period_val, id_control_type_val, id_measure_val, id_block_val]):
        logger.error(f"     - CRITICAL: Lookup ID failed for essential data. Skipping row for discipline '{discipline_title}'. Missing IDs for objects: {[o is None for o in [discipline_obj, type_record_obj, period_obj, control_type_obj, measure_obj, block_obj]]}")
        return None, cached_default_module_id, cached_default_group_id

    # Определение ID Модуля и Группы с fallback и переопределением
    if not id_module_val or (module_obj and module_obj.title == "Без названия"):
        # Получаем ID дефолтного модуля (из кэша или БД)
        current_default_module_id = _get_cached_default_id(cached_default_module_id, D_Modules, {'title': "Без названия"}, 19, session)
        if cached_default_module_id is None: cached_default_module_id = current_default_module_id # Обновляем кэш
        id_module_val = current_default_module_id

        # Пытаемся переопределить "Без названия"
        if use_other_modules and id_discipline_val in modules_mapping:
            mapped_module_id = modules_mapping[id_discipline_val]
            # Проверяем существование mapped_module_id без запроса объекта
            if session.query(exists().where(D_Modules.id == mapped_module_id)).scalar():
                # logger.debug(f"       - Overriding module 'Без названия' with mapped ID {mapped_module_id} for discipline ID {id_discipline_val}.")
                id_module_val = mapped_module_id
            # else:
                 # logger.warning(f"       - Mapped module ID {mapped_module_id} not found. Using 'Без названия' (ID: {id_module_val}).")

    if not id_group_val:
        # Получаем ID дефолтной группы (из кэша или БД)
        current_default_group_id = _get_cached_default_id(cached_default_group_id, Groups, {'name_group': "Основные"}, 1, session)
        if cached_default_group_id is None: cached_default_group_id = current_default_group_id # Обновляем кэш
        id_group_val = current_default_group_id

    # Получение num_row
    num_row_val = num_rows_map.get((period_title, discipline_title))
    if num_row_val is None:
        logger.warning(f"     - Could not determine num_row for discipline '{discipline_title}' in period '{period_title}'. Assigning 999.")
        num_row_val = 999 # Или другое дефолтное значение

    # Обработка числовых значений
    try: amount = int(round(float(row.get("Количество", 0)) * 100)) if pandas.notna(row.get("Количество")) else 0
    except (ValueError, TypeError): logger.warning(f"     - Invalid 'Количество': {row.get('Количество')}. Setting amount=0."); amount = 0
    try: zet = int(round(float(row.get("ЗЕТ", 0)) * 100)) if pandas.notna(row.get("ЗЕТ")) else 0
    except (ValueError, TypeError): logger.warning(f"     - Invalid 'ЗЕТ': {row.get('ЗЕТ')}. Setting ZET=0."); zet = 0

    # Создание объекта
    aup_data = AupData(
        id_aup=aup_id, id_block=id_block_val, shifr=str(row.get("Шифр", "")), # Добавлено .get с дефолтом
        id_part=id_part_val, id_module=id_module_val, id_group=id_group_val,
        id_type_record=id_type_record_val, id_discipline=id_discipline_val,
        _discipline=discipline_title, id_period=id_period_val,
        num_row=num_row_val,
        id_type_control=id_control_type_val, amount=amount, id_edizm=id_measure_val, zet=zet,
        used_for_report=False
    )
    return aup_data, cached_default_module_id, cached_default_group_id

def _handle_weeks_data(header: DataFrame, aup_id: int, session: Session) -> None:
    """Обрабатывает данные о неделях (пока не реализовано)."""
    logger.debug(f"   Processing Weeks for AUP ID: {aup_id}")
    try:
        # Поиск строки 'объем программы'
        weeks_row_index = header[header['Наименование'].str.contains('объем программы', case=False, na=False)].index
        if not weeks_row_index.empty:
             logger.warning("   - Complex Weeks parsing from Excel header is not implemented. Skipping Weeks data extraction.")
             # Здесь была бы логика парсинга и сохранения Weeks
             pass
        else:
             logger.warning("   - Could not find row containing 'объем программы' in header. Skipping Weeks data extraction.")
    except Exception as e:
        logger.error(f"   Error processing Weeks section for AUP ID: {aup_id}: {e}")
        # Не критично для основного импорта
        pass

# ============================================================
# Основная функция импорта (обновленная оркестровка)
# ============================================================

@timeit
def save_excel_data(
    filename: str,
    header: DataFrame,
    data: DataFrame,
    use_other_modules: bool = True,
    session: Session = db.session # Передаем сессию
):
    """
    Сохраняет данные ОДНОГО Excel файла АУП в базу данных.
    Оркестрирует поиск/создание связанных сущностей, AupInfo, EP, AupData.
    Выполняется в рамках ПЕРЕДАННОЙ сессии. Коммит/Роллбек - снаружи.

    Args:
        filename, header, data: Данные из Excel.
        use_other_modules: Флаг использования маппинга модулей.
        session: Сессия SQLAlchemy.

    Raises:
        ValueError: Если не найдены критичные данные в заголовке/справочниках.
        SQLAlchemyError: Если произошла ошибка БД.
        Exception: Любая другая непредвиденная ошибка.
    """
    logger.debug(f"Starting save_excel_data for file: {filename}")
    header_dict = header.set_index("Наименование")["Содержание"].to_dict()
    aup_num = str(header_dict.get("Номер АУП")).strip() if pandas.notna(header_dict.get("Номер АУП")) else None
    if not aup_num: raise ValueError("Номер АУП не найден в заголовке Excel.")

    # --- Шаг 1: Поиск/создание основных связанных сущностей ---
    logger.debug(f"  Looking up/creating essential related entities for AUP {aup_num}...")
    faculty = _find_or_create_lookup(SprFaculty, {'name_faculty': header_dict.get("Факультет")}, {'id_branch': 1}, session)
    department = _find_or_create_lookup(Department, {'name_department': header_dict.get("Выпускающая кафедра")}, {}, session) # Может быть None
    degree = _find_or_create_lookup(SprDegreeEducation, {'name_deg': header_dict.get("Уровень образования")}, {}, session)
    form = _find_or_create_lookup(SprFormEducation, {'form': header_dict.get("Форма обучения")}, {}, session)
    # ROP с ID=1 должен существовать, создаем если нет
    rop = _find_or_create_lookup(SprRop, {'id_rop': 1}, {'last_name': 'Дефолтный', 'first_name': 'РОП', 'middle_name': '', 'email':'rop@example.com', 'telephone':''}, session)
    name_op = _find_or_create_name_op(header_dict.get("Код специальности"), header_dict.get("Профиль (специализация)"), header_dict.get("Направление (специальность)"), session)

    related_entities = {'faculty': faculty, 'department': department, 'degree': degree, 'form': form, 'rop': rop, 'name_op_spr': name_op}
    # Проверяем, что все КРИТИЧНЫЕ сущности найдены/созданы
    if not all([faculty, degree, form, rop, name_op]):
         missing = [k for k, v in related_entities.items() if not v and k != 'department'] # Department не критичен
         logger.error(f"Failed to find or create essential entities for AUP {aup_num}: {', '.join(missing)}")
         raise ValueError(f"Failed to find or create essential entities: {', '.join(missing)}")
    logger.debug("  Essential related entities lookup/creation successful.")

    # --- Шаг 2: Поиск/создание Образовательной Программы ---
    educational_program = _find_or_create_educational_program(aup_num, header_dict, name_op, session)
    # _find_or_create_educational_program уже выбрасывает исключение, если не удалось создать/найти
    if not educational_program:
        # Эта проверка на всякий случай, если _f_o_c_ep вернет None без ошибки
        raise ValueError(f"Educational Program could not be found or created for AUP {aup_num}.")

    # --- Шаг 3: Создание AupInfo ---
    # _prepare_and_save_aup_info выбрасывает исключение при ошибке
    aup_info = _prepare_and_save_aup_info(filename, aup_num, header_dict, related_entities, session)

    # --- Шаг 4: Связывание ОП и АУП ---
    # _link_program_and_aup выбрасывает исключение при ошибке
    _link_program_and_aup(educational_program, aup_info, session)

    # --- Шаг 5: Подготовка и сохранение AupData ---
    # _prepare_and_bulk_save_aup_data выбрасывает исключение при ошибке
    saved_aup_data_count = _prepare_and_bulk_save_aup_data(data, aup_info, use_other_modules, session)
    logger.info(f"   - Prepared {saved_aup_data_count} AupData entries for AUP {aup_num} for bulk save.")

    # --- Шаг 6: Обработка Weeks (заглушка) ---
    _handle_weeks_data(header, aup_info.id_aup, session) # Не выбрасывает критичных ошибок

    logger.info(f"Successfully processed AUP {aup_num} within the session. Commit required externally.")
    # Коммит или роллбек должен быть сделан ВНЕ этой функции


# ============================================================
# Функции для наполнения справочников (модифицированы)
# ============================================================

@timeit
def fill_spr_from_aup_data_values(values: List[str], model, session: Session, **kwargs) -> Dict[str, Any]:
    """Наполняет справочную таблицу и возвращает словарь {название: объект_модели}."""
    model_name = model.__name__
    # Динамическое определение поля для названия
    title_field_name = None
    possible_fields = ['title', 'name'] + [c.name for c in model.__table__.columns if c.name.startswith('name_')]
    for field_name in possible_fields:
        if hasattr(model, field_name):
            title_field_name = field_name
            break
    if not title_field_name: raise AttributeError(f"Model {model_name} needs 'title', 'name', or 'name_*' field.")
    title_field_attr = getattr(model, title_field_name)

    # Очистка и получение уникальных значений (уже сделано в _prepare_all_lookups)
    # cleaned_values = [v for v in (str(el).strip() for el in values if pandas.notna(el)) if v]
    unique_values = list(set(values)) # values уже очищены
    if not unique_values: return {}

    # Получение существующих записей
    existing_instances_map = {}
    try:
        existing_instances_map = {getattr(el, title_field_name): el for el in session.query(model).filter(title_field_attr.in_(unique_values)).all()}
    except SQLAlchemyError as e:
        logger.error(f"Error fetching existing {model_name}: {e}")
        # Продолжаем, но могут быть дубликаты при вставке

    # Определение новых записей
    new_values = [val for val in unique_values if val not in existing_instances_map]
    if not new_values:
        # logger.debug(f"     - No new entries to add for {model_name}.")
        return existing_instances_map # Возвращаем только существующие

    # Подготовка данных для новых записей
    created_instances_data = [{title_field_name: val, **kwargs} for val in new_values]
    # logger.debug(f"     - Preparing to add {len(created_instances_data)} new entries to {model_name}.")

    # Попытка массовой вставки
    try:
        # Используем вложенную транзакцию для bulk insert
        with session.begin_nested():
            session.bulk_insert_mappings(model, created_instances_data)
            session.flush() # Важно для получения ID и проверки ограничений
            # После flush получаем новые объекты и добавляем в результат
            newly_created = session.query(model).filter(title_field_attr.in_(new_values)).all()
            for el in newly_created: existing_instances_map[getattr(el, title_field_name)] = el
            logger.debug(f"     - Successfully flushed {len(newly_created)} new entries for {model_name}.")
    except IntegrityError: # Обработка гонки состояний или других проблем уникальности
        # session.rollback() не нужен, savepoint откатится
        logger.warning(f"   - Integrity error during bulk insert for {model_name}. Trying one by one.")
        failed_inserts = 0
        for data in created_instances_data:
            # Используем _find_or_create_lookup для безопасного добавления по одному
            # Передаем только фильтр по title_field_name и остальные данные как defaults
            filter_crit = {title_field_name: data[title_field_name]}
            defaults_crit = {k: v for k, v in data.items() if k != title_field_name}
            instance = _find_or_create_lookup(model, filter_crit, defaults_crit, session)
            if instance:
                 existing_instances_map[data[title_field_name]] = instance
            else:
                 failed_inserts += 1
                 logger.error(f"     - Failed to add/find entry '{data[title_field_name]}' for {model_name} even after one-by-one attempt.")
        if failed_inserts > 0:
             logger.error(f"     - Failed to insert {failed_inserts} entries for {model_name} during one-by-one fallback.")
    except Exception as e:
        # session.rollback() не нужен, savepoint откатится
        logger.error(f"   - Unexpected error during bulk insert for {model_name}: {e}")
        traceback.print_exc()
        # Возвращаем только то, что уже было найдено до ошибки
        return {k:v for k,v in existing_instances_map.items() if getattr(v, title_field_name) not in new_values}

    return existing_instances_map

@timeit
def fill_groups_from_aup_data_values(values: List[str], session: Session = db.session) -> Dict[str, Groups]:
    """Наполняет справочник Groups и возвращает словарь {name_group: group_instance}."""
    # Убрали kwargs, т.к. они передаются напрямую в вызове fill_spr
    return fill_spr_from_aup_data_values(values, Groups, session, color="#5f60ec", weight=5)

@timeit
def get_num_rows(data: DataFrame) -> dict[tuple[str, str], int]:
    """Определяет порядок строк дисциплин внутри каждого периода контроля."""
    default_weight = 5
    # Веса для сортировки, дисциплины с большим весом идут выше
    weights = {"Проектная деятельность": 10, "Введение в проектную деятельность": 10,
               "Управление проектами": 10, "Иностранный язык": 1}
    periods = {}
    # Группируем дисциплины по периодам
    for _, row in data.iterrows():
        period = str(row.get("Период контроля")).strip() if pandas.notna(row.get("Период контроля")) else "N/A"
        discipline = str(row.get("Дисциплина")).strip() if pandas.notna(row.get("Дисциплина")) else "N/A"
        if period == "N/A" or discipline == "N/A": continue
        weight = weights.get(discipline, default_weight)
        value = (discipline, weight)
        if period not in periods: periods[period] = []
        # Добавляем дисциплину только если ее еще нет в этом периоде
        if not any(item[0] == discipline for item in periods[period]):
            periods[period].append(value)
    # Сортируем и нумеруем
    result_map = {}
    for period, disciplines_with_weights in periods.items():
        # Сортируем сначала по весу (убывание), потом по названию (возрастание)
        disciplines_with_weights.sort(key=lambda x: (-x[1], x[0]))
        for i, (discipline, _) in enumerate(disciplines_with_weights, start=1):
            result_map[(period, discipline)] = i
    return result_map

@timeit
def get_discipline_module_mapper(session: Session = db.session) -> dict[int, int]:
    """Создает маппинг {id_discipline: id_module}, выбирая самый частый модуль для дисциплины."""
    from collections import defaultdict, Counter
    logger.debug("   Generating discipline-module mapping...")
    # Загружаем связи Дисциплина-Модуль, исключая модуль "Без названия" (если он есть)
    # И присоединяем D_Modules для фильтрации по названию
    query_result = []
    try:
        query_result = (
            session.query(AupData.id_discipline, AupData.id_module)
            .join(D_Modules, AupData.id_module == D_Modules.id)
            .filter(
                AupData.id_discipline.isnot(None),
                AupData.id_module.isnot(None),
                D_Modules.title != "Без названия" # Исключаем модуль "Без названия"
            )
            .distinct()
            .all()
        )
        logger.debug(f"     - Found {len(query_result)} potential non-'Без названия' discipline-module links.")
    except SQLAlchemyError as e:
        logger.error(f"Error querying discipline-module links: {e}")
        return {} # Возвращаем пустой маппинг при ошибке

    # Группируем модули по дисциплинам
    grouped_modules = defaultdict(list)
    for id_discipline, id_module in query_result:
        if id_discipline is not None and id_module is not None: # Доп. проверка
             grouped_modules[id_discipline].append(id_module)

    # Определяем самый частый модуль для каждой дисциплины
    result_mapping = {}
    for id_discipline, module_ids in grouped_modules.items():
        if not module_ids: continue
        try:
            count = Counter(module_ids)
            # Выбираем самый частый ID модуля
            most_frequent_module_id = max(count, key=count.get)
            result_mapping[id_discipline] = most_frequent_module_id
        except Exception as e: # Ловим возможные ошибки при работе с Counter/max
            logger.warning(f"Error processing module counts for discipline ID {id_discipline}: {e}")
            continue # Пропускаем эту дисциплину

    logger.debug(f"   - Generated non-'Без названия' mapping for {len(result_mapping)} disciplines.")
    return result_mapping

# ============================================================
# Функции для удаления AUP (модифицированы)
# ============================================================

def _delete_aup_dependencies(aup_id: int, session: Session) -> None:
    """Удаляет все данные, зависящие от AUP, КРОМЕ САМОГО AupInfo."""
    logger.debug(f"Deleting dependencies for AUP ID: {aup_id}")

    # Используем synchronize_session=False для повышения производительности,
    # но это требует осторожности, т.к. объекты в сессии не обновляются.
    # Так как мы удаляем все и потом коммитим/откатываем всю транзакцию, это должно быть безопасно.

    # Зависимости в competencies_matrix (CompetencyMatrix)
    # Используем subquery для `in_` для лучшей производительности
    aup_data_ids_q = session.query(AupData.id).filter_by(id_aup=aup_id).subquery()
    deleted_matrix_count = session.query(CompetencyMatrix).filter(CompetencyMatrix.aup_data_id.in_(aup_data_ids_q)).delete(synchronize_session=False)
    logger.debug(f"   - Deleted {deleted_matrix_count} entries in CompetencyMatrix.")

    # Зависимости в cabinet (DisciplineTable)
    # Предполагаем, что каскадное удаление настроено в модели DisciplineTable для связанных таблиц
    deleted_dt_count = session.query(DisciplineTable).filter_by(id_aup=aup_id).delete(synchronize_session=False)
    logger.debug(f"   - Deleted {deleted_dt_count} entries in DisciplineTable (cascade should handle related).")

    # Зависимости в maps (AupData, Weeks)
    deleted_ad_count = session.query(AupData).filter_by(id_aup=aup_id).delete(synchronize_session=False)
    logger.debug(f"   - Deleted {deleted_ad_count} entries in AupData.")
    deleted_weeks_count = session.query(Weeks).filter_by(aup_id=aup_id).delete(synchronize_session=False)
    logger.debug(f"   - Deleted {deleted_weeks_count} entries in Weeks.")

    # Зависимости в competencies_matrix (EducationalProgramAup)
    deleted_ep_aup_count = session.query(EducationalProgramAup).filter_by(aup_id=aup_id).delete(synchronize_session=False)
    logger.debug(f"   - Deleted {deleted_ep_aup_count} entries in EducationalProgramAup.")

    # TODO: Добавить удаление зависимостей из других модулей, если они есть (например, Revision)

    logger.debug(f"Deletion of dependencies for AUP ID {aup_id} completed (marked for deletion).")


def delete_aup_by_num(aup_num: str, session: Session) -> bool:
    """
    Централизованная функция для удаления AUP по его номеру.
    Выполняется в рамках ПЕРЕДАННОЙ сессии. Коммит/Роллбек - снаружи.
    """
    if not aup_num: logger.warning("No AUP number provided for deletion."); return False
    logger.info(f"Attempting to delete AUP with number: {aup_num}")
    try:
        # Ищем AUP в переданной сессии с блокировкой
        aup_info = session.query(AupInfo).filter_by(num_aup=str(aup_num)).with_for_update().first()
        if not aup_info:
            logger.warning(f"AUP {aup_num} not found for deletion.")
            return False

        aup_id = aup_info.id_aup
        _delete_aup_dependencies(aup_id, session) # Удаляем зависимости
        session.delete(aup_info) # Помечаем сам AUP для удаления
        # НЕ делаем flush или commit здесь, это должно быть снаружи
        logger.info(f"Successfully marked AUP {aup_num} (ID: {aup_id}) and dependencies for deletion.")
        return True
    except SQLAlchemyError as e: # Ловим ошибки БД
        # Роллбэк делается снаружи!
        logger.error(f"Database error during deletion of AUP {aup_num}: {e}")
        traceback.print_exc()
        raise e # Перебрасываем исключение, чтобы вызвать rollback снаружи
    except Exception as e: # Ловим другие ошибки
        # Роллбэк делается снаружи!
        logger.error(f"Unexpected error deleting AUP {aup_num}: {e}")
        traceback.print_exc()
        raise e # Перебрасываем исключение