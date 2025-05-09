# competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
import traceback
import logging

from flask import current_app # Для доступа к конфигурации
from sqlalchemy import create_engine, select, exists, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased, joinedload, selectinload


from .fgos_parser import parse_fgos_pdf

# --- Импортируем модели из maps.models (локальная БД) ---
from maps.models import db as local_db, SprDiscipline, AupInfo as LocalAupInfo

# --- Импортируем НАШИ модели компетенций ---
from .models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramAup, EducationalProgramPs,
    CompetencyType, IndicatorPsLink
)
# --- Импортируем НАШИ внешние модели ---
from .external_models import (
    ExternalAupInfo,
    ExternalNameOP,
    ExternalSprOKCO,
    ExternalSprFormEducation,
    ExternalSprDegreeEducation,
    ExternalAupData,
    ExternalSprDiscipline
)


# Настройка логирования
logger = logging.getLogger(__name__)
# Уровень логирования устанавливается при старте приложения или в конфиге

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
        _external_db_engine = create_engine(db_url)
        logger.info("External DB Engine for KD initialized.")
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
                    'file': assoc.aup.file 
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
    form_education_name: Optional[str] = None, # ИСПРАВЛЕНИЕ: Имя аргумента соответствует routes.py
    year_beg: Optional[int] = None,
    degree_education_name: Optional[str] = None, # ИСПРАВЛЕНИЕ: Имя аргумента соответствует routes.py
    search_query: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = 20 # ИСПРАВЛЕНИЕ: Limit может быть None
) -> Dict[str, Any]:
    """
    Получает список АУП из внешней БД КД по заданным параметрам.
    Возвращает словарь с общим количеством и списком АУП.
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
            if program_code:
                # Фильтруем по ExternalSprOKCO.program_code через связь
                query = query.join(ExternalAupInfo.spec).join(ExternalNameOP.okco) # Убедимся, что джойны есть
                filters.append(ExternalSprOKCO.program_code == program_code)
            if profile_num:
                # Фильтруем по ExternalNameOP.num_profile
                if not any(isinstance(j.target, type(ExternalNameOP)) for j in query._legacy_setup_joins): # Проверка, есть ли уже джойн
                    query = query.join(ExternalAupInfo.spec)
                filters.append(ExternalNameOP.num_profile == profile_num)
            # ИСПРАВЛЕНИЕ: Используем form_education_name для фильтрации
            if form_education_name:
                if not any(isinstance(j.target, type(ExternalSprFormEducation)) for j in query._legacy_setup_joins):
                    query = query.join(ExternalAupInfo.form)
                filters.append(ExternalSprFormEducation.form == form_education_name)
            if year_beg:
                filters.append(ExternalAupInfo.year_beg == year_beg)
            # ИСПРАВЛЕНИЕ: Используем degree_education_name для фильтрации
            if degree_education_name:
                if not any(isinstance(j.target, type(ExternalSprDegreeEducation)) for j in query._legacy_setup_joins):
                     query = query.join(ExternalAupInfo.degree)
                filters.append(ExternalSprDegreeEducation.name_deg == degree_education_name)

            if filters:
                query = query.filter(and_(*filters))

            if search_query:
                 search_pattern = f"%{search_query}%"
                 if not any(isinstance(j.target, type(ExternalNameOP)) for j in query._legacy_setup_joins):
                      query = query.join(ExternalAupInfo.spec, isouter=True) # isouter, т.к. search может быть по num_aup
                 query = query.filter(
                     or_(
                         ExternalAupInfo.num_aup.ilike(search_pattern),
                         ExternalNameOP.name_spec.ilike(search_pattern)
                     )
                 )

            total_count = query.count()

            query = query.order_by(ExternalAupInfo.year_beg.desc(), ExternalAupInfo.num_aup)

            # Применяем пагинацию, только если limit не None
            if limit is not None:
                 query = query.offset(offset).limit(limit)

            external_aups = query.all()

            result_items = [aup.as_dict() for aup in external_aups]

            logger.info(f"Fetched {len(result_items)} of {total_count} AUPs from external KD DB.")
            return {"total": total_count, "items": result_items} # Возвращаем общее количество и элементы

        except Exception as e:
            logger.error(f"Error fetching external AUPs: {e}", exc_info=True)
            # При обращении к внешней БД нет необходимости в rollback, т.к. сессия локальна для этой функции
            raise # Пробрасываем ошибку дальше


def get_external_aup_disciplines(aup_id: int) -> List[Dict[str, Any]]:
    """
    Получает список дисциплин (AupData) для конкретного АУП из внешней БД КД.
    """
    engine = get_external_db_engine()
    with Session(engine) as session:
        try:
            aup_data_entries = session.query(ExternalAupData).options(
                # joinedload(ExternalAupData.spr_discipline)
            ).filter(ExternalAupData.id_aup == aup_id).order_by(ExternalAupData.id_period, ExternalAupData.shifr, ExternalAupData.id).all()

            result = []
            for entry in aup_data_entries:
                 result.append({
                     'aup_data_id': entry.id,
                     'id_aup': entry.id_aup,
                     'discipline_id': entry.id_discipline,
                     'title': entry.discipline, # Используем название из самой aup_data
                     'semester': entry.id_period,
                     'shifr': entry.shifr,
                     'id_type_record': entry.id_type_record,
                     # ИСПРАВЛЕНИЕ ЗЕТ: Проверяем на None перед делением и присваиваем 0 если None
                     'zet': (entry.zet / 100) if entry.zet is not None else 0,
                     'amount': entry.amount,
                     'id_type_control': entry.id_type_control
                 })

            logger.info(f"Fetched {len(result)} AupData entries for AUP ID {aup_id} from external KD DB.")
            return result

        except Exception as e:
            logger.error(f"Error fetching external AupData for AUP ID {aup_id}: {e}", exc_info=True)
            raise

def get_matrix_for_aup(aup_num: str) -> Optional[Dict[str, Any]]:
    """
    Собирает ЛОКАЛЬНЫЕ данные для матрицы (LocalAupInfo, компетенции, индикаторы, связи)
    для указанного номера АУП.
    Список дисциплин теперь получается ОТДЕЛЬНО из внешней БД.
    Использует num_aup для поиска соответствующей записи LocalAupInfo в локальной БД.
    """
    try:
        session: Session = local_db.session

        # ИЗМЕНЕНИЕ: Ищем LocalAupInfo по num_aup
        local_aup_info_entry = session.query(LocalAupInfo).options(
            selectinload(LocalAupInfo.education_programs_assoc)
            .selectinload(EducationalProgramAup.educational_program)
            .selectinload(EducationalProgram.fgos)
        ).filter_by(num_aup=aup_num).first() # Ищем по num_aup
        # .get(local_aup_id) -> .filter_by(num_aup=aup_num).first()

        if not local_aup_info_entry:
            logger.warning(f"Local AupInfo with num_aup {aup_num} not found. Cannot build matrix.")
            return None
        program = None
        fgos = None
        if local_aup_info_entry.education_programs_assoc:
            primary_assoc = next((assoc for assoc in local_aup_info_entry.education_programs_assoc if assoc.is_primary), None)
            if primary_assoc and primary_assoc.educational_program:
                program = primary_assoc.educational_program
            elif local_aup_info_entry.education_programs_assoc: # Check if list is not empty
                 if local_aup_info_entry.education_programs_assoc[0].educational_program:
                    program = local_aup_info_entry.education_programs_assoc[0].educational_program
            
            if program:
                fgos = program.fgos

        if not program:
             logger.warning(f"Local AupInfo {local_aup_info_entry.num_aup} is not linked to any Educational Program in the local DB.")
             return None
        
        logger.info(f"Found Local Program (id: {program.id}, title: {program.title}) for Local AupInfo {local_aup_info_entry.num_aup}.")
        if fgos:
             logger.info(f"Found linked FGOS (id: {fgos.id}, code: {fgos.direction_code}) in local DB.")
        else:
             logger.warning(f"Educational Program {program.id} is not linked to any FGOS in the local DB.")

        comp_types_q = session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК', 'ПК'])).all()
        comp_types = {ct.code: ct for ct in comp_types_q}

        relevant_competencies = []
        if fgos:
            uk_type = comp_types.get('УК')
            opk_type = comp_types.get('ОПК')
            uk_opk_ids_to_load = []
            if uk_type: uk_opk_ids_to_load.append(uk_type.id)
            if opk_type: uk_opk_ids_to_load.append(opk_type.id)

            if uk_opk_ids_to_load:
                uk_opk_competencies = session.query(Competency).options(
                    selectinload(Competency.indicators),
                    selectinload(Competency.competency_type) # Eager load competency_type
                ).filter(
                    Competency.fgos_vo_id == fgos.id,
                    Competency.competency_type_id.in_(uk_opk_ids_to_load)
                ).all()
                relevant_competencies.extend(uk_opk_competencies)
        else:
            logger.warning("No FGOS linked to program, skipping УК/ОПК loading for matrix.")

        pk_type = comp_types.get('ПК')
        if pk_type:
            pk_competencies = session.query(Competency).options(
                selectinload(Competency.indicators),
                selectinload(Competency.competency_type) # Eager load competency_type
            ).filter(
                Competency.competency_type_id == pk_type.id
            ).all()
            relevant_competencies.extend(pk_competencies)

        competencies_data = []
        all_indicator_ids_for_matrix = set()

        # Сортировка компетенций: сначала по ID типа компетенции, затем по коду
        relevant_competencies.sort(key=lambda c: (comp_types[c.competency_type.code].id if c.competency_type and c.competency_type.code in comp_types else 99, c.code))

        for comp in relevant_competencies:
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"
            comp_dict = comp.to_dict(rules=['-indicators', '-competency_type', '-fgos', '-based_on_labor_function', '-matrix_entries'])
            comp_dict['type_code'] = type_code
            comp_dict['indicators'] = []
            if comp.indicators:
                sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                for ind in sorted_indicators:
                    all_indicator_ids_for_matrix.add(ind.id)
                    comp_dict['indicators'].append(ind.to_dict()) # Consider rules if to_dict is complex
            competencies_data.append(comp_dict)

        existing_links_data = []
        # ИЗМЕНЕНИЕ: Фильтруем связи по aup_data_id для ДИСЦИПЛИН, связанных с LocalAupInfo
        # Найдем все id_aup_data для этого LocalAupInfo из локальной БД,
        # а потом фильтруем CompetencyMatrix по этим ID.
        # Проблема: CompetencyMatrix.aup_data_id хранит ID из EXTERNAL БД!
        # Значит, нужно найти все EXTERNAL aup_data_id, которые соответствуют LocalAupInfo.num_aup
        # Это сложно. Проще считать, что ExternalAupInfo.id_aup и LocalAupInfo.num_aup совпадают
        # (как value в Dropdown) и фильтровать связи по этому значению.
        # Но CompetencyMatrix.aup_data_id - это External AupData ID.
        # Это значит, что для получения связей для num_aup нужно:
        # 1. Получить все External AupData для этого num_aup (из внешней БД).
        # 2. Получить список их External AupData ID.
        # 3. Отфильтровать CompetencyMatrix по этому списку External AupData ID.
        # Это требует запроса к внешней БД внутри логики get_matrix_for_aup, что нежелательно.
        #
        # АЛЬТЕРНАТИВНЫЙ ВАРИАНТ: CompetencyMatrix должна хранить НЕ External AupData ID,
        # а пару (External AUP ID, External AupData Type/Key), которая уникально идентифицирует строку
        # матрицы. Или хранить Local AupInfo ID и External AupData Type/Key.
        # Или хранить External AUP ID (как num_aup) и External AupData Type/Key.
        #
        # ДЛЯ MVP и УПРОЩЕНИЯ: Сохраняем текущую структуру CompetencyMatrix (aup_data_id, indicator_id),
        # где aup_data_id - это External AupData ID.
        # В логике get_matrix_for_aup, мы получаем num_aup. Чтобы найти связи, нам нужен
        # список External AupData IDs для этого num_aup.
        #
        # НЕОБХОДИМО: Добавить запрос к внешней БД внутри get_matrix_for_aup
        # для получения списка External AupData ID по num_aup.

        external_aup_data_ids_for_num_aup = []
        try:
            external_disciplines_for_num_aup = get_external_aup_disciplines(local_aup_info_entry.id_aup) # get_external_aup_disciplines ожидает External AUP ID
            external_aup_data_ids_for_num_aup = [d['aup_data_id'] for d in external_disciplines_for_num_aup]
            logger.debug(f"   - Found {len(external_aup_data_ids_for_num_aup)} External AupData IDs for AUP num {aup_num}.")
        except Exception as e:
            logger.error(f"   - Failed to fetch external AupData IDs for AUP num {aup_num}: {e}. Cannot load links.")
            # Продолжаем, но список связей будет пустым
            pass


        if external_aup_data_ids_for_num_aup:
            existing_links_db = session.query(CompetencyMatrix).filter(
                # ИЗМЕНЕНИЕ: Фильтруем по списку External AupData IDs
                CompetencyMatrix.aup_data_id.in_(external_aup_data_ids_for_num_aup),
                CompetencyMatrix.indicator_id.in_(list(all_indicator_ids_for_matrix)) # Фильтруем только по релевантным индикаторам
            ).all()
            existing_links_data = [link.to_dict(only=('aup_data_id', 'indicator_id')) for link in existing_links_db]
            logger.debug(f"   - Found {len(existing_links_data)} links in CompetencyMatrix.")
        else:
             logger.debug("   - No External AupData IDs found or available. Links list will be empty.")

        suggestions_data = []
        # TODO: Добавить вызов suggest_links_nlp(disciplines_list, competencies_data)
        # disciplines_list is no longer available here, NLP suggestions might need adjustment
        # NLP Suggestions should likely take a list of UniqueDisciplineRow objects and relevant Indicator objects

        local_aup_info_dict = local_aup_info_entry.as_dict()
        # TODO: Populate fields like profile, year_beg, form_of_education from LocalAupInfo or related entities if missing
        # These might be missing in LocalAupInfo if not imported completely.
        # They are likely available in the LocalAupInfo object itself if relationships are loaded.
        # For now, rely on .as_dict() and hope it works or manually add:
        # local_aup_info_dict['profile'] = local_aup_info_entry.spec.name_spec if local_aup_info_entry.spec else None
        # local_aup_info_dict['year_beg'] = local_aup_info_entry.year_beg
        # local_aup_info_dict['form_of_education'] = local_aup_info_entry.form.form if local_aup_info_entry.form else None


        return {
            "aup_info": local_aup_info_dict, # Это LocalAupInfo
            "competencies": competencies_data,
            "links": existing_links_data,
            "suggestions": suggestions_data,
            # Добавляем external_aup_id и num_aup для фронтенда
            "external_aup_id": local_aup_info_entry.id_aup,
            # External AUP ID, предполагая что LocalAupInfo.id_aup == ExternalAupInfo.id_aup
            "external_aup_num": aup_num,
        }

    except Exception as e: # Catches SQLAlchemyError, AttributeError, etc.
        logger.error(f"Error in get_matrix_for_aup (aup_num: {aup_num}): {e}", exc_info=True)
        if 'session' in locals() and hasattr(session, 'is_active') and session.is_active:
            session.rollback()
        raise # Re-raise the exception to be handled by the caller or Flask error handlers
    
# --- Функции для изменения данных ---

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
    """
    try:
        parsed_data = parse_fgos_pdf(file_bytes, filename)
        if not parsed_data or not parsed_data.get('metadata') or (not parsed_data.get('uk_competencies') and not parsed_data.get('opk_competencies')):
             logger.warning(f"parse_fgos_file: Parsing failed or returned insufficient data for {filename}")
             raise ValueError("Не удалось извлечь основные метаданные и/или компетенции из файла ФГОС.")
        return parsed_data
    except ValueError as e:
        logger.error(f"parse_fgos_file: Parser ValueError for {filename}: {e}")
        raise e
    except Exception as e:
        logger.error(f"parse_fgos_file: Unexpected error parsing {filename}: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при парсинге файла ФГОС: {e}")


def save_fgos_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[FgosVo]:
    """
    Сохраняет структурированные данные ФГОС из парсера в БД.
    ОБРАТИТЕ ВНИМАНИЕ: Эта функция принимает сессию как аргумент.
    Вызывающий код должен передать local_db.session.
    """
    if not parsed_data or not parsed_data.get('metadata'):
        logger.warning("save_fgos_data: No parsed data or metadata provided.")
        return None

    metadata = parsed_data['metadata']
    fgos_number = metadata.get('order_number')
    fgos_date_str = metadata.get('order_date')
    fgos_direction_code = metadata.get('direction_code')
    fgos_education_level = metadata.get('education_level')
    fgos_generation = metadata.get('generation')
    fgos_direction_name = metadata.get('direction_name')

    if not fgos_number or not fgos_date_str or not fgos_direction_code or not fgos_education_level:
        logger.error("save_fgos_data: Missing core metadata from parsed data for saving.")
        return None

    fgos_date_obj = None
    try:
        fgos_date_obj = datetime.datetime.strptime(fgos_date_str, '%d.%m.%Y').date()
    except (ValueError, TypeError):
        try:
            logger.warning(f"save_fgos_data: Could not parse date '{fgos_date_str}' in standard format. Attempting other formats.")
            pass
        except Exception as e:
             logger.warning(f"save_fgos_data: Unexpected error parsing date '{fgos_date_str}': {e}")
             fgos_date_obj = None

    if not fgos_date_obj:
         logger.error(f"save_fgos_data: Failed to parse date '{fgos_date_str}' into a Date object.")
         return None

    existing_fgos = session.query(FgosVo).filter_by(
        direction_code=fgos_direction_code,
        education_level=fgos_education_level,
        number=fgos_number,
        date=fgos_date_obj
    ).first()

    if existing_fgos:
        if force_update:
            logger.info(f"save_fgos_data: Existing FGOS found ({existing_fgos.id}, code: {existing_fgos.direction_code}). Force update requested. Deleting old...")
            try:
                session.delete(existing_fgos)
                logger.info(f"save_fgos_data: Old FGOS ({existing_fgos.id}) marked for deletion.")
            except SQLAlchemyError as e:
                logger.error(f"save_fgos_data: Database error marking old FGOS {existing_fgos.id} for deletion: {e}", exc_info=True)
                return None
        else:
            logger.warning(f"save_fgos_data: FGOS with same code, level, number, date already exists ({existing_fgos.id}). Force update NOT requested. Skipping save.")
            return existing_fgos

    try:
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
        logger.info(f"save_fgos_data: New FgosVo object created for {fgos_vo.direction_code}.")
    except SQLAlchemyError as e:
        logger.error(f"save_fgos_data: Database error creating FgosVo object: {e}", exc_info=True)
        return None

    try:
        comp_types_map = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
        if not comp_types_map:
             logger.error("save_fgos_data: CompetencyType (УК, ОПК) not found in DB. Cannot save competencies.")
             return None

        saved_competencies_count = 0
        saved_indicators_count = 0
        all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])

        for parsed_comp in all_parsed_competencies:
            comp_code = parsed_comp.get('code')
            comp_name = parsed_comp.get('name')
            parsed_indicators = parsed_comp.get('indicators', [])

            if not comp_code or not comp_name:
                logger.warning(f"save_fgos_data: Skipping competency due to missing code/name: {parsed_comp}")
                continue

            comp_prefix = comp_code.split('-')[0]
            comp_type = comp_types_map.get(comp_prefix)

            if not comp_type:
                logger.warning(f"save_fgos_data: Skipping competency {comp_code}: Competency type {comp_prefix} not found in DB.")
                continue
                
            # Flush to get fgos_vo.id if it's a new object and not yet persisted (e.g. after delete)
            session.flush() # Ensure fgos_vo.id is available

            existing_comp = session.query(Competency).filter_by(
                 code=comp_code,
                 fgos_vo_id=fgos_vo.id 
            ).first()
            
            if existing_comp:
                 logger.warning(f"save_fgos_data: Competency {comp_code} already exists for FGOS {fgos_vo.id}. Updating instead of creating.")
                 continue

            competency = Competency(
                competency_type_id=comp_type.id,
                fgos_vo_id=fgos_vo.id,
                code=comp_code,
                name=comp_name,
            )
            session.add(competency)
            session.flush() 
            saved_competencies_count += 1

            for parsed_ind in parsed_indicators:
                ind_code = parsed_ind.get('code')
                ind_formulation = parsed_ind.get('formulation')

                if not ind_code or not ind_formulation or not ind_code.startswith(f"{comp_code}."):
                    logger.warning(f"save_fgos_data: Skipping indicator due to missing code/formulation or code mismatch ({comp_code}.* vs {ind_code}): {parsed_ind}")
                    continue

                existing_ind = session.query(Indicator).filter_by(
                     code=ind_code,
                     competency_id=competency.id
                ).first()
                
                if existing_ind:
                     logger.warning(f"save_fgos_data: Indicator {ind_code} already exists for competency {competency.id}. Skipping creation.")
                     continue

                indicator = Indicator(
                    competency_id=competency.id,
                    code=ind_code,
                    formulation=ind_formulation,
                    source=f"ФГОС {fgos_vo.direction_code} ({fgos_vo.generation})"
                )
                session.add(indicator)
                saved_indicators_count += 1
        logger.info(f"save_fgos_data: Queued {saved_competencies_count} competencies and {saved_indicators_count} indicators for saving.")

    except SQLAlchemyError as e:
        logger.error(f"save_fgos_data: Database error saving competencies/indicators: {e}", exc_info=True)
        return None

    try:
        recommended_ps_codes = parsed_data.get('recommended_ps_codes', [])
        logger.info(f"save_fgos_data: Found {len(recommended_ps_codes)} potential recommended PS codes in parsed data.")
        
        ps_by_code = {}
        if recommended_ps_codes:
             existing_prof_standards = session.query(ProfStandard).filter(ProfStandard.code.in_(recommended_ps_codes)).all()
             ps_by_code = {ps.code: ps for ps in existing_prof_standards}

        linked_ps_count = 0
        for ps_code in recommended_ps_codes:
            prof_standard = ps_by_code.get(ps_code)
            if prof_standard:
                session.flush() # Ensure fgos_vo.id is available
                existing_link = session.query(FgosRecommendedPs).filter_by(
                    fgos_vo_id=fgos_vo.id,
                    prof_standard_id=prof_standard.id
                ).first()
                
                if not existing_link:
                     link = FgosRecommendedPs(
                         fgos_vo_id=fgos_vo.id,
                         prof_standard_id=prof_standard.id,
                         is_mandatory=False
                     )
                     session.add(link)
                     linked_ps_count += 1
                else:
                     logger.warning(f"save_fgos_data: Link between FGOS {fgos_vo.id} and PS {prof_standard.code} already exists. Skipping creation.")
            else:
                logger.warning(f"save_fgos_data: Recommended PS with code {ps_code} not found in DB. Skipping link creation.")
        logger.info(f"save_fgos_data: Queued {linked_ps_count} recommended PS links for saving.")

    except SQLAlchemyError as e:
        logger.error(f"save_fgos_data: Database error saving recommended PS links: {e}", exc_info=True)
        return None

    try:
        session.commit()
        logger.info(f"save_fgos_data: Final commit successful for FGOS ID {fgos_vo.id}.")
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"save_fgos_data: Final commit failed for FGOS ID {getattr(fgos_vo, 'id', 'N/A')}: {e}", exc_info=True)
        return None

    return fgos_vo


def get_fgos_list() -> List[FgosVo]:
    """
    Получает список всех сохраненных ФГОС ВО.
    """
    try:
        # Используем local_db
        fgos_list = local_db.session.query(FgosVo).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()
        return fgos_list
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_fgos_list: {e}", exc_info=True)
        return []


def get_fgos_details(fgos_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает детальную информацию по ФГОС ВО.
    """
    try:
        session: Session = local_db.session # Используем local_db
        if not session.is_active: # Should not happen with scoped sessions typically
            session = local_db.create_session({}) # Recreate if somehow inactive

        fgos = session.query(FgosVo).options(
            selectinload(FgosVo.competencies).selectinload(Competency.indicators).joinedload(Indicator.competency),
            selectinload(FgosVo.competencies).selectinload(Competency.competency_type), # Eager load competency_type
            selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard)
        ).get(fgos_id)

        if not fgos:
            logger.warning(f"FGOS with id {fgos_id} not found for details.")
            return None

        details = fgos.to_dict()
        details['date'] = details['date'].isoformat() if details.get('date') else None

        uk_competencies_data = []
        opk_competencies_data = []

        sorted_competencies = sorted(fgos.competencies, key=lambda c: c.code)

        for comp in sorted_competencies:
            if comp.competency_type and comp.competency_type.code in ['УК', 'ОПК']:
                 comp_dict = comp.to_dict(rules=['-fgos', '-based_on_labor_function', '-indicators']) # Remove indicators to add them sorted
                 comp_dict['indicators'] = []
                 if comp.indicators:
                      sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                      comp_dict['indicators'] = [ind.to_dict() for ind in sorted_indicators]

                 if comp.competency_type.code == 'УК':
                      uk_competencies_data.append(comp_dict)
                 elif comp.competency_type.code == 'ОПК':
                      opk_competencies_data.append(comp_dict)

        details['uk_competencies'] = uk_competencies_data
        details['opk_competencies'] = opk_competencies_data

        recommended_ps_list = []
        if fgos.recommended_ps_assoc:
            for assoc in fgos.recommended_ps_assoc:
                if assoc.prof_standard:
                    recommended_ps_list.append({
                        'id': assoc.prof_standard.id,
                        'code': assoc.prof_standard.code,
                        'name': assoc.prof_standard.name,
                        'is_mandatory': assoc.is_mandatory,
                        'description': assoc.description,
                    })
        details['recommended_ps_list'] = recommended_ps_list

        logger.info(f"Fetched details for FGOS {fgos_id}.")
        return details

    except SQLAlchemyError as e:
        logger.error(f"Database error in get_fgos_details for fgos_id {fgos_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_fgos_details for fgos_id {fgos_id}: {e}", exc_info=True)
        return None


def delete_fgos(fgos_id: int, session: Session) -> bool:
    """
    Удаляет ФГОС ВО и все связанные сущности.
    ОБРАТИТЕ ВНИМАНИЕ: Эта функция принимает сессию как аргумент.
    Вызывающий код должен передать local_db.session.
    """
    try:
        fgos_to_delete = session.query(FgosVo).get(fgos_id)
        if not fgos_to_delete:
            logger.warning(f"delete_fgos: FGOS with id {fgos_id} not found.")
            return False

        session.delete(fgos_to_delete)
        session.commit()
        logger.info(f"delete_fgos: FGOS with id {fgos_id} deleted successfully (cascading enabled).")
        return True

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"delete_fgos: Database error deleting FGOS {fgos_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"delete_fgos: Unexpected error deleting FGOS {fgos_id}: {e}", exc_info=True)
        return False

# Вспомогательные функции

def suggest_links_nlp(disciplines: List[Dict], indicators: List[Dict]) -> List[Dict]:
    """
    Получает предложения по связям "Дисциплина-ИДК" от NLP модуля.
    Это заглушка, которая будет заменена реальным вызовом к NLP.
    """
    import random
    
    if not disciplines or not indicators:
        return []
    
    result = []
    # Ensure disciplines have 'aup_data_id' and indicators have 'id'
    valid_disciplines = [d for d in disciplines if 'aup_data_id' in d]
    valid_indicators = [i for i in indicators if 'id' in i]

    if not valid_disciplines or not valid_indicators:
        return []

    for _ in range(min(5, len(valid_disciplines) * len(valid_indicators))):
        d = random.choice(valid_disciplines)
        i = random.choice(valid_indicators)
        result.append({
            'aup_data_id': d['aup_data_id'],
            'indicator_id': i['id'],
            'score': round(random.random(), 2)
        })
    
    return result
