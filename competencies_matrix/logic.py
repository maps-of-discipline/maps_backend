# competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
import traceback
import logging
# import functools # Not currently used

from flask import current_app
from sqlalchemy import create_engine, select, exists, and_, or_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session, aliased, joinedload, selectinload
# from sqlalchemy import inspect # Not currently used directly in this selection

# --- Local DB models (maps.models) ---
from maps.models import db as local_db, SprDiscipline
from maps.models import AupInfo as LocalAupInfo, AupData as LocalAupData # AupInfo here is maps.models.AupInfo

# --- Competency models ---
from .models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramAup, EducationalProgramPs,
    CompetencyType, IndicatorPsLink,
    GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
)
# --- External models ---
from .external_models import (
    ExternalAupInfo, ExternalNameOP, ExternalSprOKCO, ExternalSprFormEducation,
    ExternalSprDegreeEducation, ExternalAupData, ExternalSprDiscipline, ExternalSprFaculty,
    ExternalDepartment
)

# --- Parsers ---
from .fgos_parser import (
    parse_fgos_pdf, # For parsing FGOS PDF
    parse_prof_standard, # For parsing PS files (orchestrator)
)

logger = logging.getLogger(__name__)

_external_db_engine = None

def get_external_db_engine():
    """Initializes and returns the engine for the external KD DB."""
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

# --- Data Fetching Functions ---

def get_educational_programs_list() -> List[EducationalProgram]:
    """Fetches list of all educational programs."""
    try:
        # При загрузке списка программ, явно загружаем связанные AupInfo
        # чтобы EducationalProgram.to_dict мог их включить
        programs = EducationalProgram.query.options(
             selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup)
        ).order_by(EducationalProgram.title).all()
        return programs
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_educational_programs_list: {e}")
        return []

def get_program_details(program_id: int) -> Optional[Dict[str, Any]]:
    """Fetches detailed information about an educational program."""
    try:
        program = EducationalProgram.query.options(
            selectinload(EducationalProgram.fgos), # Eager load FGOS
            selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup), # Eager load AUPs
            selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard) # Eager load selected PS
        ).get(program_id)

        if not program:
            logger.warning(f"Program with id {program_id} not found for details.")
            return None
        
        # Явно указываем, какие связанные данные включить при сериализации
        details = program.to_dict(
            include_fgos=True,
            include_aup_list=True,
            include_selected_ps_list=True,
            include_recommended_ps_list=True # Также включаем рекомендованные ПС из ФГОС
        )
        return details

    except AttributeError as ae: 
        logger.error(f"AttributeError in get_program_details for program_id {program_id}: {ae}", exc_info=True)
        return None 
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_program_details for program_id {program_id}: {e}", exc_info=True)
        return None 
    except Exception as e:
        logger.error(f"Unexpected error in get_program_details for program_id {program_id}: {e}", exc_info=True)
        return None


def get_external_aups_list(
    program_code: Optional[str] = None, profile_num: Optional[str] = None, profile_name: Optional[str] = None,
    form_education_name: Optional[str] = None, year_beg: Optional[int] = None, degree_education_name: Optional[str] = None,
    search_query: Optional[str] = None, offset: int = 0, limit: Optional[int] = 20
) -> Dict[str, Any]:
    """Fetches AUP list from external KD DB with filters and pagination."""
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
            if program_code: filters.append(ExternalSprOKCO.program_code == program_code)
            
            profile_filters_or = []
            if profile_num: profile_filters_or.append(ExternalNameOP.num_profile == profile_num)
            if profile_name: profile_filters_or.append(ExternalNameOP.name_spec.ilike(f"%{profile_name}%"))
            if profile_filters_or: filters.append(or_(*profile_filters_or))

            if form_education_name: filters.append(ExternalSprFormEducation.form == form_education_name)
            if year_beg: filters.append(ExternalAupInfo.year_beg == year_beg)
            if degree_education_name: filters.append(ExternalSprDegreeEducation.name_deg == degree_education_name)

            query = query.join(ExternalAupInfo.spec, isouter=True)\
                         .join(ExternalNameOP.okco, isouter=True) 
            query = query.join(ExternalAupInfo.form, isouter=True)
            query = query.join(ExternalAupInfo.degree, isouter=True)
            query = query.join(ExternalAupInfo.faculty, isouter=True)
            query = query.join(ExternalAupInfo.department, isouter=True)

            if filters: query = query.filter(and_(*filters))

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
    """Fetches discipline entries (AupData) for a specific AUP from external KD DB."""
    engine = get_external_db_engine()
    with Session(engine) as session:
        try:
            aup_data_entries = session.query(ExternalAupData).filter(ExternalAupData.id_aup == aup_id)\
                .order_by(ExternalAupData.id_period, ExternalAupData.shifr, ExternalAupData.id).all()

            result = []
            for entry in aup_data_entries:
                 result.append({
                     'aup_data_id': entry.id, 
                     'id_aup': entry.id_aup, 
                     'discipline_id': entry.id_discipline,
                     'title': entry.discipline, 
                     'semester': entry.id_period,
                     'shifr': entry.shifr,
                     'id_type_record': entry.id_type_record,
                     'zet': (entry.zet / 100) if entry.zet is not None else 0, 
                     'amount': entry.amount,
                     'id_type_control': entry.id_type_control
                 })

            logger.info(f"Fetched {len(result)} AupData entries for external AUP ID {aup_id} from external KD DB.")
            return result

        except Exception as e:
            logger.error(f"Error fetching external AupData for external AUP ID {aup_id}: {e}", exc_info=True)
            raise


def get_matrix_for_aup(aup_num: str) -> Optional[Dict[str, Any]]:
    """
    Collects all data needed for the competency matrix for a given AUP number.
    Fetches disciplines from external KD DB and competencies/links from local DB.
    """
    logger.info(f"get_matrix_for_aup: Processing request for AUP num: {aup_num}")
    session: Session = local_db.session
    matrix_response: Dict[str, Any] = {
        "aup_info": None, "disciplines": [], "competencies": [], "links": [],
        "suggestions": [], "external_aup_id": None, "external_aup_num": aup_num,
        "source": "not_found", "error_details": None
    }

    local_aup_info_entry: Optional[LocalAupInfo] = None
    educational_program: Optional[EducationalProgram] = None
    fgos: Optional[FgosVo] = None
    
    try:
        # ИСПРАВЛЕНИЕ: Используем правильное имя backref-отношения 'educational_program_links'
        local_aup_info_entry = session.query(LocalAupInfo).options(
            selectinload(LocalAupInfo.educational_program_links) # ИЗМЕНЕНО
                .selectinload(EducationalProgramAup.educational_program)
                .selectinload(EducationalProgram.fgos)
        ).filter_by(num_aup=aup_num).first()

        if local_aup_info_entry:
            logger.info(f"   - Found LocalAupInfo (ID: {local_aup_info_entry.id_aup}) for num_aup: {aup_num}.")
            if hasattr(local_aup_info_entry, 'as_dict') and callable(local_aup_info_entry.as_dict):
                matrix_response["aup_info"] = local_aup_info_entry.as_dict()
            else:
                logger.warning(f"LocalAupInfo (ID: {local_aup_info_entry.id_aup}) does not have as_dict method. Using basic info.")
                matrix_response["aup_info"] = {
                    'id_aup': local_aup_info_entry.id_aup,
                    'num_aup': local_aup_info_entry.num_aup,
                }
            
            # ИСПРАВЛЕНИЕ: Используем правильное имя backref-отношения
            if local_aup_info_entry.educational_program_links:
                primary_assoc = next((assoc for assoc in local_aup_info_entry.educational_program_links if assoc.is_primary), None)
                assoc_to_use = primary_assoc or local_aup_info_entry.educational_program_links[0]
                if assoc_to_use and assoc_to_use.educational_program:
                    educational_program = assoc_to_use.educational_program
                    if educational_program.fgos: fgos = educational_program.fgos
        else:
            logger.warning(f"   - LocalAupInfo for num_aup '{aup_num}' not found.")
    except Exception as e_local_aup:
        logger.error(f"   - Error finding LocalAupInfo for num_aup '{aup_num}': {e_local_aup}", exc_info=True)
        current_error_details = matrix_response.get("error_details", "") or ""
        matrix_response["error_details"] = (current_error_details +
                                            f" Error finding local AUP record {aup_num}: {e_local_aup}.")
        # Не прерываем выполнение, попробуем загрузить из внешней БД

    # ... (остальная часть функции без изменений) ...
    external_disciplines: List[Dict[str, Any]] = []
    external_aup_id_for_disciplines: Optional[int] = None
    attempted_external_fetch = False

    try:
        logger.debug(f"   - Searching external KD for AUP with num_aup '{aup_num}'...")
        external_aup_search_result = get_external_aups_list(search_query=aup_num, limit=1)
        attempted_external_fetch = True 

        if external_aup_search_result["total"] > 0 and external_aup_search_result["items"]:
            exact_match_aup = next((item for item in external_aup_search_result["items"] if item.get('num_aup') == aup_num), None)
            if exact_match_aup:
                external_aup_id_for_disciplines = exact_match_aup.get('id_aup')
                matrix_response["external_aup_id"] = external_aup_id_for_disciplines
                matrix_response["external_aup_num"] = exact_match_aup.get('num_aup', aup_num)
                if not local_aup_info_entry: 
                    matrix_response["aup_info"] = exact_match_aup 
                    matrix_response["source"] = "external_header_only"
                
                if external_aup_id_for_disciplines is not None:
                    external_disciplines = get_external_aup_disciplines(external_aup_id_for_disciplines)
                    matrix_response["disciplines"] = external_disciplines
                    logger.info(f"     - Fetched {len(external_disciplines)} discipline entries from external KD.")
                    if local_aup_info_entry and matrix_response["source"] != "local_fallback_disciplines":
                        matrix_response["source"] = "local_with_external_disciplines"
                    elif not local_aup_info_entry: 
                        matrix_response["source"] = "external_only"
                else:
                    error_msg = f" External AUP {aup_num} found, but its ID is missing. Disciplines not loaded."
                    current_error_details = matrix_response.get("error_details", "") or ""
                    matrix_response["error_details"] = (current_error_details + error_msg)
                    logger.warning(f"     - External AUP '{aup_num}' found, but its external ID is missing. Cannot fetch disciplines.")
            else:
                error_msg = f" AUP {aup_num} not found (exact match) in external DB. Disciplines not loaded."
                current_error_details = matrix_response.get("error_details", "") or ""
                matrix_response["error_details"] = (current_error_details + error_msg)
                logger.warning(f"   - AUP with num_aup '{aup_num}' not found as an exact match in external KD search results.")
        else:
            error_msg = f" AUP {aup_num} not found in external DB. Disciplines not loaded."
            current_error_details = matrix_response.get("error_details", "") or ""
            matrix_response["error_details"] = (current_error_details + error_msg)
            logger.warning(f"   - AUP with num_aup '{aup_num}' not found in external KD by num_aup search.")
    except Exception as e_ext_disciplines:
        attempted_external_fetch = True
        logger.error(f"   - Error during external KD lookup/discipline fetch for num_aup '{aup_num}': {e_ext_disciplines}", exc_info=True)
        current_error_details = matrix_response.get("error_details", "") or ""
        matrix_response["error_details"] = (current_error_details +
                                            f" Error loading disciplines for AUP {aup_num} from external DB: {e_ext_disciplines}.")

    if not external_disciplines and local_aup_info_entry:
        logger.warning(f"   - External disciplines for AUP {aup_num} are empty. Attempting to load disciplines from local AupData for local AUP ID: {local_aup_info_entry.id_aup}.")
        try:
            local_aup_data_entries = session.query(LocalAupData).options(
                joinedload(LocalAupData.discipline) 
            ).filter(LocalAupData.id_aup == local_aup_info_entry.id_aup).order_by(LocalAupData.id_period, LocalAupData.shifr, LocalAupData.id).all()

            if local_aup_data_entries:
                local_disciplines_for_response = []
                for entry in local_aup_data_entries:
                    local_disciplines_for_response.append({
                        'aup_data_id': entry.id, 
                        'id_aup': entry.id_aup,
                        'discipline_id': entry.id_discipline,
                        'title': entry.discipline.title if entry.discipline else entry._discipline, 
                        'semester': entry.id_period,
                        'shifr': entry.shifr,
                        'id_type_record': entry.id_type_record,
                        'zet': (entry.zet / 100) if entry.zet is not None else 0, 
                        'amount': entry.amount,
                        'id_type_control': entry.id_type_control
                    })
                matrix_response["disciplines"] = local_disciplines_for_response
                matrix_response["source"] = "local_fallback_disciplines"
                fallback_msg = " Using local discipline data."
                current_error_details = matrix_response.get("error_details", "") or ""
                if current_error_details and attempted_external_fetch: 
                    matrix_response["error_details"] += fallback_msg
                else:
                    matrix_response["error_details"] = "Using local discipline data (external could not be loaded or was not requested)."
                logger.info(f"     - Fetched {len(local_disciplines_for_response)} discipline entries from LOCAL AupData for AUP ID {local_aup_info_entry.id_aup}.")
            else:
                logger.warning(f"     - No disciplines found in LOCAL AupData for local AUP ID {local_aup_info_entry.id_aup} either.")
        except Exception as e_local_disc:
            logger.error(f"   - Error fetching local disciplines for AUP {local_aup_info_entry.id_aup}: {e_local_disc}", exc_info=True)
            current_error_details = matrix_response.get("error_details", "") or ""
            matrix_response["error_details"] = (current_error_details +
                                                f" Error loading local disciplines: {e_local_disc}.")


    if local_aup_info_entry: 
        if matrix_response["source"] not in ["local_fallback_disciplines", "external_header_only", "external_only"]: 
             matrix_response["source"] = "local_only" if not external_disciplines else "local_with_external_disciplines"

        comp_types_q = session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК', 'ПК'])).all()
        comp_types = {ct.code: ct for ct in comp_types_q}
        relevant_competencies = []

        if educational_program and educational_program.fgos: 
            fgos_id_to_load = educational_program.fgos.id
            uk_type = comp_types.get('УК')
            opk_type = comp_types.get('ОПК')
            uk_opk_ids_to_load = [tid.id for tid in [uk_type, opk_type] if tid]
            if uk_opk_ids_to_load:
                uk_opk_competencies = session.query(Competency).options(
                    selectinload(Competency.indicators), selectinload(Competency.competency_type)
                ).filter(Competency.fgos_vo_id == fgos_id_to_load, Competency.competency_type_id.in_(uk_opk_ids_to_load)).all()
                relevant_competencies.extend(uk_opk_competencies)
                logger.debug(f"     - Loaded {len(uk_opk_competencies)} УК/ОПК for FGOS ID {fgos_id_to_load}.")
            else: logger.warning(f"     - Competency types УК/ОПК not found in DB. Cannot load УК/ОПК for FGOS ID {fgos_id_to_load}.")

        elif educational_program and not educational_program.fgos:
             logger.warning(f"     - Educational Program ID {educational_program.id} linked to AUP {aup_num} has no FGOS linked. Skipping УК/ОПК.")
        else: 
             logger.warning(f"     - No Educational Program linked to local AUP {aup_num}. Skipping УК/ОПК loading.")

        pk_type = comp_types.get('ПК')
        if pk_type:
            if educational_program and educational_program.selected_ps_assoc:
                logger.warning("     - MVP: Loading ALL PKs, not filtered by selected PS for the program.")
                all_pk_competencies = session.query(Competency).options(
                    selectinload(Competency.indicators), selectinload(Competency.competency_type)
                ).filter(Competency.competency_type_id == pk_type.id).all() 
                relevant_competencies.extend(all_pk_competencies)
                logger.debug(f"     - Loaded {len(all_pk_competencies)} PKs (all PKs).")
            elif educational_program and not educational_program.selected_ps_assoc:
                logger.warning(f"     - Educational Program ID {educational_program.id} has no selected PS links. Skipping PK loading.")
            else: 
                logger.warning(f"     - No Educational Program linked to local AUP {aup_num} or no selected PS for program. Skipping PK loading.")
        else: 
            logger.warning("     - Competency type ПК not found in DB. Skipping PK loading.")

        competencies_data = []; all_indicator_ids_for_matrix = set()
        comp_type_id_sort_order = {ct.id: i for i, ct_code in enumerate(['УК', 'ОПК', 'ПК']) for ct in comp_types_q if ct.code == ct_code}
        relevant_competencies.sort(key=lambda c: (comp_type_id_sort_order.get(c.competency_type_id, 999), c.code))

        for comp in relevant_competencies:
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"
            comp_dict = comp.to_dict(rules=['-indicators', '-competency_type', '-fgos', '-based_on_labor_function', '-matrix_entries'])
            comp_dict['type_code'] = type_code; comp_dict['indicators'] = []
            if comp.indicators:
                sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                for ind in sorted_indicators:
                    all_indicator_ids_for_matrix.add(ind.id)
                    ind_dict = ind.to_dict();
                    ind_dict['competency_code'] = comp.code; ind_dict['competency_name'] = comp.name
                    comp_dict['indicators'].append(ind_dict)
            competencies_data.append(comp_dict)
        matrix_response["competencies"] = competencies_data
        logger.info(f"   - Prepared {len(competencies_data)} competency entries for response.")

        if matrix_response["disciplines"] and all_indicator_ids_for_matrix:
            discipline_source_aup_data_ids = [d['aup_data_id'] for d in matrix_response["disciplines"] if d.get('aup_data_id') is not None]
            if discipline_source_aup_data_ids:
                existing_links_db = session.query(CompetencyMatrix).filter(
                    CompetencyMatrix.aup_data_id.in_(discipline_source_aup_data_ids),
                    CompetencyMatrix.indicator_id.in_(list(all_indicator_ids_for_matrix))
                ).all()
                matrix_response["links"] = [link.to_dict(only=('aup_data_id', 'indicator_id', 'is_manual')) for link in existing_links_db]
                logger.debug(f"     - Loaded {len(matrix_response['links'])} matrix links from local DB (based on current discipline source IDs).")
            else:
                logger.debug("     - No valid aup_data_ids from disciplines to load links for.")
        else:
            logger.debug("     - No disciplines loaded or no indicators for matrix, local links will be empty.")
    
    if not local_aup_info_entry and not matrix_response["disciplines"] and matrix_response["source"] != "external_header_only": 
        matrix_response["source"] = "not_found"
        logger.error(f"   - AUP with num_aup '{aup_num}' not found in local DB. External search also failed or yielded no disciplines.")
        current_error_details = matrix_response.get("error_details", "") or ""
        if not current_error_details: 
            matrix_response["error_details"] = f"AUP {aup_num} not found in local or external DB, or disciplines could not be loaded."
        if not matrix_response.get("aup_info") and not matrix_response.get("disciplines"):
             return None

    return matrix_response

def update_matrix_link(aup_data_id: int, indicator_id: int, create: bool = True) -> Dict[str, Any]:
    """Creates or deletes a Discipline(AUP)-Indicator link in the matrix."""
    session: Session = local_db.session
    try:
        indicator_exists = session.query(exists().where(Indicator.id == indicator_id)).scalar()
        if not indicator_exists:
            message = f"update_matrix_link: Indicator with id {indicator_id} not found in local DB."
            logger.warning(message)
            return { 'success': False, 'status': 'error', 'message': message, 'error_type': 'indicator_not_found' }
        
        existing_link = session.query(CompetencyMatrix).filter_by(
            aup_data_id=aup_data_id,
            indicator_id=indicator_id
        ).first()

        if create:
            if not existing_link:
                link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
                session.add(link)
                session.commit()
                message = f"Link created: External AupData ID {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return { 'success': True, 'status': 'created', 'message': message }
            else:
                if not existing_link.is_manual:
                     existing_link.is_manual = True
                     session.add(existing_link)
                     session.commit()
                     logger.info(f"Link updated to manual: External AupData ID {aup_data_id} <-> Indicator {indicator_id}")
                message = f"Link already exists: External AupData ID {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return { 'success': True, 'status': 'already_exists', 'message': message }
        else:  # delete
            if existing_link:
                session.delete(existing_link)
                session.commit()
                message = f"Link deleted: External AupData ID {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return { 'success': True, 'status': 'deleted', 'message': message }
            else:
                message = f"Link not found for deletion: External AupData ID {aup_data_id} <-> Indicator {indicator_id}"
                logger.warning(message)
                return { 'success': True, 'status': 'not_found', 'message': message } 

    except SQLAlchemyError as e:
        session.rollback()
        message = f"Database error in update_matrix_link: {e}"
        logger.error(message, exc_info=True)
        return { 'success': False, 'status': 'error', 'message': message, 'error_type': 'database_error' }
    except Exception as e:
        session.rollback() 
        message = f"Unexpected error in update_matrix_link: {e}"
        logger.error(message, exc_info=True)
        return { 'success': False, 'status': 'error', 'message': message, 'error_type': 'unexpected_error', 'details': str(e) }

def get_all_competencies() -> List[Dict[str, Any]]:
    try:
        competencies = local_db.session.query(Competency).options(joinedload(Competency.competency_type)).all()
        result = []
        for comp in competencies:
             comp_dict = comp.to_dict(rules=['-indicators', '-fgos', '-based_on_labor_function'])
             comp_dict['type_code'] = comp.competency_type.code if comp.competency_type else "UNKNOWN"
             result.append(comp_dict)
        return result
    except Exception as e: logger.error(f"Error in get_all_competencies: {e}", exc_info=True); raise

def get_competency_details(comp_id: int) -> Optional[Dict[str, Any]]:
    try:
        competency = local_db.session.query(Competency).options(
            joinedload(Competency.competency_type), joinedload(Competency.indicators)
        ).get(comp_id)
        if not competency: logger.warning(f"Competency with id {comp_id} not found for details."); return None
        result = competency.to_dict(rules=['-indicators', '-fgos', '-based_on_labor_function'])
        result['type_code'] = competency.competency_type.code if competency.competency_type else "UNKNOWN"
        result['indicators'] = [ind.to_dict() for ind in competency.indicators] if competency.indicators else []
        return result
    except Exception as e: logger.error(f"Error in get_competency_details for id {comp_id}: {e}", exc_info=True); raise

def create_competency(data: Dict[str, Any]) -> Optional[Competency]:
    required_fields = ['type_code', 'code', 'name']
    if not all(field in data and data[field] is not None and str(data[field]).strip() for field in required_fields):
        logger.warning("Missing required fields for competency creation."); return None
    try:
        session: Session = local_db.session
        comp_type = session.query(CompetencyType).filter_by(code=data['type_code']).first()
        if not comp_type: logger.warning(f"Competency type with code {data['type_code']} not found."); return None
        if data['type_code'] != 'ПК': logger.warning(f"Manual creation endpoint only supports type 'ПК'. Received type '{data['type_code']}'."); return None
        query = session.query(Competency).filter_by(code=str(data['code']).strip(), competency_type_id=comp_type.id)
        existing_comp = query.first()
        if existing_comp: logger.warning(f"Competency with code {data['code']} and type {data['type_code']} already exists."); return None
        competency = Competency(
            competency_type_id=comp_type.id, code=str(data['code']).strip(), name=str(data['name']).strip(),
            description=str(data['description']).strip() if data.get('description') is not None else None,
        )
        session.add(competency); session.commit()
        logger.info(f"Competency created: {competency.code} (ID: {competency.id})"); return competency
    except IntegrityError as e: session.rollback(); logger.error(f"Database IntegrityError creating competency: {e}", exc_info=True); return None 
    except SQLAlchemyError as e: session.rollback(); logger.error(f"Database error creating competency: {e}", exc_info=True); return None
    except Exception as e: session.rollback(); logger.error(f"Unexpected error creating competency: {e}", exc_info=True); return None

def update_competency(comp_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]: 
    logger.info(f"update_competency: Received update request for competency ID: {comp_id}. Data: {data}")
    if not data: logger.warning(f"update_competency: No data provided for update for competency ID {comp_id}."); return None 
    try:
        session: Session = local_db.session
        competency = session.query(Competency).get(comp_id)
        if not competency: logger.warning(f"update_competency: Competency with id {comp_id} not found."); return None 
        allowed_fields = {'name', 'description'}; updated = False
        for field in data:
            if field in allowed_fields and hasattr(competency, field):
                 processed_value = str(data[field]).strip()
                 if field == 'description':
                      if processed_value == '': processed_value = None
                      if competency.description == processed_value: continue 
                 else:
                     if getattr(competency, field) == processed_value: continue 
                 setattr(competency, field, processed_value); updated = True
                 logger.debug(f"update_competency: Updated field '{field}' for comp {comp_id} to '{processed_value}'")
            elif field in data: logger.warning(f"update_competency: Ignoring field '{field}' for update of comp {comp_id} as it is not allowed via this endpoint.")
        if updated: session.add(competency); session.commit(); logger.info(f"update_competency: Competency {comp_id} updated successfully.")
        else: logger.info(f"update_competency: No changes detected for competency {comp_id}. No commit needed.")
        return competency.to_dict(rules=['-indicators'])
    except SQLAlchemyError as e: session.rollback(); logger.error(f"update_competency: Database error updating competency {comp_id}: {e}", exc_info=True); raise e 
    except Exception as e: session.rollback(); logger.error(f"update_competency: Unexpected error updating competency {comp_id}: {e}", exc_info=True); raise e 

def delete_competency(comp_id: int, session: Session) -> bool:
    logger.info(f"delete_competency: Attempting to delete competency ID: {comp_id}")
    try:
         with session.begin_nested(): 
              comp_to_delete = session.query(Competency).get(comp_id)
              if not comp_to_delete: logger.warning(f"delete_competency: Competency {comp_id} not found for deletion."); return False 
              session.delete(comp_to_delete); logger.info(f"delete_competency: Competency {comp_id} marked for deletion.")
         logger.info(f"delete_competency: Deletion for {comp_id} prepared in session. Outer commit needed."); return True 
    except SQLAlchemyError as e: session.rollback(); logger.error(f"delete_competency: Database error for {comp_id}: {e}", exc_info=True); raise e 
    except Exception as e: session.rollback(); logger.error(f"delete_competency: Unexpected error for {comp_id}: {e}", exc_info=True); raise e 

def get_all_indicators() -> List[Dict[str, Any]]:
    try:
        indicators = local_db.session.query(Indicator).options(joinedload(Indicator.competency)).all()
        result = []
        for ind in indicators:
             ind_dict = ind.to_dict(rules=['-competency', '-labor_functions', '-matrix_entries'])
             if ind.competency: ind_dict['competency_code'] = ind.competency.code; ind_dict['competency_name'] = ind.competency.name
             result.append(ind_dict)
        return result
    except Exception as e: logger.error(f"Error in get_all_indicators: {e}", exc_info=True); raise

def get_indicator_details(ind_id: int) -> Optional[Dict[str, Any]]:
    try:
        indicator = local_db.session.query(Indicator).options(joinedload(Indicator.competency)).get(ind_id)
        if not indicator: logger.warning(f"Indicator with id {ind_id} not found for details."); return None
        result = indicator.to_dict(rules=['-competency', '-labor_functions', '-matrix_entries'])
        if indicator.competency: result['competency_code'] = indicator.competency.code; result['competency_name'] = indicator.competency.name
        return result
    except Exception as e: logger.error(f"Error in get_indicator_details for id {ind_id}: {e}", exc_info=True); raise

def create_indicator(data: Dict[str, Any]) -> Optional[Indicator]:
    required_fields = ['competency_id', 'code', 'formulation']
    if not all(field in data and data[field] is not None and str(data[field]).strip() for field in required_fields):
        logger.warning("Missing required fields for indicator creation."); return None
    try:
        session: Session = local_db.session
        competency = session.query(Competency).get(data['competency_id'])
        if not competency: logger.warning(f"Parent competency with id {data['competency_id']} not found."); return None
        existing_indicator = session.query(Indicator).filter_by(code=str(data['code']).strip(), competency_id=data['competency_id']).first()
        if existing_indicator: logger.warning(f"Indicator with code {data['code']} for competency {data['competency_id']} already exists."); return None
        indicator = Indicator(
            competency_id=data['competency_id'], code=str(data['code']).strip(), formulation=str(data['formulation']).strip(),
            source=str(data['source']).strip() if data.get('source') is not None else None,
        )
        session.add(indicator); session.commit()
        logger.info(f"Indicator created: {indicator.code} (ID: {indicator.id}) for competency {indicator.competency_id}"); return indicator
    except IntegrityError as e: session.rollback(); logger.error(f"Database IntegrityError creating indicator: {e}", exc_info=True); return None
    except SQLAlchemyError as e: session.rollback(); logger.error(f"Database error creating indicator: {e}", exc_info=True); return None
    except Exception as e: session.rollback(); logger.error(f"Unexpected error creating indicator: {e}", exc_info=True); return None

def update_indicator(ind_id: int, data: Dict[str, Any]) -> Optional[Indicator]:
    logger.info(f"update_indicator: Received update request for indicator ID: {ind_id}. Data: {data}")
    if not data: logger.warning(f"update_indicator: No data provided for update for indicator ID {ind_id}."); return None
    try:
        session: Session = local_db.session
        indicator = session.query(Indicator).get(ind_id)
        if not indicator: logger.warning(f"update_indicator: Indicator with id {ind_id} not found."); return None 
        allowed_fields = {'code', 'formulation', 'source'}; updated = False
        for field in data:
            if field in allowed_fields and hasattr(indicator, field):
                 processed_value = str(data[field]).strip()
                 if field == 'source':
                      if processed_value == '': processed_value = None
                      if indicator.source == processed_value: continue 
                 elif field == 'code':
                      if processed_value != indicator.code:
                           existing_with_new_code = session.query(Indicator).filter_by(code=processed_value, competency_id=indicator.competency_id).first()
                           if existing_with_new_code: logger.warning(f"update_indicator: Indicator with code {processed_value} already exists for competency {indicator.competency_id}."); raise ValueError(f"Indicator with code {processed_value} already exists for this competency.")
                      if indicator.code == processed_value: continue 
                 else: 
                     if getattr(indicator, field) == processed_value: continue 
                 setattr(indicator, field, processed_value); updated = True
                 logger.debug(f"update_indicator: Updated field '{field}' for ind {ind_id} to '{processed_value}'")
            elif field in data and hasattr(indicator, field): logger.warning(f"update_indicator: Field '{field}' is not allowed for update via this endpoint for ind {ind_id}.")
        if updated: session.add(indicator); session.commit(); logger.info(f"update_indicator: Indicator {ind_id} updated successfully.")
        else: logger.info(f"update_indicator: No changes detected for indicator {ind_id}. No commit needed.")
        return indicator 
    except ValueError as ve: session.rollback(); logger.warning(f"update_indicator: Validation error for indicator {ind_id}: {ve}"); raise ve 
    except IntegrityError as e: session.rollback(); logger.error(f"update_indicator: Database IntegrityError for {ind_id}: {e}", exc_info=True); raise e 
    except SQLAlchemyError as e: session.rollback(); logger.error(f"update_indicator: Database error for {ind_id}: {e}", exc_info=True); raise e 
    except Exception as e: session.rollback(); logger.error(f"update_indicator: Unexpected error for {ind_id}: {e}", exc_info=True); raise e 

def delete_indicator(ind_id: int, session: Session) -> bool:
    logger.info(f"delete_indicator: Attempting to delete indicator ID: {ind_id}")
    try:
         with session.begin_nested(): 
              ind_to_delete = session.query(Indicator).get(ind_id)
              if not ind_to_delete: logger.warning(f"delete_indicator: Indicator {ind_id} not found for deletion."); return False 
              session.delete(ind_to_delete); logger.info(f"delete_indicator: Indicator {ind_id} marked for deletion.")
         logger.info(f"delete_indicator: Deletion for {ind_id} prepared in session. Outer commit needed."); return True 
    except SQLAlchemyError as e: session.rollback(); logger.error(f"delete_indicator: Database error for {ind_id}: {e}", exc_info=True); raise e 
    except Exception as e: session.rollback(); logger.error(f"delete_indicator: Unexpected error for {ind_id}: {e}", exc_info=True); raise e 

def parse_fgos_file(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    try:
        parsed_data = parse_fgos_pdf(file_bytes, filename)
        if not parsed_data or not parsed_data.get('metadata'):
             logger.warning(f"parse_fgos_file: Parsing failed or returned insufficient metadata for {filename}")
             if not parsed_data: raise ValueError("Parser returned empty data.")
             if not parsed_data.get('metadata'): raise ValueError("Failed to extract metadata from FGOS file.")
        return parsed_data
    except ValueError as e: logger.error(f"parse_fgos_file: Parser ValueError for {filename}: {e}"); raise e
    except Exception as e: logger.error(f"parse_fgos_file: Unexpected error parsing {filename}: {e}", exc_info=True); raise Exception(f"Unexpected error parsing FGOS file '{filename}': {e}")

def save_fgos_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[FgosVo]:
    logger.info(f"save_fgos_data: Attempting to save data for FGOS from '{filename}'. force_update: {force_update}")
    if not parsed_data or not parsed_data.get('metadata'): logger.warning("save_fgos_data: No parsed data or metadata provided for saving."); return None
    metadata = parsed_data.get('metadata', {}); fgos_number = metadata.get('order_number'); fgos_date_obj = metadata.get('order_date'); fgos_direction_code = metadata.get('direction_code'); fgos_education_level = metadata.get('education_level'); fgos_generation = metadata.get('generation'); fgos_direction_name = metadata.get('direction_name')
    if not all((fgos_number, fgos_date_obj, fgos_direction_code, fgos_education_level)): logger.error("save_fgos_data: Missing core metadata from parsed data for saving."); return None
    try:
        with session.begin_nested(): 
            existing_fgos = session.query(FgosVo).filter_by(direction_code=fgos_direction_code, education_level=fgos_education_level, number=fgos_number, date=fgos_date_obj).first()
            fgos_vo = None 
            if existing_fgos:
                if force_update:
                    logger.info(f"save_fgos_data: Existing FGOS found ({existing_fgos.id}). Force update. Deleting old comps/links...")
                    session.query(Competency).filter_by(fgos_vo_id=existing_fgos.id).delete(synchronize_session='fetch')
                    session.query(FgosRecommendedPs).filter_by(fgos_vo_id=existing_fgos.id).delete(synchronize_session='fetch'); session.flush()
                    fgos_vo = existing_fgos; fgos_vo.direction_name = fgos_direction_name or 'Not specified'; fgos_vo.generation = fgos_generation; fgos_vo.file_path = filename
                    session.add(fgos_vo); session.flush(); logger.info(f"save_fgos_data: Existing FGOS ({fgos_vo.id}) updated.")
                else: logger.warning(f"save_fgos_data: FGOS with same key data already exists ({existing_fgos.id}). Skipping save."); return existing_fgos
            else: 
                fgos_vo = FgosVo(number=fgos_number, date=fgos_date_obj, direction_code=fgos_direction_code, direction_name=fgos_direction_name or 'Not specified', education_level=fgos_education_level, generation=fgos_generation, file_path=filename)
                session.add(fgos_vo); session.flush(); logger.info(f"save_fgos_data: New FgosVo created with ID {fgos_vo.id} for {fgos_vo.direction_code}.")
            comp_types_map = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
            if not comp_types_map: logger.error("save_fgos_data: CompetencyType (УК, ОПК) not found. Cannot save competencies."); raise ValueError("CompetencyType (УК, ОПК) not found.")
            saved_competencies_count = 0; all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])
            for parsed_comp in all_parsed_competencies:
                comp_code = parsed_comp.get('code'); comp_name = parsed_comp.get('name')
                if not comp_code or not comp_name: logger.warning(f"save_fgos_data: Skipping competency due to missing code/name: {parsed_comp}"); continue
                comp_prefix = comp_code.split('-')[0].upper(); comp_type = comp_types_map.get(comp_prefix)
                if not comp_type: logger.warning(f"save_fgos_data: Skipping competency {comp_code}: Competency type {comp_prefix} not found."); continue
                existing_comp_for_fgos = session.query(Competency).filter_by(code=comp_code, competency_type_id=comp_type.id, fgos_vo_id=fgos_vo.id).first()
                if existing_comp_for_fgos: logger.warning(f"save_fgos_data: Competency {comp_code} already exists for FGOS {fgos_vo.id}. Skipping."); continue 
                competency = Competency(competency_type_id=comp_type.id, fgos_vo_id=fgos_vo.id, code=comp_code, name=comp_name)
                session.add(competency); session.flush(); saved_competencies_count += 1; logger.debug(f"save_fgos_data: Created Competency {competency.code} (ID: {competency.id}) for FGOS {fgos_vo.id}.")
            logger.info(f"save_fgos_data: Saved {saved_competencies_count} competencies for FGOS {fgos_vo.id}.")
            recommended_ps_codes = parsed_data.get('recommended_ps_codes', []); logger.info(f"save_fgos_data: Found {len(recommended_ps_codes)} potential recommended PS codes.")
            if len(recommended_ps_codes) > 0:
                 existing_prof_standards = session.query(ProfStandard).filter(ProfStandard.code.in_(recommended_ps_codes)).all(); ps_by_code = {ps.code: ps for ps in existing_prof_standards}
                 linked_ps_count = 0
                 for ps_code in recommended_ps_codes:
                    prof_standard = ps_by_code.get(ps_code)
                    if prof_standard:
                        existing_link = session.query(FgosRecommendedPs).filter_by(fgos_vo_id=fgos_vo.id, prof_standard_id=prof_standard.id).first()
                        if not existing_link: link = FgosRecommendedPs(fgos_vo_id=fgos_vo.id, prof_standard_id=prof_standard.id, is_mandatory=False); session.add(link); linked_ps_count += 1; logger.debug(f"save_fgos_data: Created link FGOS {fgos_vo.id} <-> PS {prof_standard.code}.")
                        else: logger.debug(f"save_fgos_data: Link between FGOS {fgos_vo.id} and PS {prof_standard.code} already exists.")
                    else: logger.warning(f"save_fgos_data: Recommended PS with code {ps_code} not found in DB. Skipping link.")
                 logger.info(f"save_fgos_data: Queued {linked_ps_count} new recommended PS links.")
        logger.info(f"save_fgos_data: Changes for FGOS ID {fgos_vo.id} prepared. Outer commit required."); return fgos_vo
    except IntegrityError as e: logger.error(f"save_fgos_data: Integrity error for FGOS from '{filename}': {e}", exc_info=True); return None 
    except SQLAlchemyError as e: logger.error(f"save_fgos_data: Database error for FGOS from '{filename}': {e}", exc_info=True); return None
    except Exception as e: logger.error(f"save_fgos_data: Unexpected error for FGOS from '{filename}': {e}", exc_info=True); return None

def get_fgos_list() -> List[FgosVo]:
    try:
        fgos_list = local_db.session.query(FgosVo).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()
        return fgos_list
    except SQLAlchemyError as e: logger.error(f"Database error in get_fgos_list: {e}", exc_info=True); return []
    except Exception as e: logger.error(f"Unexpected error in get_fgos_list: {e}", exc_info=True); return []

def get_fgos_details(fgos_id: int) -> Optional[Dict[str, Any]]:
    try:
        session: Session = local_db.session 
        fgos = session.query(FgosVo).options(
            selectinload(FgosVo.competencies).selectinload(Competency.indicators), 
            selectinload(FgosVo.competencies).selectinload(Competency.competency_type), 
            selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard) 
        ).get(fgos_id)
        if not fgos: logger.warning(f"get_fgos_details: FGOS with id {fgos_id} not found."); return None
        details = fgos.to_dict(rules=['-competencies', '-recommended_ps_assoc', '-educational_programs'])
        uk_competencies_data = []; opk_competencies_data = []
        comp_types_map_by_id = {ct.id: ct.code for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
        def sort_key_competency(c): type_code = comp_types_map_by_id.get(c.competency_type_id, 'ZZZ'); return (type_code, c.code)
        sorted_competencies = sorted(fgos.competencies, key=sort_key_competency)
        for comp in sorted_competencies:
            if comp.competency_type and comp.competency_type.code in ['УК', 'ОПК']: 
                 comp_dict = comp.to_dict(rules=['-fgos', '-based_on_labor_function', '-indicators', '-competency_type'])
                 comp_dict['type_code'] = comp.competency_type.code 
                 comp_dict['indicators'] = [ind.to_dict() for ind in comp.indicators] if comp.indicators else []
                 if len(comp_dict['indicators']) > 0: comp_dict['indicators'].sort(key=lambda i: i['code'])
                 if comp.competency_type.code == 'УК': uk_competencies_data.append(comp_dict)
                 elif comp.competency_type.code == 'ОПК': opk_competencies_data.append(comp_dict)
        details['uk_competencies'] = uk_competencies_data; details['opk_competencies'] = opk_competencies_data
        recommended_ps_list = []
        if fgos.recommended_ps_assoc:
            sorted_ps_assoc = sorted(fgos.recommended_ps_assoc, key=lambda a: a.prof_standard.code if a.prof_standard else '')
            for assoc_item in sorted_ps_assoc:
                if assoc_item.prof_standard: recommended_ps_list.append({'id': assoc_item.prof_standard.id, 'code': assoc_item.prof_standard.code, 'name': assoc_item.prof_standard.name, 'is_mandatory': assoc_item.is_mandatory, 'description': assoc_item.description,})
        details['recommended_ps_list'] = recommended_ps_list
        logger.info(f"get_fgos_details: Fetched details for FGOS {fgos_id}."); return details
    except SQLAlchemyError as e: logger.error(f"get_fgos_details: Database error for fgos_id {fgos_id}: {e}", exc_info=True); return None
    except Exception as e: logger.error(f"get_fgos_details: Unexpected error for fgos_id {fgos_id}: {e}", exc_info=True); return None

def delete_fgos(fgos_id: int, session: Session) -> bool:
    logger.info(f"delete_fgos: Attempting to delete FGOS with id: {fgos_id}")
    try:
        with session.begin_nested(): 
            fgos_to_delete = session.query(FgosVo).get(fgos_id)
            if not fgos_to_delete: logger.warning(f"delete_fgos: FGOS with id {fgos_id} not found for deletion."); return False 
            session.delete(fgos_to_delete); logger.info(f"delete_fgos: FGOS with id {fgos_id} and related entities marked for deletion.")
        logger.info(f"delete_fgos: Deletion for FGOS {fgos_id} prepared. Outer commit required."); return True 
    except SQLAlchemyError as e: logger.error(f"delete_fgos: Database error deleting FGOS {fgos_id}: {e}", exc_info=True); raise e 
    except Exception as e: logger.error(f"delete_fgos: Unexpected error deleting FGOS {fgos_id}: {e}", exc_info=True); raise e 

def _prepare_ps_structure_from_dict(structure_dict: Dict[str, Any], session: Session) -> List[Any]:
    logger.debug("_prepare_ps_structure_from_dict: Preparing PS structure objects.")
    objects = []
    for otf_data in structure_dict.get('generalized_labor_functions', []):
        otf_obj = GeneralizedLaborFunction(code=otf_data.get('code'), name=otf_data.get('name'), qualification_level=otf_data.get('qualification_level')); objects.append(otf_obj)
        for tf_data in otf_data.get('labor_functions', []):
            tf_obj = LaborFunction(code=tf_data.get('code'), name=tf_data.get('name'), qualification_level=tf_data.get('qualification_level'), generalized_labor_function=otf_obj); objects.append(tf_obj)
            for i, la_data in enumerate(tf_data.get('labor_actions', [])): objects.append(LaborAction(labor_function=tf_obj, description=la_data.get('description'), order=i))
            for i, rs_data in enumerate(tf_data.get('required_skills', [])): objects.append(RequiredSkill(labor_function=tf_obj, description=rs_data.get('description'), order=i))
            for i, rk_data in enumerate(tf_data.get('required_knowledge', [])): objects.append(RequiredKnowledge(labor_function=tf_obj, description=rk_data.get('description'), order=i))
    return objects

def parse_prof_standard_file(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    logger.info(f"parse_prof_standard_file: Starting PS parsing for file: {filename}")
    try:
        result = parse_prof_standard(file_bytes, filename) 
        if result.get('success') and result.get('parsed_data'): logger.info(f"parse_prof_standard_file: Parsing successful for {filename}."); return result 
        else: logger.warning(f"parse_prof_standard_file: Parsing failed or no data for {filename}. Error: {result.get('error')}"); return result 
    except Exception as e: logger.error(f"parse_prof_standard_file: Unexpected error during PS parsing for {filename}: {e}", exc_info=True); return {"success": False, "error": f"Unexpected error parsing file '{filename}': {e}", "filename": filename, "error_type": "unexpected_error"}

def save_prof_standard_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[ProfStandard]:
    logger.info(f"save_prof_standard_data: Saving PS data from '{filename}'. force_update: {force_update}")
    if not isinstance(parsed_data, dict): logger.error("save_prof_standard_data: Invalid parsed_data format (not a dict)."); return None
    ps_code = parsed_data.get('code'); ps_name = parsed_data.get('name'); ps_markdown = parsed_data.get('parsed_content_markdown')
    structure_dict = parsed_data.get('structure') 
    if not structure_dict: logger.warning(f"save_prof_standard_data: No detailed structure in parsed_data for PS {ps_code}. Saving metadata/markdown only."); structure_dict = {} 
    if not ps_code or not ps_name or ps_markdown is None: logger.error("save_prof_standard_data: Missing essential data (code, name, markdown) from parsed data."); return None
    try:
        with session.begin_nested(): 
            existing_ps = session.query(ProfStandard).filter_by(code=ps_code).first(); prof_standard = None 
            if existing_ps:
                if force_update:
                    logger.info(f"save_prof_standard_data: Existing PS ({existing_ps.id}, code: {ps_code}). Force update. Deleting old structure...")
                    session.query(GeneralizedLaborFunction).filter_by(prof_standard_id=existing_ps.id).delete(synchronize_session='fetch'); session.flush() 
                    prof_standard = existing_ps; prof_standard.name = ps_name; prof_standard.parsed_content = ps_markdown 
                    prof_standard.order_number = parsed_data.get('order_number', prof_standard.order_number); prof_standard.order_date = parsed_data.get('order_date', prof_standard.order_date)
                    prof_standard.registration_number = parsed_data.get('registration_number', prof_standard.registration_number); prof_standard.registration_date = parsed_data.get('registration_date', prof_standard.registration_date)
                    session.add(prof_standard); session.flush(); logger.info(f"save_prof_standard_data: Existing PS ({prof_standard.id}) updated.")
                else: logger.warning(f"save_prof_standard_data: PS {ps_code} already exists ({existing_ps.id}). No force update. Skipping."); return existing_ps 
            else: 
                prof_standard = ProfStandard(code=ps_code, name=ps_name, parsed_content=ps_markdown, order_number = parsed_data.get('order_number'), order_date = parsed_data.get('order_date'), registration_number = parsed_data.get('registration_number'), registration_date = parsed_data.get('registration_date'))
                session.add(prof_standard); session.flush(); logger.info(f"save_prof_standard_data: New ProfStandard created (ID {prof_standard.id}, code {ps_code}).")
            if structure_dict and isinstance(structure_dict.get('generalized_labor_functions'), list):
                 ps_structure_objects = _prepare_ps_structure_from_dict(structure_dict, session)
                 for obj in ps_structure_objects:
                     if hasattr(obj, 'prof_standard_id'): obj.prof_standard_id = prof_standard.id
                     session.add(obj)
                 session.flush(); logger.info(f"save_prof_standard_data: Saved structure for PS {prof_standard.code}.")
            elif structure_dict and structure_dict.get('generalized_labor_functions') is not None: logger.warning(f"save_prof_standard_data: 'generalized_labor_functions' in parsed structure is not a list for PS {ps_code}. Skipping structure save.")
            else: logger.debug(f"save_prof_standard_data: No detailed structure parsed/provided for PS {ps_code}.")
        logger.info(f"save_prof_standard_data: Final changes for PS ID {prof_standard.id} prepared. Outer commit required."); return prof_standard
    except IntegrityError as e: message = f"save_prof_standard_data: Integrity error for PS '{ps_code}' from '{filename}': {e}"; logger.error(message, exc_info=True); return None 
    except SQLAlchemyError as e: message = f"save_prof_standard_data: Database error for PS '{ps_code}' from '{filename}': {e}"; logger.error(message, exc_info=True); return None
    except Exception as e: message = f"save_prof_standard_data: Unexpected error for PS '{ps_code}' from '{filename}': {e}"; logger.error(message, exc_info=True); return None

def get_prof_standards_list() -> List[ProfStandard]:
    logger.debug("get_prof_standards_list: Fetching all ProfStandards.")
    try:
        prof_standards = local_db.session.query(ProfStandard).order_by(ProfStandard.code).all()
        logger.debug(f"get_prof_standards_list: Found {len(prof_standards)} ProfStandards."); return prof_standards
    except SQLAlchemyError as e: logger.error(f"get_prof_standards_list: Database error: {e}", exc_info=True); return []
    except Exception as e: logger.error(f"get_prof_standards_list: Unexpected error: {e}", exc_info=True); return []

def get_prof_standard_details(ps_id: int) -> Optional[Dict[str, Any]]:
    logger.debug(f"get_prof_standard_details: Fetching details for PS ID: {ps_id}")
    try:
        session: Session = local_db.session 
        ps = session.query(ProfStandard).options(
            selectinload(ProfStandard.generalized_labor_functions).selectinload(GeneralizedLaborFunction.labor_functions).selectinload(LaborFunction.labor_actions), 
            selectinload(ProfStandard.generalized_labor_functions).selectinload(GeneralizedLaborFunction.labor_functions).selectinload(LaborFunction.required_skills), 
            selectinload(ProfStandard.generalized_labor_functions).selectinload(GeneralizedLaborFunction.labor_functions).selectinload(LaborFunction.required_knowledge) 
        ).get(ps_id)
        if not ps: logger.warning(f"get_prof_standard_details: PS with ID {ps_id} not found."); return None
        details = ps.to_dict(rules=['-generalized_labor_functions', '-fgos_assoc', '-educational_program_assoc'])
        details['parsed_content_markdown'] = ps.parsed_content; otf_list = []
        if len(ps.generalized_labor_functions) > 0:
            sorted_otfs = sorted(ps.generalized_labor_functions, key=lambda otf: otf.code)
            for otf_item in sorted_otfs:
                 otf_dict = otf_item.to_dict(rules=['-prof_standard', '-labor_functions']); otf_dict['labor_functions'] = []
                 if len(otf_item.labor_functions) > 0:
                      sorted_tfs = sorted(otf_item.labor_functions, key=lambda tf: tf.code)
                      for tf_item in sorted_tfs:
                           tf_dict = tf_item.to_dict(rules=['-generalized_labor_function', '-labor_actions', '-required_skills', '-required_knowledge', '-indicators', '-competencies'])
                           tf_dict['labor_actions'] = sorted([la.to_dict() for la in tf_item.labor_actions], key=lambda x: x.get('order', 0))
                           tf_dict['required_skills'] = sorted([rs.to_dict() for rs in tf_item.required_skills], key=lambda x: x.get('order', 0))
                           tf_dict['required_knowledge'] = sorted([rk.to_dict() for rk in tf_item.required_knowledge], key=lambda x: x.get('order', 0))
                           otf_dict['labor_functions'].append(tf_dict)
                 otf_list.append(otf_dict)
        details['generalized_labor_functions'] = otf_list
        logger.debug(f"get_prof_standard_details: Fetched details for PS {ps_id}."); return details
    except SQLAlchemyError as e: logger.error(f"get_prof_standard_details: Database error for PS ID {ps_id}: {e}", exc_info=True); return None
    except Exception as e: logger.error(f"get_prof_standard_details: Unexpected error for PS ID {ps_id}: {e}", exc_info=True); return None