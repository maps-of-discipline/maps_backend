# maps/logic/save_excel_data.py
# maps/logic/save_excel_data.py
import datetime
from typing import Dict, Any, List, Optional, Tuple
import pandas
from pandas import DataFrame
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import exists
import traceback
from werkzeug.datastructures import FileStorage
from sqlalchemy.orm import Session
import re # Импортируем модуль для регулярных выражений

from maps.logic.excel_check import ExcelValidator
from maps.logic.read_excel import read_excel
from maps.logic.tools import timeit
from utils.logging import logger

from maps.models import (
    db, D_Blocks, D_ControlType, D_EdIzmereniya, D_Modules, D_Part, D_Period,
    D_TypeRecord, SprDegreeEducation, SprDiscipline, SprFaculty, SprFormEducation,
    SprOKCO, AupData, AupInfo, Groups, Department, NameOP, SprRop, Weeks
)

from competencies_matrix.models import (
    EducationalProgram, EducationalProgramAup, CompetencyMatrix, FgosVo
)
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
    """
    Находит запись FgosVo на основе данных заголовка АУП.
    Ищем по коду направления, уровню образования и поколению стандарта.
    """
    direction_code = header_dict.get("Код специальности")
    education_level = header_dict.get("Уровень образования") # Например, "Бакалавриат"
    standard_type = header_dict.get("Тип стандарта") # Например, "ФГОС3++"

    if not direction_code or not education_level or not standard_type:
        logger.warning(f"   - Missing key FGOS identification data in header: Code='{direction_code}', Level='{education_level}', Standard='{standard_type}'. Cannot find FGOS.")
        return None

    # Примерные соответствия между строкой в Excel и значениями в БД (нужно уточнить по факту)
    level_mapping = {'Бакалавриат': 'бакалавриат', 'Магистратура': 'магистратура', 'Специалитет': 'специалитет'} # Добавить другие варианты при необходимости
    standard_mapping = {'ФГОС3+': '3+', 'ФГОС 3+': '3+', 'ФГОС3++': '3++', 'ФГОС 3++': '3++'} # Добавить другие варианты

    mapped_level = level_mapping.get(str(education_level).strip())
    mapped_standard = standard_mapping.get(str(standard_type).strip())

    if not mapped_level or not mapped_standard:
        logger.warning(f"   - Cannot map FGOS level '{education_level}' or standard type '{standard_type}'. Cannot find FGOS.")
        return None

    # Ищем ФГОС по коду направления, уровню и поколению
    fgos = session.query(FgosVo).filter_by(
        direction_code=str(direction_code).strip(),
        education_level=mapped_level,
        generation=mapped_standard
    ).first()

    if not fgos:
        logger.warning(f"   - No matching FgosVo found for Code='{direction_code}', Level='{mapped_level}', Generation='{mapped_standard}'.")
        # TODO: Возможно, создать заглушку FGOS, если не найден? Или оставить как есть? Пока оставляем как есть.
        return None

    logger.debug(f"   - Found matching FgosVo ID {fgos.id}.")
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
        # Используем явный контекст сессии
        session = db.session
        
        result = {
            "aup": "-", # Placeholder
            "filename": filename,
            "errors": [],
        }
        all_files_results.append(result)

        try:
            # 1. Чтение Excel файла
            # Используем seek(0) чтобы быть уверенными, что чтение начнется с начала
            file.stream.seek(0) 
            header, data = read_excel(file.stream)
            logger.debug(f"   - Excel file '{filename}' read successfully.")

            # Получаем номер АУП для результата
            # ИСПРАВЛЕНО: Надежное получение номера АУП для логов и результатов
            header_dict_for_aup_num = header.set_index("Наименование")["Содержание"].to_dict()
            aup_num_for_log = str(header_dict_for_aup_num.get("Номер АУП")).strip() if pandas.notna(header_dict_for_aup_num.get("Номер АУП")) else "-"
            result["aup"] = aup_num_for_log


            # 2. Валидация данных
            logger.debug("   Validating data...")
            validation_errors = ExcelValidator.validate(options, header, data)

            if validation_errors:
                result["errors"] = validation_errors
                logger.warning(f"   !!! Validation failed for '{filename}'. AUP: {aup_num_for_log}")
                # Не нужно откатывать, т.к. сохранения еще не было
                continue # Переходим к следующему файлу

            logger.debug("   - Validation successful.")

            # Делаем удаление в начале транзакции для этого файла
            if options.get("forced_upload", False): # Если опция 'forced_upload' включена
                logger.info(f"   Force flag enabled. Attempting to delete existing AUP with number: {aup_num_for_log}")
                # Обратите внимание: delete_aup_by_num теперь может выбросить исключение
                try:
                    deleted = delete_aup_by_num(aup_num_for_log, session)
                    if deleted:
                        logger.info(f"     - Existing AUP deleted successfully.")
                    else:
                        logger.warning(f"     - AUP {aup_num_for_log} not found for deletion (it might not have existed).")
                except Exception as e:
                    # Ошибка при удалении (например, конфликт FK, который не обрабатывается каскадом)
                    error_msg = f"Ошибка при попытке удалить существующий АУП {aup_num_for_log} (опция --force): {e}"
                    logger.error(error_msg)
                    # Делаем явный rollback перед тем как добавить ошибку и перейти к следующему файлу
                    session.rollback() 
                    result["errors"].append({"message": error_msg})
                    continue # Переходим к следующему файлу


            # 3. Сохранение данных в БД
            logger.debug("   Saving data to database...")
            # Используем save_excel_data для одного файла в рамках текущей сессии
            # Обратите внимание: save_excel_data теперь может выбросить исключение
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
            # Ловим любую ошибку в процессе обработки файла
            session.rollback() # Откатываем транзакцию для этого файла
            error_msg = f"Произошла ошибка при обработке файла '{filename}' (АУП: {aup_num_for_log}): {e}"
            logger.error(error_msg)
            traceback.print_exc()
            result["errors"].append({"message": error_msg})
            
        finally:
             # Закрываем поток файла после использования
             # file.stream.close() # Поток закрывается автоматически после выхода из with open или при завершении запроса
             pass # Нет необходимости явно закрывать FileStorage stream

    logger.info("Finished processing all uploaded AUP files.")
    return all_files_results

# ============================================================
# НОВЫЕ/ОБНОВЛЕННЫЕ Вспомогательные функции для поиска/создания сущностей
# ============================================================

def _find_or_create_lookup(model, filter_criteria: Dict[str, Any], defaults: Dict[str, Any], session: Session) -> Any:
    """
    Находит или создает запись в справочной таблице.
    Улучшена обработка None значений в filter_criteria и defaults.
    Добавлен возврат None при ошибке или невозможности создать/найти.

    Args:
        model: Класс модели SQLAlchemy.
        filter_criteria: Словарь для фильтрации. None значения игнорируются.
        defaults: Словарь со значениями по умолчанию для создания новой записи. None значения игнорируются.
        session: Сессия SQLAlchemy.

    Returns:
        Найденный или созданный объект модели, или None при ошибке/невозможности.
    """
    # Убираем None из критериев фильтра и значений по умолчанию
    clean_filter_criteria = {k: v for k, v in filter_criteria.items() if v is not None and (not isinstance(v, str) or v.strip())}
    clean_defaults = {k: v for k, v in defaults.items() if v is not None and (not isinstance(v, str) or v.strip())}

    # Если нет критериев фильтра, не можем искать существующий объект по этим критериям
    if clean_filter_criteria:
        instance = session.query(model).filter_by(**clean_filter_criteria).first()
        if instance:
            logger.debug(f"   - Found existing {model.__name__}: {clean_filter_criteria}")
            # Если объект вне сессии, мержим его
            if instance not in session:
                 try:
                     instance = session.merge(instance, load=True)
                 except Exception as e:
                      logger.error(f"     - Error merging existing {model.__name__} ({getattr(instance, 'id', 'N/A')}): {e}")
                      # Продолжаем без мержинга, если ошибка (может быть некритично)
                      pass
            return instance

    # Если объект не найден ИЛИ не было критериев фильтра, пробуем создать
    # Используем clean_defaults + clean_filter_criteria для создания (приоритет у clean_filter_criteria если поле дублируется)
    create_data = {**clean_defaults, **clean_filter_criteria}
    
    if not create_data: # Если после объединения все равно нет данных для создания
        logger.warning(f"   - No valid data to lookup or create {model.__name__}. Filter: {filter_criteria}, Defaults: {defaults}")
        return None

    instance = model(**create_data)
    try:
        session.add(instance)
        session.flush() # Получаем ID
        # Пытаемся получить ID, предполагая стандартные имена
        instance_id = getattr(instance, 'id', getattr(instance, f'id_{model.__tablename__.split("_")[-1]}', 'N/A'))
        logger.debug(f"     - Created new {model.__name__} with ID: {instance_id}. Data: {create_data}")
        return instance
    except IntegrityError as ie: # Обработка гонки состояний или дубликата, который не нашелся первым запросом
        session.rollback() # Откатываем вложенную транзакцию или изменения
        logger.warning(f"   - Integrity error creating {model.__name__} with data {create_data}. Attempting to refetch.")
        # Пробуем найти еще раз, возможно, запись появилась между первым SELECT и INSERT
        if clean_filter_criteria: # Ищем только если были критерии фильтрации
             instance = session.query(model).filter_by(**clean_filter_criteria).first()
             if instance:
                  logger.debug(f"     - Refetched existing {model.__name__} after integrity error.")
                  if instance not in session:
                      try:
                           instance = session.merge(instance, load=True)
                      except Exception as e: logger.error(f"     - Error merging refetched {model.__name__}: {e}")
                  return instance
             else:
                  logger.error(f"     - Failed to refetch {model.__name__} after integrity error with filter {clean_filter_criteria}.")
                  return None # Не смогли найти после ошибки
        else:
             logger.error(f"   - Integrity error creating {model.__name__} with no filter criteria. Cannot refetch.")
             return None # Не было критериев фильтра, не можем найти конфликтную запись

    except Exception as e:
        session.rollback() # Откатываем вложенную транзакцию или изменения
        logger.error(f"   - Unexpected error creating {model.__name__} with data {create_data}: {e}")
        traceback.print_exc()
        return None

def _find_or_create_name_op(program_code: Optional[str], profile_name: Optional[str], okso_name: Optional[str], session: Session) -> Optional[NameOP]:
    """
    Находит или создает запись NameOP (профиль) и связанный SprOKCO.
    Улучшена обработка None и пустых строк для профиля.
    """
    if not program_code or not str(program_code).strip():
        logger.error("Missing 'Код специальности' for NameOP lookup/creation. Aborting.")
        return None # Не можем создать без кода

    program_code = str(program_code).strip()
    # Профиль может быть None или пустой строкой для некоторых ОП без профиля
    profile_name_cleaned = profile_name if profile_name and not pandas.isna(profile_name) and str(profile_name).strip() else f"Основная ОП ({program_code})" # Используем дефолтное имя если профиль отсутствует

    # 1. Ищем или создаем OKCO
    okso_name_cleaned = okso_name if okso_name and not pandas.isna(okso_name) and str(okso_name).strip() else f"Направление {program_code}"
    okso_defaults = {'name_okco': okso_name_cleaned}
    okso = _find_or_create_lookup(SprOKCO, {'program_code': program_code}, okso_defaults, session)
    if not okso: # Если OKCO не удалось найти или создать
        logger.error(f"   - Failed to find or create SprOKCO for code {program_code}. Cannot proceed with NameOP.")
        return None

    # 2. Ищем или создаем NameOP
    # Используем очищенное имя профиля для поиска и создания
    name_op_filter = {'program_code': program_code, 'name_spec': profile_name_cleaned}
    existing_name_op = session.query(NameOP).filter_by(**name_op_filter).first()
    if existing_name_op:
        logger.debug(f"   - Found existing NameOP: '{profile_name_cleaned}' ({program_code})")
        if existing_name_op not in session:
             try:
                 existing_name_op = session.merge(existing_name_op, load=True)
             except Exception as e: logger.error(f"     - Error merging existing NameOP ({getattr(existing_name_op, 'id_spec', 'N/A')}): {e}")
        return existing_name_op
    else:
        # Определяем номер профиля - это может вызвать IntegrityError если гонка
        # Лучше использовать _find_or_create_lookup который обработает IntegrityError
        
        # Находим максимальный существующий num_profile для данного program_code
        max_num_profile = session.query(db.func.max(NameOP.num_profile))\
                               .filter_by(program_code=program_code)\
                               .scalar()
        
        try:
            next_num = int(max_num_profile) + 1 if max_num_profile and str(max_num_profile).isdigit() else 1
            num_profile_str = f"{next_num:02}" # Формат '01', '02' etc.
        except Exception as e:
             logger.error(f"Error determining next num_profile for {program_code}. Using default '01'. Error: {e}")
             num_profile_str = '01'

        logger.debug(f"   - Creating new NameOP: '{profile_name_cleaned}' ({program_code}), num_profile: {num_profile_str}")

        name_op_defaults = {'num_profile': num_profile_str}
        # filter_criteria уже содержит program_code и name_spec (используем очищенное имя профиля)
        # Используем _find_or_create_lookup для создания NameOP
        new_name_op = _find_or_create_lookup(NameOP, name_op_filter, name_op_defaults, session)
        
        if new_name_op and not new_name_op.okco: # Если NameOP создан, но связь с OKCO потеряна (IntegrityError при создании?)
             new_name_op.okco = okso # Явно устанавливаем связь
             session.add(new_name_op)
             try: session.flush()
             except Exception as e: logger.error(f"Error flushing NameOP after setting OKCO: {e}")

        return new_name_op


# ============================================================
# ОБНОВЛЕННАЯ основная функция импорта
# ============================================================

@timeit
def save_excel_data(
    filename: str,
    header: DataFrame,
    data: DataFrame,
    use_other_modules: bool = True,
    session: Session = db.session # Явно указываем тип сессии
):
    """
    Сохраняет данные одного Excel файла АУП в базу данных.
    (РЕФАКТОРИНГ: Добавлено автоматическое создание EducationalProgram)
    Вся операция выполняется в рамках ПЕРЕДАННОЙ сессии.
    Коммит или роллбек должен быть сделан ВНЕ этой функции.

    Args:
        filename: Имя файла Excel.
        header: DataFrame с данными заголовка ('Лист1').
        data: DataFrame с данными дисциплин ('Лист2').
        use_other_modules: Флаг использования маппинга модулей.
        session: Сессия SQLAlchemy для выполнения операций.
    """
    logger.debug(f"Processing AUP from file: {filename}")
    # ИСПРАВЛЕНО: Надежное получение header_dict и номера АУП
    header_dict = header.set_index("Наименование")["Содержание"].to_dict()
    aup_num_raw = header_dict.get("Номер АУП")
    aup_num = str(aup_num_raw).strip() if pandas.notna(aup_num_raw) else None

    if not aup_num:
         logger.error("Номер АУП не найден или пуст в заголовке Excel. Import aborted.")
         raise ValueError("Номер АУП не найден в заголовке Excel.")

    # ------------------------------------------------------------
    # Шаг 1: Удаление существующего AUP (вызывается перед этой функцией, если force=True)
    # ------------------------------------------------------------
    # Проверка на существование AUP в текущей сессии (для предотвращения дубликата)
    # Эта проверка теперь выполняется ТОЛЬКО в `process_uploaded_aup_files` перед вызовом этой функции
    # Если сюда дошли, и AUP уже есть, это значит, что `delete_aup_by_num` не был вызван (force=False)
    # или не сработал, или произошла гонка.
    # Проверим наличие в сессии/БД без попытки удалить
    existing_aup_check = session.query(AupInfo.id_aup).filter_by(num_aup=aup_num).first()
    if existing_aup_check:
         logger.error(f"AUP with number {aup_num} already exists in DB. Import aborted. Use --force to overwrite.")
         raise IntegrityError(f"AUP with number {aup_num} already exists.", params=None, orig=None)


    # ------------------------------------------------------------
    # Шаг 2: Поиск/создание связанных справочных сущностей (Факультет, Кафедра, РОП и т.д.)
    # ------------------------------------------------------------
    logger.debug("   Looking up/creating essential related entities for AUP...")
    try:
        # ИСПРАВЛЕНО: Используем более надежную версию _find_or_create_lookup
        faculty = _find_or_create_lookup(SprFaculty, {'name_faculty': header_dict.get("Факультет")}, {'id_branch': 1}, session)
        department_name = header_dict.get("Выпускающая кафедра")
        department = _find_or_create_lookup(Department, {'name_department': department_name}, {}, session) if department_name and not pandas.isna(department_name) else None
        degree = _find_or_create_lookup(SprDegreeEducation, {'name_deg': header_dict.get("Уровень образования")}, {}, session)
        form = _find_or_create_lookup(SprFormEducation, {'form': header_dict.get("Форма обучения")}, {}, session)
        # Default ROP (ID 1) - предполагаем, что РОП с ID=1 всегда существует или создается сидом
        rop = _find_or_create_lookup(SprRop, {'id_rop': 1}, {'last_name': 'Дефолтный', 'first_name': 'РОП', 'middle_name': '', 'email':'rop@example.com', 'telephone':''}, session)
        # ИСПРАВЛЕНО: Используем более надежную версию _find_or_create_name_op
        name_op_spr = _find_or_create_name_op(
            program_code=header_dict.get("Код специальности"),
            profile_name=header_dict.get("Профиль (специализация)"),
            okso_name=header_dict.get("Направление (специальность)"),
            session=session
        )
        logger.debug("   Essential related entities lookup/creation successful.")
    except Exception as e:
        logger.error(f"   Error during essential related entity lookup/creation: {e}")
        # Не выбрасываем ошибку сразу, т.к. можем добавить ее в result["errors"] в process_uploaded_aup_files
        # НО: save_excel_data должна либо успешно завершиться, либо выбросить исключение, чтобы вызвать rollback
        # Поэтому здесь лучше все-таки выбросить исключение
        raise # Перебрасываем ошибку

    # Проверяем, что все необходимые сущности для AUP были найдены или созданы
    if not faculty or not degree or not form or not rop or not name_op_spr:
         missing = [
             "Faculty" if not faculty else None,
             "Degree" if not degree else None,
             "Form" if not form else None,
             "ROP" if not rop else None,
             "NameOP_Spr" if not name_op_spr else None
         ]
         error_msg = f"Failed to find or create essential related entities for AUP: {', '.join(filter(None, missing))}. Aborting import for this AUP."
         logger.error(error_msg)
         raise ValueError(error_msg) # Выбрасываем исключение, чтобы обработать его снаружи
    # Department can be None

    # ------------------------------------------------------------
    # Шаг 3: Поиск/создание Образовательной Программы (EducationalProgram)
    # ------------------------------------------------------------
    logger.debug("   Looking up/creating Educational Program...")
    try:
        # 3.1. Парсим данные для EducationalProgram из заголовка АУП
        program_code = name_op_spr.program_code # Берем из найденного NameOP
        profile_name = name_op_spr.name_spec # Берем из найденного NameOP
        qualification = header_dict.get("Квалификация")
        form_of_education_raw = header_dict.get("Форма обучения")
        form_of_education = str(form_of_education_raw).strip() if form_of_education_raw and not pandas.isna(form_of_education_raw) else None
        enrollment_year_str = header_dict.get("Год набора")
        
        # ===> ИСПРАВЛЕНО: Используем новую функцию для парсинга года набора <===
        enrollment_year = _parse_enrollment_year(enrollment_year_str)
        # ===> КОНЕЦ ИСПРАВЛЕНИЯ <===
        

        if not program_code or not profile_name or not qualification or not form_of_education or enrollment_year is None:
             error_msg = f"Missing key data for Educational Program lookup/creation from AUP header (Code: {program_code}, Profile: {profile_name}, Qual: {qualification}, Form: {form_of_education}, Year: {enrollment_year}). Aborting."
             logger.error(error_msg)
             # ===> ИСПРАВЛЕНО: Поднимаем более специфическую ошибку <===
             raise ValueError(f"Не удалось определить обязательные поля для Образовательной Программы из заголовка Excel. Проверьте поля 'Код специальности', 'Профиль (специализация)', 'Квалификация', 'Форма обучения', 'Год набора'.")
             # ===> КОНЕЦ ИСПРАВЛЕНИЯ <===

        # 3.2. Находим соответствующий ФГОС ВО
        fgos_vo = _find_fgos_by_aup_header(header_dict, session)
        # FGOS может быть не найден, но это не должно блокировать создание программы, только ссылку на ФГОС

        # 3.3. Формируем фильтр и дефолтные значения для поиска/создания EducationalProgram
        program_filter = {
            'code': program_code,
            'profile': profile_name, # Используем profile
            'qualification': qualification,
            'form_of_education': form_of_education,
            'enrollment_year': enrollment_year
        }
        # Конструируем title, если создаем новую программу
        program_title_default = f"{profile_name} ({program_code})"
        program_defaults = {
            'title': program_title_default,
            'fgos_vo_id': fgos_vo.id if fgos_vo else None # Ссылка на ФГОС, если найден
        }

        # 3.4. Поиск или создание EducationalProgram
        # ИСПРАВЛЕНО: Используем более надежную версию _find_or_create_lookup
        educational_program = _find_or_create_lookup(
            EducationalProgram,
            program_filter,
            program_defaults,
            session
        )

        if not educational_program:
             # Эта ветка, по идее, не должна быть достигнута, если _find_or_create_lookup не вернул None
             error_msg = f"Failed to find or create Educational Program for AUP {aup_num} after _find_or_create_lookup call."
             logger.error(error_msg)
             raise ValueError(error_msg)

        logger.debug(f"   Educational Program found/created with ID: {educational_program.id}.")

    except Exception as e:
        logger.error(f"   Error during Educational Program lookup/creation for AUP {aup_num}: {e}")
        raise # Перебрасываем ошибку

    # ------------------------------------------------------------
    # Шаг 4: Создание AupInfo
    # ------------------------------------------------------------
    logger.debug("   Creating AupInfo entry...")
    try:
        years, months = _get_education_duration(header_dict.get("Фактический срок обучения"))
        period_educ_raw = header_dict.get("Период обучения")
        period_educ = str(period_educ_raw).strip() if period_educ_raw and not pandas.isna(period_educ_raw) else None
        
        # ИСПРАВЛЕНО: Более надежное извлечение года начала и окончания из "Период обучения"
        year_beg, year_end = None, None
        if period_educ:
             period_match = re.match(r'^\s*(\d{4})\s*-\s*(\d{4})', period_educ)
             if period_match:
                  year_beg = int(period_match.group(1))
                  year_end = int(period_match.group(2))
             else:
                  logger.warning(f"Could not parse 'Период обучения' '{period_educ}'. Expected format 'YYYY - YYYY'.")


        is_actual = datetime.datetime.today().year <= (year_end if year_end is not None else 0)

        # Проверка на None перед доступом к ID найденных/созданных сущностей
        faculty_id = faculty.id_faculty if faculty else None
        rop_id = rop.id_rop if rop else None
        department_id = department.id_department if department else None # Department может быть None
        degree_id = degree.id_degree if degree else None
        form_id = form.id_form if form else None
        spec_id = name_op_spr.id_spec if name_op_spr else None # Используем id NameOP

        # Базовые поля из Excel, могут быть None или NaN в Excel -> None
        base_raw = header_dict.get("На базе")
        base = str(base_raw).strip() if base_raw and not pandas.isna(base_raw) else None
        type_educ_raw = header_dict.get("Вид образования")
        type_educ = str(type_educ_raw).strip() if type_educ_raw and not pandas.isna(type_educ_raw) else None
        qualification_raw = header_dict.get("Квалификация")
        qualification_aup = str(qualification_raw).strip() if qualification_raw and not pandas.isna(qualification_raw) else None # Квалификация АУП
        type_standard_raw = header_dict.get("Тип стандарта")
        type_standard = str(type_standard_raw).strip() if type_standard_raw and not pandas.isna(type_standard_raw) else None


        aup_info = AupInfo(
            file=filename, num_aup=aup_num, base=base,
            id_faculty=faculty_id, id_rop=rop_id, id_department=department_id,
            id_degree=degree_id, id_form=form_id, id_spec=spec_id,
            type_educ=type_educ,
            qualification=qualification_aup, # Используем квалификацию из заголовка АУП
            type_standard=type_standard,
            period_educ=period_educ, years=years, months=months,
            year_beg=year_beg, year_end=year_end, is_actual=is_actual,
            is_delete=False, date_delete=None
        )
        session.add(aup_info)
        session.flush() # Получаем id_aup
        logger.info(f"   AupInfo created with ID: {aup_info.id_aup} for num_aup: {aup_num}")
    except Exception as e:
        logger.error(f"   Error creating AupInfo for {aup_num}: {e}")
        raise

    # ------------------------------------------------------------
    # Шаг 5: Связывание AupInfo с EducationalProgram
    # ------------------------------------------------------------
    logger.debug(f"   Linking AUP {aup_info.num_aup} to Educational Program ID {educational_program.id}...")
    try:
        link_exists = session.query(EducationalProgramAup).filter_by(
            educational_program_id=educational_program.id,
            aup_id=aup_info.id_aup
        ).first()
        if not link_exists:
            # Проверяем, сколько уже первичных связей у этой программы
            primary_links_count = session.query(EducationalProgramAup).filter_by(
                educational_program_id=educational_program.id,
                is_primary=True
            ).count()
            is_primary_link = (primary_links_count == 0) # Делаем первичной, если других первичных нет

            new_link = EducationalProgramAup(educational_program_id=educational_program.id, aup_id=aup_info.id_aup, is_primary=is_primary_link)
            session.add(new_link)
            logger.info(f"     - Linked AUP {aup_info.num_aup} to Program ID {educational_program.id} (is_primary={is_primary_link}).")
        else:
            logger.debug(f"     - Link for AUP {aup_info.num_aup} and Program ID {educational_program.id} already exists.")
            # TODO: Возможно, обновить is_primary, если в новой выгрузке этот AUP указан как основной?

    except Exception as e:
        logger.error(f"   Error linking AUP {aup_info.num_aup} to Program ID {educational_program.id}: {e}")
        raise

    # ------------------------------------------------------------
    # Шаг 6: Подготовка AupData
    # ------------------------------------------------------------
    logger.debug(f"   Preparing AupData for AUP ID: {aup_info.id_aup}")
    try:
        aup_data_instances = prepare_aup_data(
            data, aup_info, use_other_modules=use_other_modules, session=session
        )
        if aup_data_instances:
            session.bulk_save_objects(aup_data_instances)
            # session.flush() # Не нужно, bulk_save_objects не гарантирует ID до commit
            logger.debug(f"   - Prepared {len(aup_data_instances)} AupData entries for bulk save.")
        else:
            logger.warning(f"   - No AupData instances were generated for AUP {aup_num}.")
    except Exception as e:
        logger.error(f"   Error preparing AupData for {aup_num}: {e}")
        raise # Перебрасываем, чтобы откатить транзакцию

    # ------------------------------------------------------------
    # Шаг 7: Обработка Weeks (Недель)
    # ------------------------------------------------------------
    logger.debug(f"   Preparing Weeks for AUP ID: {aup_info.id_aup}")
    try:
        # Находим колонку с неделями в header DataFrame. Имя может варьироваться ('Количество недель', 'Всего часов' и т.д.)
        # Будем искать по заголовку 'Объем программы...' на 'Лист1'
        weeks_row_index = header[header['Наименование'].str.contains('объем программы', case=False, na=False)].index
        if not weeks_row_index.empty:
             weeks_row = header.loc[weeks_row_index[0]]
             # Колонки с неделями начинаются после "Сводные данные по бюджету времени в неделях"
             # и обычно имеют заголовки семестров или номера недель (1, 2, ..., 52).
             # В предоставленном файле заголовки - "1 7", "8 14" и т.д.
             # Сами значения недель находятся в строке "Теоретическое обучение", "Экзаменационные сессии", "Каникулы" и т.д.
             # В предоставленном файле - строка с "Теоретическое обучение" имеет индекс 48
             theoretical_study_row_index = header[header['Наименование'].str.contains('Теоретическое обучение', case=False, na=False)].index
             if not theoretical_study_row_index.empty:
                  weeks_data_row = header.loc[theoretical_study_row_index[0]]
                  logger.debug(f"     - Found Weeks data row at index {theoretical_study_row_index[0]}.")
                  # Колонки с данными недель начинаются после колонки 'Всего' в сводных данных (индекс 55 в вашем файле)
                  # Колонки с семестрами в шапке графика (строки 3, 4) имеют индексы 4-55.
                  # Нужно сопоставить колонки недель с периодами (семестрами).
                  # В вашем файле: Семестр 1 (колонка 4, "22 IX 28") -> Недели (колонка 4, 4)
                  #                 Семестр 2 (колонка 8, "27 X 2 XI") -> Недели (колонка 8, 4) ... 
                  # Это сложное сопоставление.
                  # ПРОЩЕ: Найти колонку "Теоретическое обучение", "Экзаменационные сессии", "Каникулы" и др.
                  # В вашем файле: Теоретическое обучение (колонка 48, 4), Экзамены (50, 2), Каникулы (56, 2)
                  
                  # Пока реализуем только сохранение общих недель по типам (Теоретическое, Экзамены, Каникулы)
                  # Для связи с d_period (семестрами) нужно более сложное сопоставление колонок шапки.
                  # ВРЕМЕННО: Заглушка для Weeks или попытка очень простого парсинга по известным колонкам
                  logger.warning("   - Complex Weeks parsing is not fully implemented. Skipping Weeks data extraction from Excel.")
                  # TODO: Реализовать надежный парсер для Weeks (связь недель с периодами).

             else:
                  logger.warning("   - Could not find 'Теоретическое обучение' row in header for Weeks data.")
        else:
             logger.warning("   - Could not find row containing 'объем программы' in header for Weeks data.")
             
        # TODO: Реализовать сохранение данных в таблицу Weeks

    except Exception as e:
        logger.error(f"   Error preparing Weeks for AUP ID: {aup_info.id_aup}: {e}")
        # Не выбрасываем ошибку сразу, т.к. это не критично для импорта АУП
        pass # Продолжаем

    logger.info(f"Successfully prepared data for AUP {aup_num}. Commit required outside this function.")

# ============================================================
# Вспомогательные функции для подготовки AupData
# ============================================================

@timeit
def prepare_aup_data(
    data: DataFrame,
    aup_info: AupInfo,
    use_other_modules: bool = True,
    session: Session = db.session # Явно указываем тип сессии
) -> list[AupData]:
    """Подготавливает список объектов AupData для сохранения в БД."""
    logger.debug(f"   Preparing AupData for AUP ID: {aup_info.id_aup}")
    get_group_from_module = (
        lambda module: str(module)[8:-1].strip() if isinstance(module, str) and "Модуль" in module else str(module)
    )

    # Получаем справочники, передавая сессию
    # ИСПРАВЛЕНО: Явное приведение к строке и очистка перед передачей
    blocks = fill_spr_from_aup_data_values([str(el).strip() for el in data["Блок"] if pandas.notna(el)], D_Blocks, session=session)
    parts = fill_spr_from_aup_data_values([str(el).strip() for el in data["Часть"] if pandas.notna(el)], D_Part, session=session)
    record_types = fill_spr_from_aup_data_values([str(el).strip() for el in data["Тип записи"] if pandas.notna(el)], D_TypeRecord, session=session)
    disciplines_spr = fill_spr_from_aup_data_values([str(el).strip() for el in data["Дисциплина"] if pandas.notna(el)], SprDiscipline, session=session)
    periods = fill_spr_from_aup_data_values([str(el).strip() for el in data["Период контроля"] if pandas.notna(el)], D_Period, session=session)
    control_types = fill_spr_from_aup_data_values([str(el).strip() for el in data["Нагрузка"] if pandas.notna(el)], D_ControlType, session=session)
    measures = fill_spr_from_aup_data_values([str(el).strip() for el in data["Ед. изм."].dropna()], D_EdIzmereniya, session=session) # Dropping NaN in 'Ед. изм.'
    # Add modules lookup
    modules_spr = fill_spr_from_aup_data_values([str(el).strip() for el in data["Модуль"] if pandas.notna(el)], D_Modules, session=session)
    
    modules_mapping = {}
    if use_other_modules:
        modules_mapping = get_discipline_module_mapper(session=session)

    # ИСПРАВЛЕНО: Получение названий групп из модуля с очисткой
    group_names = [get_group_from_module(str(el)) for el in data["Модуль"] if pandas.notna(el)]
    groups_spr = fill_groups_from_aup_data_values(group_names, session=session)

    num_rows = get_num_rows(data)

    instances = []
    for _, row in data.iterrows():
        # ИСПРАВЛЕНО: Надежное получение значений из строки с очисткой
        discipline_title = str(row["Дисциплина"]).strip() if pandas.notna(row["Дисциплина"]) else None
        period_title = str(row["Период контроля"]).strip() if pandas.notna(row["Период контроля"]) else None
        type_record_title = str(row["Тип записи"]).strip() if pandas.notna(row["Тип записи"]) else None
        control_type_title = str(row["Нагрузка"]).strip() if pandas.notna(row["Нагрузка"]) else None
        measure_title = str(row["Ед. изм."]).strip() if pandas.notna(row["Ед. изм."]) else None
        block_title = str(row["Блок"]).strip() if pandas.notna(row["Блок"]) else None
        part_title = str(row["Часть"]).strip() if pandas.notna(row["Часть"]) else None # Может быть NaN
        module_title = str(row["Модуль"]).strip() if pandas.notna(row["Модуль"]) else None # Может быть NaN
        group_title = get_group_from_module(str(row["Модуль"])) if pandas.notna(row["Модуль"]) else None # Может быть NaN


        # Пропускаем строку, если нет минимально необходимых данных
        if not discipline_title or not period_title or not type_record_title or not control_type_title or not measure_title or not block_title:
             logger.warning(f"     - Skipping row due to missing essential data: Discipline='{discipline_title}', Period='{period_title}', etc.")
             continue

        # Получение ID из справочников с проверкой
        discipline_spr = disciplines_spr.get(discipline_title)
        type_record_spr = record_types.get(type_record_title)
        period_spr = periods.get(period_title)
        control_type_spr = control_types.get(control_type_title)
        measure_spr = measures.get(measure_title)
        block_spr = blocks.get(block_title)
        part_spr = parts.get(part_title) if part_title else None # Может быть None
        module_spr = modules_spr.get(module_title) if module_title else None # Может быть None
        group_spr = groups_spr.get(group_title) if group_title else None # Может быть None


        # Если какая-то из обязательных справочных записей не нашлась (что не должно произойти после fill_spr)
        if not discipline_spr or not type_record_spr or not period_spr or not control_type_spr or not measure_spr or not block_spr:
             logger.error(f"     - CRITICAL: Lookup failed for essential data after fill_spr. Skipping row for discipline '{discipline_title}'.")
             continue

        # Определение ID для вставки
        id_discipline_val = discipline_spr.id
        id_type_record_val = type_record_spr.id
        id_period_val = period_spr.id
        id_control_type_val = control_type_spr.id
        id_measure_val = measure_spr.id
        id_block_val = block_spr.id
        id_part_val = part_spr.id if part_spr else None # ID Части может быть None

        # Определение ID Модуля и Группы с fallback
        module_to_use_id = module_spr.id if module_spr else session.query(D_Modules.id).filter_by(title="Без названия").scalar() # Default 'Без названия' ID
        if module_to_use_id is None: module_to_use_id = session.query(D_Modules).get(19).id if session.query(D_Modules).get(19) else None # Fallback to ID 19

        group_to_use_id = group_spr.id_group if group_spr else session.query(Groups.id_group).filter_by(name_group="Основные").scalar() # Default 'Основные' ID
        if group_to_use_id is None: group_to_use_id = session.query(Groups).get(1).id_group if session.query(Groups).get(1) else None # Fallback to ID 1

        # Попытка переопределить модуль "Без названия" на основе маппинга
        if module_spr and module_spr.title == "Без названия" and use_other_modules and id_discipline_val in modules_mapping:
            mapped_module_id = modules_mapping[id_discipline_val]
            mapped_module = session.query(D_Modules).get(mapped_module_id)
            if mapped_module:
                 logger.debug(f"       - Overriding module 'Без названия' with '{mapped_module.title}' (ID: {mapped_module_id}) for discipline ID {id_discipline_val}.")
                 module_to_use_id = mapped_module_id
            else:
                 logger.warning(f"       - Mapped module ID {mapped_module_id} not found for discipline ID {id_discipline_val}. Using 'Без названия'.")


        # Обработка числовых значений
        try: amount = int(round(float(row["Количество"]) * 100)) if pandas.notna(row["Количество"]) else 0
        except (ValueError, TypeError): logger.warning(f"     - Invalid 'Количество': {row['Количество']}. Setting amount=0."); amount = 0
        try: zet = int(round(float(row["ЗЕТ"]) * 100)) if pandas.notna(row["ЗЕТ"]) else 0
        except (ValueError, TypeError): logger.warning(f"     - Invalid 'ЗЕТ': {row['ЗЕТ']}. Setting ZET=0."); zet = 0

        # Получение num_row
        num_row_val = num_rows.get((period_title, discipline_title)) if period_title and discipline_title else None
        if num_row_val is None:
            logger.warning(f"     - Could not determine num_row for discipline '{discipline_title}' in period '{period_title}'. Skipping row.")
            continue


        aup_data = AupData(
            id_aup=aup_info.id_aup, id_block=id_block_val, shifr=str(row["Шифр"]),
            id_part=id_part_val, id_module=module_to_use_id, id_group=group_to_use_id,
            id_type_record=id_type_record_val, id_discipline=id_discipline_val,
            _discipline=discipline_title, id_period=id_period_val,
            num_row=num_row_val,
            id_type_control=id_control_type_val, amount=amount, id_edizm=id_measure_val, zet=zet,
            used_for_report=False
        )
        instances.append(aup_data)
    logger.debug(f"   Finished preparing {len(instances)} AupData entries.")
    return instances


@timeit
def fill_spr_from_aup_data_values(values, model, session: Session = db.session, **kwargs) -> Dict[str, Any]:
    """Наполняет справочную таблицу и возвращает словарь {название: объект_модели}."""
    model_name = model.__name__
    title_field_attr, title_field_name = None, None
    possible_fields = ['title', 'name'] + [c.name for c in model.__table__.columns if c.name.startswith('name_')]
    for field_name in possible_fields:
        if hasattr(model, field_name):
            title_field_attr = getattr(model, field_name); title_field_name = field_name; break
    else: raise AttributeError(f"Model {model_name} needs 'title', 'name', or 'name_*' field.")

    cleaned_values = [str(el).strip() for el in values if pandas.notna(el) and str(el).strip()]
    unique_values = list(set(cleaned_values))
    if not unique_values: return {}

    existing_instances_q = session.query(model).filter(title_field_attr.in_(unique_values)).all()
    existing_instances = {getattr(el, title_field_name): el for el in existing_instances_q}
    # logger.debug(f"     - Found {len(existing_instances)} existing entries in {model_name}.")

    created_instances_data = []
    for val in unique_values:
        if val not in existing_instances:
            created_instances_data.append({title_field_name: val, **kwargs})

    if created_instances_data:
        # logger.debug(f"     - Adding {len(created_instances_data)} new entries to {model_name}.")
        try:
            session.bulk_insert_mappings(model, created_instances_data)
            session.flush() # Важно для ID
            newly_created_instances = session.query(model).filter(title_field_attr.in_([data[title_field_name] for data in created_instances_data])).all()
            for el in newly_created_instances: existing_instances[getattr(el, title_field_name)] = el
            # logger.debug(f"     - Successfully flushed {len(newly_created_instances)} new entries for {model_name}.")
        except IntegrityError as e:
            # session.rollback() # Не делаем rollback здесь
            logger.error(f"Integrity error during bulk insert for {model_name}: {e}. Trying one by one.")
            failed_inserts = 0
            for data in created_instances_data:
                 if data[title_field_name] not in existing_instances:
                     try:
                         with session.begin_nested(): # Используем savepoint
                             instance = model(**data)
                             session.add(instance)
                             session.flush()
                             existing_instances[data[title_field_name]] = instance
                     except IntegrityError:
                         logger.warning(f"     - Duplicate skipped on single insert for {model_name}: {data[title_field_name]}")
                         conflicting = session.query(model).filter(title_field_attr == data[title_field_name]).first()
                         if conflicting: existing_instances[data[title_field_name]] = conflicting
                         else: failed_inserts+=1; logger.error(f"     - Could not retrieve conflicting {model_name}: {data[title_field_name]}")
                     except Exception as single_e: logger.error(f"     - Error on single insert for {model_name} ({data[title_field_name]}): {single_e}"); failed_inserts+=1
            if failed_inserts > 0: logger.error(f"     - Failed to insert {failed_inserts} entries for {model_name}.")
        except Exception as e:
            # session.rollback() # Не делаем rollback здесь
            logger.error(f"Unexpected error during bulk insert for {model_name}: {e}")
            traceback.print_exc()
    return existing_instances

@timeit
def fill_groups_from_aup_data_values(values: List[str], session: Session = db.session) -> Dict[str, Groups]:
    """Наполняет справочник Groups и возвращает словарь {name_group: group_instance}."""
    return fill_spr_from_aup_data_values(values, Groups, session, color="#5f60ec", weight=5) # Используем общий хелпер


def _delete_aup_dependencies(aup_id: int, session: Session) -> None:
    """Удаляет все данные, зависящие от AUP, КРОМЕ САМОГО AupInfo."""
    logger.debug(f"Deleting dependencies for AUP ID: {aup_id}")
    # 1. Удаление связей в матрице компетенций
    aup_data_ids = [ad.id for ad in session.query(AupData.id).filter_by(id_aup=aup_id).all()]
    if aup_data_ids:
        deleted_matrix_count = session.query(CompetencyMatrix).filter(CompetencyMatrix.aup_data_id.in_(aup_data_ids)).delete(synchronize_session='fetch')
        logger.debug(f"   - Deleted {deleted_matrix_count} entries in CompetencyMatrix.")
    # 2. Удаление связей AUP с Образовательными Программами
    deleted_ep_aup_count = session.query(EducationalProgramAup).filter_by(aup_id=aup_id).delete(synchronize_session='fetch')
    logger.debug(f"   - Deleted {deleted_ep_aup_count} entries in EducationalProgramAup.")
    # 3. Удаление таблиц DisciplineTable (модуль cabinet)
    deleted_dt_count = session.query(DisciplineTable).filter_by(id_aup=aup_id).delete(synchronize_session='fetch')
    logger.debug(f"   - Deleted {deleted_dt_count} entries in DisciplineTable.")
    # 4. Удаление AupData записей
    deleted_ad_count = session.query(AupData).filter_by(id_aup=aup_id).delete(synchronize_session='fetch')
    logger.debug(f"   - Deleted {deleted_ad_count} entries in AupData.")
    # 5. Удаление записей из таблицы Weeks
    if 'Weeks' in globals() and hasattr(Weeks, 'query'): # Проверка на существование модели и атрибута query
        deleted_weeks_count = session.query(Weeks).filter_by(aup_id=aup_id).delete(synchronize_session='fetch')
        logger.debug(f"   - Deleted {deleted_weeks_count} entries in Weeks.")
    logger.debug(f"Deletion of dependencies for AUP ID {aup_id} completed.")

def delete_aup_by_num(aup_num: str, session: Session) -> bool:
    """Централизованная функция для удаления AUP по его номеру."""
    logger.info(f"Attempting to delete AUP with number: {aup_num}")
    if not aup_num:
        logger.warning(f"No AUP number provided for deletion.")
        return False
    aup_info = session.query(AupInfo).filter_by(num_aup=str(aup_num)).first()
    if not aup_info: logger.warning(f"AUP {aup_num} not found for deletion."); return False
    try:
        aup_id = aup_info.id_aup
        _delete_aup_dependencies(aup_id, session) # Удаляем зависимости
        session.delete(aup_info) # Удаляем сам AUP
        # НЕ делаем flush или commit здесь, это должно быть снаружи
        logger.info(f"Successfully marked AUP {aup_num} (ID: {aup_id}) and dependencies for deletion.")
        return True
    except Exception as e:
        # session.rollback() # Откат делается снаружи
        logger.error(f"Error deleting AUP {aup_num}: {e}")
        traceback.print_exc()
        raise e # Перебрасываем

@timeit
def get_num_rows(data: DataFrame) -> dict[tuple[str, str], int]:
    """Определяет порядок строк дисциплин внутри каждого периода контроля."""
    default_weight=5; weights={"Проектная деятельность":10,"Введение в проектную деятельность":10,"Управление проектами":10,"Иностранный язык":1,}; periods={};
    for _,row in data.iterrows():
        period=str(row["Период контроля"]).strip() if pandas.notna(row["Период контроля"]) else "N/A"; discipline=str(row["Дисциплина"]).strip() if pandas.notna(row["Дисциплина"]) else "N/A"; # Исправлено pandas.na на pandas.notna
        if period=="N/A" or discipline=="N/A": continue;
        weight=weights.get(discipline,default_weight); value=(discipline,weight);
        if period not in periods: periods[period]=[value];
        else:
            if not any(item[0] == discipline for item in periods[period]): periods[period].append(value);
    res={};
    for period,disciplines_with_weights in periods.items():
        disciplines_with_weights.sort(key=lambda x:(-x[1],x[0]));
        for i,(discipline,_) in enumerate(disciplines_with_weights,start=1): res[(period,discipline)]=i;
    return res

@timeit
def get_discipline_module_mapper(session: Session = db.session) -> dict[int, int]:
    """Создает маппинг {id_discipline: id_module}."""
    from collections import defaultdict, Counter; logger.debug("   Generating discipline-module mapping...");
    query_result=(session.query(AupData.id_discipline,AupData.id_module).join(D_Modules,AupData.id_module==D_Modules.id).filter(AupData.id_discipline.isnot(None),AupData.id_module.isnot(None)).distinct().all());
    logger.debug(f"     - Found {len(query_result)} potential discipline-module links.");
    grouped_modules=defaultdict(list);
    for id_discipline,id_module in query_result: grouped_modules[id_discipline].append(id_module);
    result_mapping={};
    for id_discipline,module_ids in grouped_modules.items():
        if not module_ids: continue;
        count=Counter(module_ids); most_frequent_module_id=max(count.items(),key=lambda item:item[1])[0]; result_mapping[id_discipline]=most_frequent_module_id;
    logger.debug(f"   - Generated mapping for {len(result_mapping)} disciplines."); return result_mapping