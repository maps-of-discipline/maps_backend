# competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
import traceback
import logging

from flask import current_app # Для доступа к конфигурации
from sqlalchemy import create_engine, select, exists, and_, or_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError # Добавляем IntegrityError
from sqlalchemy.orm import Session, aliased, joinedload, selectinload # Добавляем selectinload

# --- Импортируем модели из maps.models (локальная БД) ---
from maps.models import db as local_db, SprDiscipline, AupInfo as LocalAupInfo, AupData # Добавляем AupData

# --- Импортируем НАШИ модели компетенций ---
from .models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramAup, EducationalProgramPs,
    CompetencyType, IndicatorPsLink,
    # Модели структуры ПС (нужны для сохранения)
    GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
)
# --- Импортируем НАШИ внешние модели ---
from .external_models import (
    ExternalAupInfo,
    ExternalNameOP,
    ExternalSprOKCO,
    ExternalSprFormEducation,
    ExternalSprDegreeEducation,
    ExternalAupData,
    ExternalSprDiscipline, # Добавляем ExternalSprDiscipline
    ExternalSprFaculty, # Добавлено для поиска
    ExternalDepartment # Добавлено для поиска
)

# --- Импортируем парсеры ---
from .fgos_parser import parse_fgos_pdf
# from .parsers import parse_prof_standard_file # Переименовано в parse_prof_standard_uploaded_file


# Настройка логирования
logger = logging.getLogger(__name__)

# --- Глобальная переменная для движка внешней БД (инициализируется один раз) ---
_external_db_engine = None

def get_external_db_engine():
    """Инициализирует и возвращает движок для внешней БД КД."""
    global _external_db_engine
    if _external_db_engine is None:
        db_url = current_app.config.get('EXTERNAL_KD_DATABASE_URL')
        if not db_url:
            logger.error("EXTERNAL_KD_DATABASE_URL is not configured.")
            raise RuntimeError("EXTERNAL_KD_DATABASE_URL is not configured.")
        try:
            _external_db_engine = create_engine(db_url)
            logger.info("External DB Engine for KD initialized.")
        except Exception as e:
            logger.error(f"Failed to create external DB engine: {e}", exc_info=True)
            raise RuntimeError(f"Failed to create external DB engine: {e}")
    return _external_db_engine

# --- Функции для получения данных для отображения ---

def get_educational_programs_list() -> List[EducationalProgram]:
    """
    Получает список всех образовательных программ из БД.

    Returns:
        List[EducationalProgram]: Список объектов SQLAlchemy EducationalProgram.
    """
    try:
        # Используем joinedload для предзагрузки первого AUP
        # Это может ускорить отображение списка, если первый_aup_id используется на фронте
        # EducationalProgram.query будет использовать сессию от local_db
        programs = EducationalProgram.query.options(
             joinedload(EducationalProgram.aup_assoc).joinedload(EducationalProgramAup.aup)
        ).order_by(EducationalProgram.title).all()
        return programs
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_educational_programs_list: {e}")
        return [] # Возвращаем пустой список в случае ошибки

def get_program_details(program_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает детальную информацию по ОП, включая связанные сущности.

    Args:
        program_id: ID образовательной программы.

    Returns:
        Optional[Dict[str, Any]]: Словарь с данными программы или None, если не найдена.
                                   Структура должна включать детали ФГОС, список АУП,
                                   список выбранных и рекомендованных ПС.
    """
    try:
        # EducationalProgram.query будет использовать сессию от local_db
        program = EducationalProgram.query.options(
            selectinload(EducationalProgram.fgos),
            selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
            selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard)
        ).get(program_id)

        if not program:
            logger.warning(f"Program with id {program_id} not found for details.")
            return None

        details = {
            'id': program.id,
            'title': program.title,
            'code': program.code,
            'profile': program.profile,
            'qualification': program.qualification,
            'form_of_education': program.form_of_education,
            'enrollment_year': program.enrollment_year,
            'fgos_vo_id': program.fgos_vo_id,
            'created_at': program.created_at.isoformat() if program.created_at else None,
            'updated_at': program.updated_at.isoformat() if program.updated_at else None
        }

        if program.fgos:
            details['fgos_details'] = {
                'id': program.fgos.id,
                'number': program.fgos.number,
                'date': program.fgos.date.isoformat() if program.fgos.date else None,
                'direction_code': program.fgos.direction_code,
                'direction_name': program.fgos.direction_name,
                'education_level': program.fgos.education_level,
                'generation': program.fgos.generation,
                'file_path': program.fgos.file_path
            }
        else:
            details['fgos_details'] = None
            
        details['aup_list'] = []
        if program.aup_assoc:
            # .aup here refers to LocalAupInfo due to the aliased import
            details['aup_list'] = [
                {
                    'id_aup': assoc.aup.id_aup,
                    'num_aup': assoc.aup.num_aup,
                    'file': assoc.aup.file,
                    'is_primary': assoc.is_primary # Добавляем флаг is_primary
                } 
                for assoc in program.aup_assoc if assoc.aup
            ]
        
        details['selected_ps_list'] = []
        if program.selected_ps_assoc:
            details['selected_ps_list'] = [
                {
                    'id': assoc.prof_standard.id,
                    'code': assoc.prof_standard.code,
                    'name': assoc.prof_standard.name
                }
                for assoc in program.selected_ps_assoc if assoc.prof_standard
            ]

        recommended_ps_list = []
        if program.fgos and program.fgos.recommended_ps_assoc:
            for assoc in program.fgos.recommended_ps_assoc:
                if assoc.prof_standard:
                    recommended_ps_list.append({
                        'id': assoc.prof_standard.id,
                        'code': assoc.prof_standard.code,
                        'name': assoc.prof_standard.name
                    })
                    
        details['recommended_ps_list'] = recommended_ps_list

        return details
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_program_details for program_id {program_id}: {e}")
        return None
    except AttributeError as e:
        logger.error(f"Attribute error likely due to missing relationship/data in get_program_details for program_id {program_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_program_details for program_id {program_id}: {e}", exc_info=True)
        return None


def get_external_aups_list(
    program_code: Optional[str] = None,
    profile_num: Optional[str] = None, 
    profile_name: Optional[str] = None,
    form_education_name: Optional[str] = None,
    year_beg: Optional[int] = None,
    degree_education_name: Optional[str] = None,
    search_query: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = 20
) -> Dict[str, Any]:
    """
    Получает список АУП из внешней БД КД по заданным параметрам.
    """
    engine = get_external_db_engine()
    with Session(engine) as session:
        try:
            query = session.query(ExternalAupInfo).options(
                joinedload(ExternalAupInfo.spec).joinedload(ExternalNameOP.okco),
                joinedload(ExternalAupInfo.form),
                joinedload(ExternalAupInfo.degree),
                joinedload(ExternalAupInfo.faculty),
                joinedload(ExternalAupInfo.department)
            )

            filters = []
            
            # SQLAlchemy обычно достаточно умен, чтобы не дублировать JOIN, можно вызывать join при необходимости.
            # Но явное добавление join() может улучшить читаемость и контроль за генерацией SQL.
            # Если фильтры зависят от joined-таблиц, join() должен быть вызван ДО добавления фильтра.

            if program_code:
                filters.append(ExternalSprOKCO.program_code == program_code)
            
            profile_filters_or = []
            if profile_num:
                profile_filters_or.append(ExternalNameOP.num_profile == profile_num)
            if profile_name:
                profile_filters_or.append(ExternalNameOP.name_spec.ilike(f"%{profile_name}%"))
            
            if profile_filters_or:
                 filters.append(or_(*profile_filters_or))

            if form_education_name:
                filters.append(ExternalSprFormEducation.form == form_education_name)
                
            if year_beg:
                filters.append(ExternalAupInfo.year_beg == year_beg)
                
            if degree_education_name:
                filters.append(ExternalSprDegreeEducation.name_deg == degree_education_name)

            # Добавляем OUTER JOIN для полей, которые могут отсутствовать, но используются в search_query или фильтрах
            query = query.join(ExternalAupInfo.spec, isouter=True)\
                         .join(ExternalNameOP.okco, isouter=True) # Джойнимся от NameOP, т.к. NameOP может не быть
            query = query.join(ExternalAupInfo.form, isouter=True)
            query = query.join(ExternalAupInfo.degree, isouter=True)
            query = query.join(ExternalAupInfo.faculty, isouter=True)
            query = query.join(ExternalAupInfo.department, isouter=True)


            if filters:
                query = query.filter(and_(*filters))

            if search_query:
                 search_pattern = f"%{search_query}%"
                 search_conditions = [
                     ExternalAupInfo.num_aup.ilike(search_pattern),
                     ExternalNameOP.name_spec.ilike(search_pattern), 
                     ExternalSprOKCO.program_code.ilike(search_pattern), 
                     ExternalSprFaculty.name_faculty.ilike(search_pattern), 
                     ExternalDepartment.name_department.ilike(search_pattern), 
                 ]
                 query = query.filter(or_(*search_conditions))

            total_count = query.count()
            # Сортировка по year_beg (убывание) затем по num_aup
            query = query.order_by(ExternalAupInfo.year_beg.desc(), ExternalAupInfo.num_aup)
            if limit is not None: query = query.offset(offset).limit(limit)
            external_aups = query.all()
            result_items = [aup.as_dict() for aup in external_aups]

            logger.info(f"Fetched {len(result_items)} of {total_count} AUPs from external KD DB.")
            return {"total": total_count, "items": result_items}

        except Exception as e:
            logger.error(f"Error fetching external AUPs: {e}", exc_info=True)
            raise

def get_external_aup_disciplines(aup_id: int) -> List[Dict[str, Any]]:
    """
    Получает список дисциплин (AupData) для конкретного АУП из внешней БД КД.
    """
    engine = get_external_db_engine()
    with Session(engine) as session:
        try:
            # Запрос к ExternalAupData по id_aup
            aup_data_entries = session.query(ExternalAupData).options(
                # joinedload(ExternalAupData.spr_discipline) # Если spr_discipline определена в external_models
            ).filter(ExternalAupData.id_aup == aup_id).order_by(ExternalAupData.id_period, ExternalAupData.shifr, ExternalAupData.id).all()

            result = []
            for entry in aup_data_entries:
                 result.append({
                     'aup_data_id': entry.id, # ЭТО ID из внешней БД aup_data
                     'id_aup': entry.id_aup, # ЭТО ID AUP из внешней БД tbl_aup
                     'discipline_id': entry.id_discipline,
                     'title': entry.discipline,
                     'semester': entry.id_period,
                     'shifr': entry.shifr,
                     'id_type_record': entry.id_type_record,
                     # ИСПРАВЛЕНИЕ ЗЕТ: Проверяем на None перед делением и присваиваем 0 если None
                     'zet': (entry.zet / 100) if entry.zet is not None else 0,
                     'amount': entry.amount,
                     'id_type_control': entry.id_type_control
                 })

            logger.info(f"Fetched {len(result)} AupData entries for external AUP ID {aup_id} from external KD DB.")
            return result

        except Exception as e:
            logger.error(f"Error fetching external AupData for external AUP ID {aup_id}: {e}", exc_info=True)
            # Пробрасываем ошибку, чтобы вызывающий код мог ее обработать (например, вернуть 500 или 404)
            raise


def get_matrix_for_aup(aup_num: str) -> Optional[Dict[str, Any]]:
    logger.info(f"get_matrix_for_aup: Processing request for AUP num: {aup_num}")
    session: Session = local_db.session
    matrix_response: Dict[str, Any] = {
        "aup_info": None,
        "disciplines": [], # Заполняется данными ИЗ ВНЕШНЕЙ БД (ExternalAupData as dict)
        "competencies": [], # Заполняется данными ИЗ ЛОКАЛЬНОЙ БД (Competency as dict)
        "links": [], # Заполняется данными ИЗ ЛОКАЛЬНОЙ БД (CompetencyMatrix as dict)
        "suggestions": [], # Заглушка для NLP
        "external_aup_id": None, # ID AUP из внешней БД tbl_aup (используется для запроса дисциплин)
        "external_aup_num": aup_num, # Num AUP, который запросил клиент
        "source": "not_found", # local_only, external_only, local_with_external_disciplines, not_found
        "error_details": None # Сообщения об ошибках загрузки
    }

    local_aup_info_entry: Optional[LocalAupInfo] = None
    educational_program: Optional[EducationalProgram] = None
    fgos: Optional[FgosVo] = None
    
    # --- Шаг 1: Поиск локальной записи AupInfo ---
    try:
        local_aup_info_entry = session.query(LocalAupInfo).options(
            selectinload(LocalAupInfo.education_programs_assoc)
                .selectinload(EducationalProgramAup.educational_program)
                .selectinload(EducationalProgram.fgos)
        ).filter_by(num_aup=aup_num).first()

        if local_aup_info_entry:
            logger.info(f"   - Found LocalAupInfo (ID: {local_aup_info_entry.id_aup}) for num_aup: {aup_num}.")
            # Заполняем локальные метаданные сразу
            matrix_response["aup_info"] = local_aup_info_entry.as_dict()
            
            # Определяем связанную ОП и ФГОС
            if local_aup_info_entry.education_programs_assoc:
                primary_assoc = next((assoc for assoc in local_aup_info_entry.education_programs_assoc if assoc.is_primary), None)
                assoc_to_use = primary_assoc or (local_aup_info_entry.education_programs_assoc[0] if local_aup_info_entry.education_programs_assoc else None)
                if assoc_to_use and assoc_to_use.educational_program:
                    educational_program = assoc_to_use.educational_program
                    logger.info(f"     - Linked EducationalProgram (ID: {educational_program.id}) found.")
                    if educational_program.fgos:
                        fgos = educational_program.fgos
                        logger.info(f"     - Linked FGOS (ID: {fgos.id}, Code: {fgos.direction_code}) found.")
                    else:
                        logger.warning(f"     - EducationalProgram (ID: {educational_program.id}) is not linked to an FGOS.")
            else:
                 logger.warning(f"     - LocalAupInfo (ID: {local_aup_info_entry.id_aup}) is not linked to any EducationalProgram.")
        else:
            logger.warning(f"   - LocalAupInfo for num_aup '{aup_num}' not found.")

    except Exception as e_local_aup:
        logger.error(f"   - Error finding LocalAupInfo for num_aup '{aup_num}': {e_local_aup}", exc_info=True)
        matrix_response["error_details"] = (matrix_response["error_details"] or "") + f" Ошибка при поиске локальной записи АУП {aup_num}: {e_local_aup}."
        # Не пробрасываем ошибку, продолжаем, чтобы попробовать загрузить дисциплины

    # --- Шаг 2: Поиск external_aup_id в КД по aup_num и загрузка дисциплин ---
    external_disciplines: List[Dict[str, Any]] = []
    external_aup_info_from_kd_search: Optional[Dict[str, Any]] = None
    external_aup_id_for_disciplines: Optional[int] = None

    try:
        logger.debug(f"   - Searching external KD for AUP with num_aup '{aup_num}' to get external_aup_id for disciplines...")
        # Используем тот же API, что и фронтенд для поиска АУП, но ищем конкретный num_aup
        # Устанавливаем limit=1, т.к. нам нужен только один AUP с таким номером
        external_aup_search_result = get_external_aups_list(search_query=aup_num, limit=1)

        if external_aup_search_result["total"] > 0 and external_aup_search_result["items"]:
            # Убедимся, что найденный АУП действительно имеет тот же num_aup, что и искали
            # Это важно, т.к. search_query может вернуть похожие, а не точные совпадения
            exact_match_aup = next((item for item in external_aup_search_result["items"] if item.get('num_aup') == aup_num), None)
            
            if exact_match_aup:
                external_aup_info_from_kd_search = exact_match_aup
                external_aup_id_for_disciplines = external_aup_info_from_kd_search.get('id_aup')
                matrix_response["external_aup_id"] = external_aup_id_for_disciplines # Сохраняем найденный внешний ID
                matrix_response["external_aup_num"] = external_aup_info_from_kd_search.get('num_aup', aup_num) # Сохраняем num_aup из КД

                if not local_aup_info_entry: # Если локальный AupInfo не был найден
                     matrix_response["aup_info"] = external_aup_info_from_kd_search # Используем метаданные из КД

                if external_aup_id_for_disciplines is not None:
                     logger.debug(f"     - Found exact AUP match in external KD with num_aup '{aup_num}'. External ID for disciplines: {external_aup_id_for_disciplines}.")
                     external_disciplines = get_external_aup_disciplines(external_aup_id_for_disciplines)
                     matrix_response["disciplines"] = external_disciplines # <-- ПОПУЛЯЦИЯ matrix_response["disciplines"]
                     logger.info(f"     - Fetched {len(external_disciplines)} discipline entries from external KD for external AUP ID: {external_aup_id_for_disciplines}.")
                else:
                     logger.warning(f"     - External AUP '{aup_num}' found, but its external ID is missing. Cannot fetch disciplines.")
                     matrix_response["error_details"] = (matrix_response["error_details"] or "") + f" Внешний АУП {aup_num} найден, но его ID отсутствует в КД. Дисциплины не загружены."
            else:
                logger.warning(f"   - AUP with num_aup '{aup_num}' not found as an exact match in external KD search results. Disciplines will be empty.")
                matrix_response["error_details"] = (matrix_response["error_details"] or "") + f" АУП {aup_num} не найден (точное совпадение) во внешней БД Карт Дисциплин. Дисциплины не загружены."
        else:
            logger.warning(f"   - AUP with num_aup '{aup_num}' not found in external KD by num_aup search. Disciplines will be empty.")
            matrix_response["error_details"] = (matrix_response["error_details"] or "") + f" АУП {aup_num} не найден во внешней БД Карт Дисциплин. Дисциплины не загружены."

    except Exception as e_ext_disciplines:
        logger.error(f"   - Error during external KD lookup/discipline fetch for num_aup '{aup_num}': {e_ext_disciplines}", exc_info=True)
        matrix_response["error_details"] = (matrix_response["error_details"] or "") + f" Ошибка при загрузке дисциплин АУП {aup_num} из внешней БД: {e_ext_disciplines}."
        # Не пробрасываем ошибку, продолжаем загрузку локальных компетенций

    # --- Шаг 3: Загрузка локальных данных компетенций и связей ---
    if local_aup_info_entry:
        matrix_response["source"] = "local_with_external_disciplines" if external_disciplines else "local_no_external_disciplines"

        comp_types_q = session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК', 'ПК'])).all()
        comp_types = {ct.code: ct for ct in comp_types_q}
        relevant_competencies = []
        if fgos:
            uk_type = comp_types.get('УК')
            opk_type = comp_types.get('ОПК')
            uk_opk_ids_to_load = [tid.id for tid in [uk_type, opk_type] if tid]
            if uk_opk_ids_to_load:
                uk_opk_competencies = session.query(Competency).options(
                    selectinload(Competency.indicators), selectinload(Competency.competency_type)
                ).filter(Competency.fgos_vo_id == fgos.id,
                         Competency.competency_type_id.in_(uk_opk_ids_to_load)).all()
                relevant_competencies.extend(uk_opk_competencies)
                logger.debug(f"     - Loaded {len(uk_opk_competencies)} УК/ОПК for FGOS {fgos.id}.")
        else:
            logger.warning(f"     - No FGOS linked to local AupInfo, skipping УК/ОПК for AUP num: {aup_num}")

        pk_type = comp_types.get('ПК')
        if pk_type:
            pk_competencies = session.query(Competency).options(
                selectinload(Competency.indicators), selectinload(Competency.competency_type)
            ).filter(Competency.competency_type_id == pk_type.id).all() # Загружаем ВСЕ ПК
            relevant_competencies.extend(pk_competencies)
            logger.debug(f"     - Loaded {len(pk_competencies)} ПК from local DB.")

        competencies_data = []
        all_indicator_ids_for_matrix = set()
        comp_type_sort_order = {ct.code: ct.id for ct in comp_types_q} # Для сортировки
        relevant_competencies.sort(key=lambda c: (comp_type_sort_order.get(c.competency_type.code, 999) if c.competency_type else 999, c.code))

        for comp in relevant_competencies:
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"
            comp_dict = comp.to_dict(rules=['-indicators', '-competency_type', '-fgos', '-based_on_labor_function', '-matrix_entries'])
            comp_dict['type_code'] = type_code
            comp_dict['indicators'] = []
            if comp.indicators:
                sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                for ind in sorted_indicators:
                    all_indicator_ids_for_matrix.add(ind.id)
                    ind_dict = ind.to_dict()
                    ind_dict['competency_code'] = comp.code # Добавляем ссылку на родительскую компетенцию
                    ind_dict['competency_name'] = comp.name
                    comp_dict['indicators'].append(ind_dict)
            competencies_data.append(comp_dict)
        matrix_response["competencies"] = competencies_data

        if external_disciplines and all_indicator_ids_for_matrix:
            external_aup_data_ids = [d['aup_data_id'] for d in external_disciplines if d.get('aup_data_id') is not None]
            if external_aup_data_ids:
                existing_links_db = session.query(CompetencyMatrix).filter(
                    CompetencyMatrix.aup_data_id.in_(external_aup_data_ids),
                    CompetencyMatrix.indicator_id.in_(list(all_indicator_ids_for_matrix))
                ).all()
                matrix_response["links"] = [link.to_dict(only=('aup_data_id', 'indicator_id', 'is_manual')) for link in existing_links_db]
                logger.debug(f"     - Loaded {len(matrix_response['links'])} matrix links from local DB (based on external discipline IDs).")
            else:
                 logger.debug("     - No valid external discipline IDs to load local links for.")
        else:
            logger.debug("     - No external disciplines loaded or no indicators for matrix, local links will be empty.")

    elif matrix_response["aup_info"]: # Локальный AupInfo НЕ найден, но найден внешний AUP в Шаге 2
        matrix_response["source"] = "external_only"
        logger.warning(f"   - LocalAupInfo with num_aup '{aup_num}' not found. Using data from external KD for aup_info field.")
        matrix_response["competencies"] = []
        matrix_response["links"] = []
        logger.warning("     - Matrix will be shown with external disciplines only. No local competencies/links.")
    else: # Ни локальный, ни внешний АУП не найдены
        matrix_response["source"] = "not_found"
        logger.error(f"   - AUP with num_aup '{aup_num}' not found in local DB. External search also failed or yielded no external_aup_id. Cannot proceed.")
        if not matrix_response["error_details"]: # Если еще нет деталей ошибки
            matrix_response["error_details"] = f"АУП {aup_num} не найден ни в локальной, ни во внешней базе данных, или не удалось определить ID для загрузки дисциплин."
        return None # Возвращаем None, чтобы routes.py вернул 404

    return matrix_response

# Остальные функции в logic.py остаются без изменений
# update_matrix_link
# create_competency, create_indicator
# parse_fgos_file, save_fgos_data, get_fgos_list, get_fgos_details, delete_fgos
# parse_prof_standard_file, save_prof_standard_data
# get_prof_standards_list, get_prof_standard_details (TODO)
# _prepare_ps_structure, _prepare_all_lookups, etc.

def update_matrix_link(aup_data_id: int, indicator_id: int, create: bool = True) -> Dict[str, Any]:
    """
    Создает или удаляет связь Дисциплина(АУП)-ИДК в матрице.
    (Версия с подробным возвратом статуса)
    CompetencyMatrix.aup_data_id теперь хранит ID из ВНЕШНЕЙ БД aup_data.
    """
    session: Session = local_db.session # Используем local_db
    try:
        # AupData check is now against external data, so we can't check it here directly
        # unless we query the external DB or assume aup_data_id is valid.
        # For now, we only check Indicator existence in local DB.
        # The responsibility of providing a valid aup_data_id (from external source) is on the client.

        indicator_exists = session.query(exists().where(Indicator.id == indicator_id)).scalar()
        if not indicator_exists:
            message = f"update_matrix_link: Indicator with id {indicator_id} not found."
            logger.warning(message)
            return {
                'success': False,
                'status': 'error',
                'message': message,
                'error_type': 'indicator_not_found'
            }
        
        # We no longer check AupData existence here as it's external.
        # The original check was:
        # aup_data_exists = session.query(exists().where(AupData.id == aup_data_id)).scalar()
        # if not aup_data_exists: ... return error ...

        existing_link = session.query(CompetencyMatrix).filter_by(
            aup_data_id=aup_data_id, # This aup_data_id is from the external system
            indicator_id=indicator_id
        ).first()

        if create:
            if not existing_link:
                link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
                session.add(link)
                session.commit()
                message = f"Link created: External AupData ID {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return {
                    'success': True,
                    'status': 'created',
                    'message': message
                }
            else:
                message = f"Link already exists: External AupData ID {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return {
                    'success': True,
                    'status': 'already_exists',
                    'message': message
                }
        else: # delete
            if existing_link:
                session.delete(existing_link)
                session.commit()
                message = f"Link deleted: External AupData ID {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return {
                    'success': True,
                    'status': 'deleted',
                    'message': message
                }
            else:
                message = f"Link not found for deletion: External AupData ID {aup_data_id} <-> Indicator {indicator_id}"
                logger.warning(message)
                return {
                    'success': True,
                    'status': 'not_found',
                    'message': message
                }

    except SQLAlchemyError as e:
        session.rollback()
        message = f"Database error in update_matrix_link: {e}"
        logger.error(message, exc_info=True)
        return {
            'success': False,
            'status': 'error',
            'message': message,
            'error_type': 'database_error'
        }
    except Exception as e:
        session.rollback()
        message = f"Unexpected error in update_matrix_link: {e}"
        logger.error(message, exc_info=True)
        return {
            'success': False,
            'status': 'error',
            'message': message,
            'error_type': 'unexpected_error',
            'details': str(e)
        }


def create_competency(data: Dict[str, Any]) -> Optional[Competency]:
    """
    Создает новую компетенцию (обычно ПК). Базовая реализация для MVP.
    """
    required_fields = ['type_code', 'code', 'name']
    if not all(field in data for field in required_fields):
        logger.warning("Missing required fields for competency creation.")
        return None

    try:
        session: Session = local_db.session # Используем local_db
        comp_type = session.query(CompetencyType).filter_by(code=data['type_code']).first()
        if not comp_type:
            logger.warning(f"Competency type with code {data['type_code']} not found.")
            return None

        existing_comp = session.query(Competency).filter_by(
             code=data['code'],
             competency_type_id=comp_type.id
        ).first()
        if existing_comp:
             logger.warning(f"Competency with code {data['code']} and type {data['type_code']} already exists.")
             return None

        competency = Competency(
            competency_type_id=comp_type.id,
            code=data['code'],
            name=data['name'],
            description=data.get('description'),
        )
        session.add(competency)
        session.commit()
        logger.info(f"Competency created: {competency.code} (ID: {competency.id})")
        return competency
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error creating competency: {e}", exc_info=True)
        return None
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error creating competency: {e}", exc_info=True)
        return None

def create_indicator(data: Dict[str, Any]) -> Optional[Indicator]:
    """
    Создает новый индикатор (ИДК). Базовая реализация для MVP.
    """
    required_fields = ['competency_id', 'code', 'formulation']
    if not all(field in data for field in required_fields):
        logger.warning("Missing required fields for indicator creation.")
        return None

    try:
        session: Session = local_db.session # Используем local_db
        competency = session.query(Competency).get(data['competency_id'])
        if not competency:
            logger.warning(f"Parent competency with id {data['competency_id']} not found.")
            return None

        existing_indicator = session.query(Indicator).filter_by(
             code=data['code'],
             competency_id=data['competency_id']
        ).first()
        if existing_indicator:
             logger.warning(f"Indicator with code {data['code']} for competency {data['competency_id']} already exists.")
             return None

        indicator = Indicator(
            competency_id=data['competency_id'],
            code=data['code'],
            formulation=data['formulation'],
            source=data.get('source')
        )
        session.add(indicator)
        session.commit()
        logger.info(f"Indicator created: {indicator.code} (ID: {indicator.id}) for competency {indicator.competency_id}")
        return indicator
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error creating indicator: {e}", exc_info=True)
        return None
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error creating indicator: {e}", exc_info=True)
        return None

# --- Функции для работы с ФГОС ---

def parse_fgos_file(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    """
    Оркестрирует парсинг загруженного файла ФГОС ВО.
    Вызывает parse_fgos_pdf из fgos_parser.py.
    """
    try:
        # parse_fgos_pdf уже логирует ошибки парсинга
        parsed_data = parse_fgos_pdf(file_bytes, filename)
        if not parsed_data or not parsed_data.get('metadata'): # УК/ОПК могут быть опциональны для MVP
             logger.warning(f"parse_fgos_file: Parsing failed or returned insufficient metadata for {filename}")
             # Здесь уже parse_fgos_pdf может выбросить ValueError, ловим и перебрасываем
             if not parsed_data: raise ValueError("Парсер вернул пустые данные.")
             if not parsed_data.get('metadata'): raise ValueError("Не удалось извлечь метаданные из файла ФГОС.")
             # Если нет УК/ОПК, это может быть не ошибка парсера, но проблема с файлом.
             # Решаем, считать ли это ошибкой парсинга или ошибкой содержимого.
             # Для MVP, если метаданные есть, считаем, что парсинг прошел, даже если нет УК/ОПК.
             logger.warning(f"parse_fgos_file: Extracted metadata but no UK/OPK found in {filename}. Metadata: {parsed_data.get('metadata')}")
        return parsed_data
    except ValueError as e:
        logger.error(f"parse_fgos_file: Parser ValueError for {filename}: {e}")
        # Перебрасываем ошибку парсинга
        raise e
    except Exception as e:
        logger.error(f"parse_fgos_file: Unexpected error parsing {filename}: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при парсинге файла ФГОС '{filename}': {e}")


def save_fgos_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[FgosVo]:
    """
    Сохраняет структурированные данные ФГОС из парсера в БД.
    Принимает сессию local_db.session. Управляет своей транзакцией (commit/rollback).
    """
    logger.info(f"save_fgos_data: Attempting to save data for FGOS from '{filename}'. force_update: {force_update}")
    if not parsed_data or not parsed_data.get('metadata'):
        logger.warning("save_fgos_data: No parsed data or metadata provided for saving.")
        return None

    metadata = parsed_data.get('metadata', {})
    fgos_number = metadata.get('order_number')
    fgos_date_obj = metadata.get('order_date') # Ожидаем Date object после парсинга
    fgos_direction_code = metadata.get('direction_code')
    fgos_education_level = metadata.get('education_level')
    fgos_generation = metadata.get('generation')
    fgos_direction_name = metadata.get('direction_name')

    if not all([fgos_number, fgos_date_obj, fgos_direction_code, fgos_education_level]):
        logger.error("save_fgos_data: Missing core metadata (number, date, code, level) from parsed data for saving.")
        # TODO: Вернуть более конкретный статус ошибки
        return None

    try:
        # Используем вложенную транзакцию (savepoint) для всей операции сохранения
        with session.begin_nested():
            existing_fgos = session.query(FgosVo).filter_by(
                direction_code=fgos_direction_code,
                education_level=fgos_education_level,
                number=fgos_number,
                date=fgos_date_obj
            ).first()

            fgos_vo = None # Переменная для объекта FgosVo, который будет сохранен/обновлен

            if existing_fgos:
                if force_update:
                    logger.info(f"save_fgos_data: Existing FGOS found ({existing_fgos.id}, code: {existing_fgos.direction_code}). Force update requested. Deleting old competencies and indicators...")
                    # Удаляем старые УК/ОПК/Индикаторы, связанные с этим ФГОС
                    session.query(Competency).filter_by(fgos_vo_id=existing_fgos.id).delete()
                    # CASCADE DELETE на Indicator сработает автоматически

                    # TODO: Удалить также старые связи FgosRecommendedPs

                    # Обновляем существующий объект FgosVo вместо создания нового
                    fgos_vo = existing_fgos
                    fgos_vo.direction_name = fgos_direction_name or 'Не указано'
                    fgos_vo.generation = fgos_generation
                    fgos_vo.file_path = filename
                    session.add(fgos_vo) # Добавляем в сессию для обновления
                    session.flush() # Получаем новый ID, если был удален и создан (хотя тут update)
                    logger.info(f"save_fgos_data: Existing FGOS ({fgos_vo.id}) updated.")

                else:
                    logger.warning(f"save_fgos_data: FGOS with same key data already exists ({existing_fgos.id}). Force update NOT requested. Skipping save.")
                    # TODO: Вернуть статус "уже существует"
                    return existing_fgos

            else: # Не существующий ФГОС - создаем новый
                fgos_vo = FgosVo(
                    number=fgos_number,
                    date=fgos_date_obj,
                    direction_code=fgos_direction_code,
                    direction_name=fgos_direction_name or 'Не указано',
                    education_level=fgos_education_level,
                    generation=fgos_generation,
                    file_path=filename
                )
                session.add(fgos_vo)
                session.flush() # Получаем ID нового объекта
                logger.info(f"save_fgos_data: New FgosVo object created with ID {fgos_vo.id} for {fgos_vo.direction_code}.")

            # Сохранение УК/ОПК и Индикаторов
            comp_types_map = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
            if not comp_types_map:
                 logger.error("save_fgos_data: CompetencyType (УК, ОПК) not found in DB. Cannot save competencies.")
                 # TODO: Вернуть ошибку
                 raise ValueError("CompetencyType (УК, ОПК) not found in DB.")

            saved_competencies_count = 0
            saved_indicators_count = 0
            all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])

            for parsed_comp in all_parsed_competencies:
                comp_code = parsed_comp.get('code')
                comp_name = parsed_comp.get('name')
                # Индикаторы не парсятся из PDF, они приходят из другого источника (seed_db)
                # Если парсер в будущем будет их извлекать, добавить логику сохранения здесь
                # parsed_indicators = parsed_comp.get('indicators', []) # <-- Из парсера

                if not comp_code or not comp_name:
                    logger.warning(f"save_fgos_data: Skipping competency due to missing code/name: {parsed_comp}")
                    continue

                comp_prefix = comp_code.split('-')[0].upper() # Приводим к верхнему регистру для надежности
                comp_type = comp_types_map.get(comp_prefix)

                if not comp_type:
                    logger.warning(f"save_fgos_data: Skipping competency {comp_code}: Competency type {comp_prefix} not found in DB.")
                    continue

                # Проверяем, существует ли компетенция с ТАКИМ ЖЕ КОДОМ И ТИПОМ для ЭТОГО ФГОС
                existing_comp_for_fgos = session.query(Competency).filter_by(
                     code=comp_code,
                     competency_type_id=comp_type.id,
                     fgos_vo_id=fgos_vo.id
                ).first()

                if existing_comp_for_fgos:
                     logger.warning(f"save_fgos_data: Competency {comp_code} (type {comp_type.code}) already exists for FGOS {fgos_vo.id}. Skipping creation/update for this competency.")
                     # TODO: В будущем можно обновлять название компетенции
                     continue

                # Создаем новую компетенцию
                competency = Competency(
                    competency_type_id=comp_type.id,
                    fgos_vo_id=fgos_vo.id,
                    code=comp_code,
                    name=comp_name,
                    # description=... (если парсер будет извлекать)
                )
                session.add(competency)
                session.flush() # Чтобы получить ID компетенции
                saved_competencies_count += 1
                logger.debug(f"save_fgos_data: Created Competency {competency.code} (ID: {competency.id}) for FGOS {fgos_vo.id}.")

                # Если индикаторы парсятся из PDF, сохранить их здесь
                # for parsed_ind in parsed_indicators:
                #     ind_code = parsed_ind.get('code')
                #     ind_formulation = parsed_ind.get('formulation')
                #     ... создание индикатора ...
                #     saved_indicators_count += 1

            logger.info(f"save_fgos_data: Saved {saved_competencies_count} competencies for FGOS {fgos_vo.id}.")
            # logger.info(f"save_fgos_data: Saved {saved_indicators_count} indicators for FGOS {fgos_vo.id} (if parsed).")

            # Сохранение рекомендованных ПС
            recommended_ps_codes = parsed_data.get('recommended_ps_codes', [])
            logger.info(f"save_fgos_data: Found {len(recommended_ps_codes)} potential recommended PS codes in parsed data for linking.")

            if recommended_ps_codes:
                 # Получаем существующие профстандарты из БД по найденным кодам
                 existing_prof_standards = session.query(ProfStandard).filter(ProfStandard.code.in_(recommended_ps_codes)).all()
                 ps_by_code = {ps.code: ps for ps in existing_prof_standards}

                 linked_ps_count = 0
                 for ps_code in recommended_ps_codes:
                    prof_standard = ps_by_code.get(ps_code)
                    if prof_standard:
                        # Проверяем, существует ли уже связь между этим ФГОС и этим ПС
                        existing_link = session.query(FgosRecommendedPs).filter_by(
                            fgos_vo_id=fgos_vo.id,
                            prof_standard_id=prof_standard.id
                        ).first()

                        if not existing_link:
                             # Создаем новую связь
                             link = FgosRecommendedPs(
                                 fgos_vo_id=fgos_vo.id,
                                 prof_standard_id=prof_standard.id,
                                 is_mandatory=False # По умолчанию считаем рекомендованным, не обязательным
                                 # description = ... (если парсер будет извлекать)
                             )
                             session.add(link)
                             linked_ps_count += 1
                             logger.debug(f"save_fgos_data: Created link FGOS {fgos_vo.id} <-> PS {prof_standard.code}.")
                        else:
                             logger.debug(f"save_fgos_data: Link between FGOS {fgos_vo.id} and PS {prof_standard.code} already exists. Skipping creation.")
                    else:
                        logger.warning(f"save_fgos_data: Recommended PS with code {ps_code} not found in DB. Skipping link creation for FGOS {fgos_vo.id}.")
                 logger.info(f"save_fgos_data: Queued {linked_ps_count} new recommended PS links for FGOS {fgos_vo.id}.")


            # Commit the nested transaction (savepoint)
            session.commit()
            logger.info(f"save_fgos_data: Changes for FGOS ID {fgos_vo.id} committed successfully.")
            return fgos_vo # Возвращаем сохраненный объект

    except IntegrityError as e:
        # Откат вложенной транзакции произойдет автоматически
        logger.error(f"save_fgos_data: Integrity error during save for FGOS from '{filename}': {e}", exc_info=True)
        # TODO: Вернуть более конкретную ошибку или статус "уже существует"
        return None
    except SQLAlchemyError as e:
        # Откат вложенной транзакции произойдет автоматически
        logger.error(f"save_fgos_data: Database error during save for FGOS from '{filename}': {e}", exc_info=True)
        # TODO: Вернуть более конкретную ошибку
        return None
    except Exception as e:
        # Откат вложенной транзакции произойдет автоматически
        logger.error(f"save_fgos_data: Unexpected error during save for FGOS from '{filename}': {e}", exc_info=True)
        # TODO: Вернуть более конкретную ошибку
        return None


def get_fgos_list() -> List[FgosVo]:
    """
    Получает список всех сохраненных ФГОС ВО.
    """
    try:
        # Используем local_db
        # Добавляем eager load для performance (если нужен тип/программа сразу)
        fgos_list = local_db.session.query(FgosVo).options(
            joinedload(FgosVo.educational_programs) # Загружаем связанные программы
        ).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()
        return fgos_list
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_fgos_list: {e}", exc_info=True)
        # При обращении к локальной БД нет необходимости в rollback, т.к. сессия управляется Flask
        return [] # Возвращаем пустой список в случае ошибки


def get_fgos_details(fgos_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает детальную информацию по ФГОС ВО.
    """
    try:
        session: Session = local_db.session

        # Используем joinedload/selectinload для предзагрузки связей
        fgos = session.query(FgosVo).options(
            selectinload(FgosVo.competencies).selectinload(Competency.indicators), # Загружаем компетенции и их индикаторы
            selectinload(FgosVo.competencies).selectinload(Competency.competency_type), # Загружаем тип компетенции
            selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard) # Загружаем связи с ПС и сами ПС
        ).get(fgos_id)

        if not fgos:
            logger.warning(f"get_fgos_details: FGOS with id {fgos_id} not found for details.")
            return None

        # Сериализация в словарь
        details = fgos.to_dict(rules=['-competencies', '-recommended_ps_assoc', '-educational_programs']) # Сериализуем базовые поля, исключая relationships

        # Сериализация компетенций с индикаторами
        uk_competencies_data = []
        opk_competencies_data = []

        # Сортировка компетенций: сначала по ID типа компетенции, затем по коду
        # Получаем типы компетенций для сортировки по их ID
        comp_types_map = {ct.id: ct.code for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
        # Сортируем компетенции по типу и коду
        sorted_competencies = sorted(fgos.competencies, key=lambda c: (c.competency_type_id if c.competency_type_id in comp_types_map else 999, c.code))


        for comp in sorted_competencies:
            if comp.competency_type and comp.competency_type.code in ['УК', 'ОПК']:
                 # Сериализуем компетенцию, исключая индикаторы для их отдельной обработки
                 comp_dict = comp.to_dict(rules=['-fgos', '-based_on_labor_function', '-indicators', '-competency_type'])
                 comp_dict['type_code'] = comp.competency_type.code # Добавляем type_code
                 comp_dict['indicators'] = []
                 if comp.indicators:
                      # Сортируем индикаторы по коду
                      sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                      comp_dict['indicators'] = [ind.to_dict() for ind in sorted_indicators] # Сериализуем индикаторы

                 if comp.competency_type.code == 'УК':
                      uk_competencies_data.append(comp_dict)
                 elif comp.competency_type.code == 'ОПК':
                      opk_competencies_data.append(comp_dict)

        details['uk_competencies'] = uk_competencies_data
        details['opk_competencies'] = opk_competencies_data

        # Сериализация рекомендованных ПС
        recommended_ps_list = []
        if fgos.recommended_ps_assoc:
            # Сортируем связи по коду ПС
            sorted_ps_assoc = sorted(fgos.recommended_ps_assoc, key=lambda assoc: assoc.prof_standard.code if assoc.prof_standard else '')
            for assoc in sorted_ps_assoc:
                if assoc.prof_standard:
                    recommended_ps_list.append({
                        'id': assoc.prof_standard.id,
                        'code': assoc.prof_standard.code,
                        'name': assoc.prof_standard.name,
                        'is_mandatory': assoc.is_mandatory,
                        'description': assoc.description,
                    })
        details['recommended_ps_list'] = recommended_ps_list

        logger.info(f"get_fgos_details: Fetched details for FGOS {fgos_id}.")
        return details

    except SQLAlchemyError as e:
        logger.error(f"get_fgos_details: Database error in get_fgos_details for fgos_id {fgos_id}: {e}", exc_info=True)
        # При обращении к локальной БД нет необходимости в rollback, т.к. сессия управляется Flask
        return None
    except AttributeError as e: # Ловим ошибки, связанные с отсутствием предзагруженных связей
        logger.error(f"get_fgos_details: Attribute error in get_fgos_details for fgos_id {fgos_id} (check joins/selectinloads): {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"get_fgos_details: Unexpected error in get_fgos_details for fgos_id {fgos_id}: {e}", exc_info=True)
        return None


def delete_fgos(fgos_id: int, session: Session) -> bool:
    """
    Удаляет ФГОС ВО и все связанные сущности.
    Принимает сессию local_db.session. Управляет своей транзакцией (commit/rollback).
    """
    logger.info(f"delete_fgos: Attempting to delete FGOS with id: {fgos_id}")
    try:
        # Используем вложенную транзакцию
        with session.begin_nested():
            fgos_to_delete = session.query(FgosVo).get(fgos_id)
            if not fgos_to_delete:
                logger.warning(f"delete_fgos: FGOS with id {fgos_id} not found for deletion.")
                return False

            # Благодаря настроенным CASCADE DELETE на FK в моделях,
            # удаление FgosVo должно автоматически удалить связанные Competency и FgosRecommendedPs.
            session.delete(fgos_to_delete)

        # Коммит вложенной транзакции
        session.commit()
        logger.info(f"delete_fgos: FGOS with id {fgos_id} and related entities deleted successfully.")
        return True

    except SQLAlchemyError as e:
        # Откат вложенной транзакции произойдет автоматически
        logger.error(f"delete_fgos: Database error deleting FGOS {fgos_id}: {e}", exc_info=True)
        # Пробрасываем ошибку дальше, если вызывающий код должен ее обрабатывать
        raise
    except Exception as e:
        # Откат вложенной транзакции произойдет автоматически
        logger.error(f"delete_fgos: Unexpected error deleting FGOS {fgos_id}: {e}", exc_info=True)
        # Пробрасываем ошибку дальше
        raise


# ============================================================
# Функции для работы с Профессиональными Стандартами (ПС) (Парсинг, Сохранение)
# ============================================================

# TODO: Добавить импорт parse_prof_standard_uploaded_file из parsers.py
from .parsers import parse_uploaded_prof_standard

def parse_prof_standard_file(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Оркестрирует парсинг загруженного файла ПС и возвращает структурированные данные.
    (Вызывается из маршрутов POST /profstandards/upload)
    """
    logger.info(f"parse_prof_standard_file: Starting parsing for file: {filename}")
    try:
        # Вызываем парсер из parsers.py
        parsed_data = parse_uploaded_prof_standard(file_bytes, filename)

        if not parsed_data or not parsed_data.get('code') or not parsed_data.get('name'):
            logger.warning(f"parse_prof_standard_file: Parsing failed or returned insufficient metadata for {filename}. Data: {parsed_data}")
            # Парсер должен выбрасывать более специфичные ошибки.
            # Если не выбросил, но данные неполные, считаем ошибкой.
            raise ValueError("Не удалось извлечь код и название профессионального стандарта из файла.")

        # TODO: Добавить проверку существования ПС с таким кодом в БД здесь для возврата информации фронтенду?

        return {"success": True, "parsed_data": parsed_data, "filename": filename}

    except Exception as e: # Ловим ошибки парсера
        logger.error(f"parse_prof_standard_file: Error parsing file {filename}: {e}", exc_info=True)
        # Возвращаем структурированный ответ об ошибке
        return {"success": False, "error": str(e), "filename": filename}


# TODO: Реализовать _prepare_ps_structure (преобразует словарь от парсера в объекты SQLAlchemy)
def _prepare_ps_structure(parsed_structure: Dict[str, Any], session: Session) -> List[Any]:
    """
    Преобразует словарь со структурой ПС (ОТФ, ТФ, ТД, НУ, НЗ) в список объектов SQLAlchemy.
    Не сохраняет в БД, только создает объекты.
    """
    logger.debug("Preparing PS structure objects from parsed data...")
    objects_to_save = []
    # Пример обработки ОТФ
    for otf_data in parsed_structure.get('generalized_labor_functions', []):
        otf_obj = GeneralizedLaborFunction(code=otf_data.get('code'), name=otf_data.get('name'), qualification_level=otf_data.get('qualification_level'))
        objects_to_save.append(otf_obj)
        # Пример обработки ТФ
        for tf_data in otf_data.get('labor_functions', []):
            tf_obj = LaborFunction(code=tf_data.get('code'), name=tf_data.get('name'), qualification_level=tf_data.get('qualification_level'), generalized_labor_function=otf_obj)
            objects_to_save.append(tf_obj)
            # Пример обработки ТД, НУ, НЗ
            for td_data in tf_data.get('labor_actions', []):
                 td_obj = LaborAction(description=td_data.get('description'), labor_function=tf_obj)
                 objects_to_save.append(td_obj)
            for skill_data in tf_data.get('required_skills', []):
                 skill_obj = RequiredSkill(description=skill_data.get('description'), labor_function=tf_obj)
                 objects_to_save.append(skill_obj)
            for knowledge_data in tf_data.get('required_knowledge', []):
                 knowledge_obj = RequiredKnowledge(description=knowledge_data.get('description'), labor_function=tf_obj)
                 objects_to_save.append(knowledge_obj)

    # TODO: Добавить обработку других полей ПС, если парсер их извлекает (номер приказа, дата и т.д.)
    # TODO: Возможно, нужно сохранить сам объект ProfStandard здесь? Или он создается в save_prof_standard_data?

    return objects_to_save


# TODO: Реализовать save_prof_standard_data (сохраняет ProfStandard и его структуру в БД)
def save_prof_standard_data(
    parsed_data: Dict[str, Any],
    filename: str,
    session: Session,
    force_update: bool = False
) -> Optional[ProfStandard]:
    """
    Сохраняет данные Профессионального Стандарта (ProfStandard) и его структуру (ОТФ, ТФ, ТД, НУ, НЗ) в БД.
    Принимает сессию local_db.session. Управляет своей транзакцией (commit/rollback).
    """
    logger.info(f"save_prof_standard_data: Attempting to save data for PS from '{filename}'. force_update: {force_update}")
    ps_code = parsed_data.get('code')
    ps_name = parsed_data.get('name')
    ps_content = parsed_data.get('parsed_content')

    if not ps_code or not ps_name:
        logger.error("save_prof_standard_data: Missing code/name from parsed data for saving.")
        return None

    try:
        with session.begin_nested(): # Используем вложенную транзакцию

            existing_ps = session.query(ProfStandard).filter_by(code=ps_code).first()
            prof_standard = None

            if existing_ps:
                if force_update:
                    logger.info(f"save_prof_standard_data: Existing PS found ({existing_ps.id}, code: {ps_code}). Force update requested.")
                    # Удаляем старую структуру (ОТФ, ТФ, ТД, НУ, НЗ)
                    # CASCADE DELETE на FK от LaborFunction к GeneralizedLaborFunction, от ТД/НУ/НЗ к ТФ и т.д.
                    session.query(GeneralizedLaborFunction).filter_by(prof_standard_id=existing_ps.id).delete()

                    # TODO: Удалить старые связи с ФГОС и ОП (FgosRecommendedPs, EducationalProgramPs)
                    session.query(FgosRecommendedPs).filter_by(prof_standard_id=existing_ps.id).delete()
                    session.query(EducationalProgramPs).filter_by(prof_standard_id=existing_ps.id).delete()
                    # TODO: Удалить старые связи с Индикаторами (IndicatorPsLink)
                    session.query(IndicatorPsLink).filter_by(labor_function_id.in_(session.query(LaborFunction.id).filter_by(generalized_labor_function_id.in_(session.query(GeneralizedLaborFunction.id).filter_by(prof_standard_id=existing_ps.id))))) # Это будет сложно, возможно нужен JOIN или CASCADE DELETE

                    # Обновляем существующий объект ProfStandard
                    prof_standard = existing_ps
                    prof_standard.name = ps_name
                    prof_standard.parsed_content = ps_content
                    prof_standard.order_number = parsed_data.get('order_number') # TODO: Парсить из файла
                    prof_standard.order_date = parsed_data.get('order_date') # TODO: Парсить из файла (Date object)
                    prof_standard.registration_number = parsed_data.get('registration_number') # TODO: Парсить из файла
                    prof_standard.registration_date = parsed_data.get('registration_date') # TODO: Парсить из файла (Date object)

                    session.add(prof_standard)
                    session.flush()
                    logger.info(f"save_prof_standard_data: Existing PS ({prof_standard.id}) updated.")
                else:
                    logger.warning(f"save_prof_standard_data: PS with code {ps_code} already exists ({existing_ps.id}). Force update NOT requested. Skipping save.")
                    # TODO: Вернуть статус "уже существует"
                    return existing_ps
            else: # Не существующий ПС - создаем новый
                prof_standard = ProfStandard(
                    code=ps_code,
                    name=ps_name,
                    parsed_content=ps_content,
                    order_number = parsed_data.get('order_number'), # TODO: Парсить из файла
                    order_date = parsed_data.get('order_date'), # TODO: Парсить из файла (Date object)
                    registration_number = parsed_data.get('registration_number'), # TODO: Парсить из файла
                    registration_date = parsed_data.get('registration_date') # TODO: Парсить из файла (Date object)
                )
                session.add(prof_standard)
                session.flush() # Получаем ID нового объекта
                logger.info(f"save_prof_standard_data: New ProfStandard object created with ID {prof_standard.id} for code {ps_code}.")

            # Сохранение структуры ПС (ОТФ, ТФ, ТД, НУ, НЗ)
            # parsed_data должна содержать ключ 'generalized_labor_functions' со списком словарей
            if 'generalized_labor_functions' in parsed_data and isinstance(parsed_data['generalized_labor_functions'], list):
                 # Преобразуем словарь в объекты SQLAlchemy
                 ps_structure_objects = _prepare_ps_structure(parsed_data, session)
                 # Связываем объекты структуры с созданным/обновленным ProfStandard
                 for obj in ps_structure_objects:
                      # Связь устанавливается через ForeignKey, но нужно убедиться, что поле prof_standard_id заполнено
                      if isinstance(obj, GeneralizedLaborFunction):
                           obj.prof_standard_id = prof_standard.id
                      elif isinstance(obj, LaborFunction) and obj.generalized_labor_function:
                           # Связь уже установлена через объект, но убедимся, что ForeignKey заполнится
                           pass # FK заполнится при добавлении в сессию
                      # Аналогично для LaborAction, RequiredSkill, RequiredKnowledge
                 session.bulk_save_objects(ps_structure_objects)
                 session.flush() # Сохраняем структуру
                 logger.info(f"save_prof_standard_data: Saved structure for PS {prof_standard.code}.")
            else:
                 logger.warning(f"save_prof_standard_data: No or invalid 'generalized_labor_functions' in parsed data for PS {ps_code}. Skipping structure save.")


        # Commit the nested transaction
        session.commit()
        logger.info(f"save_prof_standard_data: Final commit successful for PS ID {prof_standard.id}.")
        return prof_standard # Возвращаем сохраненный объект

    except IntegrityError as e:
        session.rollback() # Откат вложенной транзакции
        logger.error(f"save_prof_standard_data: Integrity error during save for PS '{ps_code}' from '{filename}': {e}", exc_info=True)
        # TODO: Вернуть более конкретную ошибку
        return None
    except SQLAlchemyError as e:
        session.rollback() # Откат вложенной транзакции
        logger.error(f"save_prof_standard_data: Database error during save for PS '{ps_code}' from '{filename}': {e}", exc_info=True)
        # TODO: Вернуть более конкретную ошибку
        return None
    except Exception as e:
        session.rollback() # Откат вложенной транзакции
        logger.error(f"save_prof_standard_data: Unexpected error during save for PS '{ps_code}' from '{filename}': {e}", exc_info=True)
        # TODO: Вернуть более конкретную ошибку
        return None

# --- Функции для получения списка ПС и деталей ---

# TODO: Реализовать get_prof_standards_list
# TODO: Реализовать get_prof_standard_details

# ============================================================
# Вспомогательные функции для NLP
# ============================================================

# TODO: Реализовать suggest_links_nlp

# def suggest_links_nlp(disciplines: List[Dict], indicators: List[Dict]) -> List[Dict]:
#     """
#     Получает предложения по связям "Дисциплина-ИДК" от NLP модуля.
#     Это заглушка, которая будет заменена реальным вызовом к NLP.
#     """
#     import random
    
#     if not disciplines or not indicators:
#         return []
    
#     result = []
#     # Ensure disciplines have 'aup_data_id' and indicators have 'id'
#     valid_disciplines = [d for d in disciplines if 'aup_data_id' in d]
#     valid_indicators = [i for i in indicators if 'id' in i]

#     if not valid_disciplines or not valid_indicators:
#         return []

#     for _ in range(min(5, len(valid_disciplines) * len(valid_indicators))):
#         d = random.choice(valid_disciplines)
#         i = random.choice(valid_indicators)
#         result.append({
#             'aup_data_id': d['aup_data_id'],
#             'indicator_id': i['id'],
#             'score': round(random.random(), 2)
#         })
    
#     return result
