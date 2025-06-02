# filepath: competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
import traceback
import logging
import json
import re

from flask import current_app
from sqlalchemy import create_engine, select, exists, and_, or_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session, aliased, joinedload, selectinload

from maps.models import db as local_db, SprDiscipline
from maps.models import AupInfo as LocalAupInfo, AupData as LocalAupData

from .models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramAup, EducationalProgramPs,
    CompetencyType, IndicatorPsLink,
    GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge,
    CompetencyEducationalProgram
)
from .external_models import (
    ExternalAupInfo, ExternalNameOP, ExternalSprOKCO, ExternalSprFormEducation,
    ExternalSprDegreeEducation, ExternalAupData, ExternalSprDiscipline, ExternalSprFaculty,
    ExternalDepartment
)

from . import fgos_parser
from . import parsers

from .parsing_utils import parse_date_string


logger = logging.getLogger(__name__)

_external_db_engine = None

def get_external_db_engine():
    """Initializes and returns the engine for the external KD DB."""
    global _external_db_engine
    if _external_db_engine is None:
        db_url = current_app.config.get('EXTERNAL_KD_DATABASE_URL')
        if not db_url: raise RuntimeError("EXTERNAL_KD_DATABASE_URL is not configured.")
        try: _external_db_engine = create_engine(db_url)
        except Exception as e: logger.error(f"Failed to create external DB engine: {e}", exc_info=True); raise RuntimeError(f"Failed to create external DB engine: {e}")
    return _external_db_engine

def _highlight_text(text: Optional[str], query: str) -> str:
    """
    Highlights the search query in the text using <b> tags.
    Case-insensitive. Handles multiple occurrences.
    """
    if not text or not query or len(query) < 2:
        return text if text is not None else ""

    escaped_query = re.escape(query)
    # Pattern to find the query, case-insensitive.
    # Use \b to match whole words if desired, but for CONTAINS/LIKE, sub-string matching is usually better.
    # For "программный код" or "база данных", simple substring works.
    pattern = re.compile(escaped_query, re.IGNORECASE)
    
    highlighted_text = pattern.sub(lambda match: f"<b>{match.group(0)}</b>", text)
    return highlighted_text

def search_prof_standards(
    search_query: str,
    ps_ids: Optional[List[int]] = None,
    offset: int = 0,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Searches within professional standards (names, ОТФ, ТФ, ТД, НУ, НЗ) for the given query.
    Returns a paginated list of PS details with matching elements highlighted.
    Also includes flags to indicate if a section contains a match.
    """
    if not search_query or len(search_query) < 2:
        raise ValueError("Поисковый запрос должен содержать минимум 2 символа.")

    session: Session = local_db.session

    # Query for ProfStandards, eagerly loading all nested structures
    # to perform in-memory search and highlighting.
    base_query = session.query(ProfStandard).options(
        joinedload(ProfStandard.generalized_labor_functions)
            .joinedload(GeneralizedLaborFunction.labor_functions)
            .joinedload(LaborFunction.labor_actions),
        joinedload(ProfStandard.generalized_labor_functions)
            .joinedload(GeneralizedLaborFunction.labor_functions)
            .joinedload(LaborFunction.required_skills),
        joinedload(ProfStandard.generalized_labor_functions)
            .joinedload(GeneralizedLaborFunction.labor_functions)
            .joinedload(LaborFunction.required_knowledge)
    )

    if ps_ids:
        base_query = base_query.filter(ProfStandard.id.in_(ps_ids))

    all_matching_ps_details: List[Dict[str, Any]] = []

    # Iterate through all relevant PS to find matches and apply highlighting
    for ps in base_query.all():
        ps_has_match = False
        ps_details = ps.to_dict()
        ps_details['has_match'] = False
        ps_details['generalized_labor_functions'] = [] # Rebuild the structure with matched children

        query_lower = search_query.lower()

        # Check PS metadata for match and apply highlighting
        if (ps.name and query_lower in ps.name.lower()):
            ps_has_match = True
        if (ps.code and query_lower in ps.code.lower()):
             ps_has_match = True

        ps_details['name'] = _highlight_text(ps.name, search_query)
        ps_details['code'] = _highlight_text(ps.code, search_query)
        
        if ps_details.get('activity_area_name'):
            if query_lower in ps_details['activity_area_name'].lower():
                ps_has_match = True
            ps_details['activity_area_name'] = _highlight_text(ps_details['activity_area_name'], search_query)
        if ps_details.get('activity_purpose'):
            if query_lower in ps_details['activity_purpose'].lower():
                ps_has_match = True
            ps_details['activity_purpose'] = _highlight_text(ps_details['activity_purpose'], search_query)


        for otf in ps.generalized_labor_functions:
            otf_has_match = False
            otf_details = otf.to_dict()
            otf_details['has_match'] = False
            otf_details['labor_functions'] = [] # Rebuild TF list

            if (otf.name and query_lower in otf.name.lower()) or \
               (otf.code and query_lower in otf.code.lower()):
                otf_has_match = True
            
            otf_details['name'] = _highlight_text(otf.name, search_query)
            otf_details['code'] = _highlight_text(otf.code, search_query)


            for tf in otf.labor_functions:
                tf_has_match = False
                tf_details = tf.to_dict()
                tf_details['has_match'] = False
                tf_details['labor_actions'] = []
                tf_details['required_skills'] = []
                tf_details['required_knowledge'] = []

                if (tf.name and query_lower in tf.name.lower()) or \
                   (tf.code and query_lower in tf.code.lower()):
                    tf_has_match = True
                
                tf_details['name'] = _highlight_text(tf.name, search_query)
                tf_details['code'] = _highlight_text(tf.code, search_query)


                for la in tf.labor_actions:
                    la_details = la.to_dict()
                    if la.description and query_lower in la.description.lower():
                        la_details['description'] = _highlight_text(la.description, search_query)
                        la_details['has_match'] = True
                        tf_has_match = True
                    tf_details['labor_actions'].append(la_details)

                for rs in tf.required_skills:
                    rs_details = rs.to_dict()
                    if rs.description and query_lower in rs.description.lower():
                        rs_details['description'] = _highlight_text(rs.description, search_query)
                        rs_details['has_match'] = True
                        tf_has_match = True
                    tf_details['required_skills'].append(rs_details)

                for rk in tf.required_knowledge:
                    rk_details = rk.to_dict()
                    if rk.description and query_lower in rk.description.lower():
                        rk_details['description'] = _highlight_text(rk.description, search_query)
                        rk_details['has_match'] = True
                        tf_has_match = True
                    tf_details['required_knowledge'].append(rk_details)
                
                # Only add TF to OTF's list if it or its children match (for filtered display)
                if tf_has_match:
                    tf_details['has_match'] = True
                    # Propagate match up the hierarchy
                    otf_has_match = True
                    otf_details['labor_functions'].append(tf_details)

            # Only add OTF to PS's list if it or its children match (for filtered display)
            if otf_has_match:
                otf_details['has_match'] = True
                # Propagate match up the hierarchy
                ps_has_match = True
                ps_details['generalized_labor_functions'].append(otf_details)
        
        # Add PS to results if it or any of its children matched
        if ps_has_match:
            ps_details['has_match'] = True
            all_matching_ps_details.append(ps_details)

    all_matching_ps_details.sort(key=lambda x: x.get('code', ''))

    total_results = len(all_matching_ps_details)
    paginated_results = all_matching_ps_details[offset : offset + limit]

    logger.info(f"Found {total_results} matching PS for query '{search_query}'. Returning {len(paginated_results)} (offset {offset}, limit {limit}).")
    return {
        "total": total_results,
        "items": paginated_results
    }

def get_educational_programs_list() -> List[EducationalProgram]:
    """Fetches list of all educational programs."""
    try: return EducationalProgram.query.options(selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup)).order_by(EducationalProgram.title).all()
    except SQLAlchemyError as e: logger.error(f"Database error fetching programs list: {e}"); return []

def get_program_details(program_id: int) -> Optional[Dict[str, Any]]:
    """Fetches detailed information about an educational program."""
    try:
        program = EducationalProgram.query.options(
            selectinload(EducationalProgram.fgos),
            selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
            selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard),
            selectinload(EducationalProgram.competencies_assoc).selectinload(CompetencyEducationalProgram.competency).selectinload(Competency.competency_type)
        ).get(program_id)

        if not program: logger.warning(f"Program with id {program_id} not found."); return None
        
        details = program.to_dict(
            include_fgos=True, include_aup_list=True, include_selected_ps_list=True,
            include_recommended_ps_list=True, include_competencies_list=True
        )
        return details

    except AttributeError as ae: logger.error(f"AttributeError for program_id {program_id}: {ae}", exc_info=True); return None
    except SQLAlchemyError as e: logger.error(f"Database error for program_id {program_id}: {e}", exc_info=True); return None
    except Exception as e: logger.error(f"Unexpected error for program_id {program_id}: {e}", exc_info=True); return None


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
                joinedload(ExternalAupInfo.form), joinedload(ExternalAupInfo.degree),
                joinedload(ExternalAupInfo.faculty), joinedload(ExternalAupInfo.department)
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
                     ExternalAupInfo.num_aup.ilike(search_pattern), ExternalNameOP.name_spec.ilike(search_pattern),
                     ExternalSprOKCO.program_code.ilike(search_pattern), ExternalSprFaculty.name_faculty.ilike(search_pattern),
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

        except Exception as e: logger.error(f"Error fetching external AUPs: {e}", exc_info=True); raise


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
                     'aup_data_id': entry.id, 'id_aup': entry.id_aup, 'discipline_id': entry.id_discipline,
                     'title': entry.discipline, 'semester': entry.id_period, 'shifr': entry.shifr,
                     'id_type_record': entry.id_type_record, 'zet': (entry.zet / 100) if entry.zet is not None else 0,
                     'amount': entry.amount, 'id_type_control': entry.id_type_control
                 })
            return result
        except Exception as e: logger.error(f"Error fetching external AupData for external AUP ID {aup_id}: {e}", exc_info=True); raise


def get_matrix_for_aup(aup_num: str) -> Optional[Dict[str, Any]]:
    """
    Collects all data needed for the competency matrix for a given AUP number.
    Fetches disciplines from external KD DB and competencies/links from local DB.
    """
    logger.info(f"Processing request for AUP num: {aup_num}")
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
        local_aup_info_entry = session.query(LocalAupInfo).options(
            selectinload(LocalAupInfo.educational_program_links)
                .selectinload(EducationalProgramAup.educational_program)
                .selectinload(EducationalProgram.fgos)
        ).filter_by(num_aup=aup_num).first()

        if local_aup_info_entry:
            matrix_response["aup_info"] = local_aup_info_entry.as_dict() if hasattr(local_aup_info_entry, 'as_dict') and callable(local_aup_info_entry.as_dict) else {'id_aup': local_aup_info_entry.id_aup, 'num_aup': local_aup_info_entry.num_aup}
            
            if local_aup_info_entry.educational_program_links:
                primary_assoc = next((assoc for assoc in local_aup_info_entry.educational_program_links if assoc.is_primary), None)
                assoc_to_use = primary_assoc or local_aup_info_entry.educational_program_links[0]
                if assoc_to_use and assoc_to_use.educational_program:
                    educational_program = assoc_to_use.educational_program
                    if educational_program.fgos: fgos = educational_program.fgos
        else: logger.warning(f"LocalAupInfo for num_aup '{aup_num}' not found.")
    except Exception as e_local_aup:
        logger.error(f"Error finding LocalAupInfo for num_aup '{aup_num}': {e_local_aup}", exc_info=True)
        current_error_details = matrix_response.get("error_details", "") or ""
        matrix_response["error_details"] = (current_error_details + f" Error finding local AUP record {aup_num}: {e_local_aup}.")

    external_disciplines: List[Dict[str, Any]] = []
    external_aup_id_for_disciplines: Optional[int] = None
    attempted_external_fetch = False

    try:
        external_aup_search_result = get_external_aups_list(search_query=aup_num, limit=1)
        attempted_external_fetch = True

        if external_aup_search_result["total"] > 0 and external_aup_search_result["items"]:
            exact_match_aup = next((item for item in external_aup_search_result["items"] if item.get('num_aup') == aup_num), None)
            if exact_match_aup:
                external_aup_id_for_disciplines = exact_match_aup.get('id_aup')
                matrix_response["external_aup_id"] = external_aup_id_for_disciplines
                matrix_response["external_aup_num"] = exact_match_aup.get('num_aup', aup_num)
                if not local_aup_info_entry: matrix_response["aup_info"] = exact_match_aup; matrix_response["source"] = "external_header_only"
                
                if external_aup_id_for_disciplines is not None:
                    external_disciplines = get_external_aup_disciplines(external_aup_id_for_disciplines)
                    matrix_response["disciplines"] = external_disciplines
                    if local_aup_info_entry and matrix_response["source"] != "local_fallback_disciplines": matrix_response["source"] = "local_with_external_disciplines"
                    elif not local_aup_info_entry: matrix_response["source"] = "external_only"
                else:
                    error_msg = f" External AUP {aup_num} found, but its ID is missing. Disciplines not loaded."
                    current_error_details = matrix_response.get("error_details", "") or ""
                    matrix_response["error_details"] = (current_error_details + error_msg)
            else:
                error_msg = f" AUP {aup_num} not found (exact match) in external DB. Disciplines not loaded."
                current_error_details = matrix_response.get("error_details", "") or ""
                matrix_response["error_details"] = (current_error_details + error_msg)
        else:
            error_msg = f" AUP {aup_num} not found in external DB. Disciplines not loaded."
            current_error_details = matrix_response.get("error_details", "") or ""
            matrix_response["error_details"] = (current_error_details + error_msg)
    except Exception as e_ext_disciplines:
        attempted_external_fetch = True
        logger.error(f"Error during external KD lookup/discipline fetch for num_aup '{aup_num}': {e_ext_disciplines}", exc_info=True)
        current_error_details = matrix_response.get("error_details", "") or ""
        matrix_response["error_details"] = (current_error_details + f" Error loading disciplines for AUP {aup_num} from external DB: {e_ext_disciplines}.")

    if not external_disciplines and local_aup_info_entry:
        try:
            local_aup_data_entries = session.query(LocalAupData).options(joinedload(LocalAupData.discipline)).filter(LocalAupData.id_aup == local_aup_info_entry.id_aup).order_by(LocalAupData.id_period, LocalAupData.shifr, LocalAupData.id).all()

            if local_aup_data_entries:
                local_disciplines_for_response = []
                for entry in local_aup_data_entries:
                    local_disciplines_for_response.append({
                        'aup_data_id': entry.id, 'id_aup': entry.id_aup, 'discipline_id': entry.id_discipline,
                        'title': entry.discipline.title if entry.discipline else entry._discipline,
                        'semester': entry.id_period, 'shifr': entry.shifr,
                        'id_type_record': entry.id_type_record, 'zet': (entry.zet / 100) if entry.zet is not None else 0,
                        'amount': entry.amount, 'id_type_control': entry.id_type_control
                    })
                matrix_response["disciplines"] = local_disciplines_for_response
                matrix_response["source"] = "local_fallback_disciplines"
                fallback_msg = " Using local discipline data."
                current_error_details = matrix_response.get("error_details", "") or ""
                if current_error_details and attempted_external_fetch: matrix_response["error_details"] += fallback_msg
                else: matrix_response["error_details"] = "Using local discipline data (external could not be loaded or was not requested)."
            else: logger.warning(f"No disciplines found in LOCAL AupData for local AUP ID {local_aup_info_entry.id_aup} either.")
        except Exception as e_local_disc:
            logger.error(f"Error fetching local disciplines for AUP {local_aup_info_entry.id_aup}: {e_local_disc}", exc_info=True)
            current_error_details = matrix_response.get("error_details", "") or ""
            matrix_response["error_details"] = (current_error_details + f" Error loading local disciplines: {e_local_disc}.")

    if local_aup_info_entry:
        if matrix_response["source"] not in ["local_fallback_disciplines", "external_header_only", "external_only"]:
             matrix_response["source"] = "local_only" if not external_disciplines else "local_with_external_disciplines"

        comp_types_q = session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК', 'ПК'])).all()
        comp_types = {ct.code: ct for ct in comp_types_q}
        relevant_competencies = []

        if educational_program and educational_program.fgos:
            fgos_id_to_load = educational_program.fgos.id
            uk_type = comp_types.get('УК'); opk_type = comp_types.get('ОПК')
            uk_opk_ids_to_load = [tid.id for tid in [uk_type, opk_type] if tid]
            if uk_opk_ids_to_load:
                uk_opk_competencies = session.query(Competency).options(
                    selectinload(Competency.indicators),
                    selectinload(Competency.competency_type),
                    selectinload(Competency.fgos) # For source_document_type
                ).filter(Competency.fgos_vo_id == fgos_id_to_load, Competency.competency_type_id.in_(uk_opk_ids_to_load)).all()
                relevant_competencies.extend(uk_opk_competencies)
            else: logger.warning(f"Competency types УК/ОПК not found in DB. Cannot load УК/ОПК for FGOS ID {fgos_id_to_load}.")
        elif educational_program and not educational_program.fgos: logger.warning(f"Educational Program ID {educational_program.id} linked to AUP {aup_num} has no FGOS linked. Skipping УК/ОПК.")
        else: logger.warning(f"No Educational Program linked to local AUP {aup_num}. Skipping УК/ОПК loading.")

        pk_type = comp_types.get('ПК')
        if pk_type:
            pk_competencies = session.query(Competency).options(
                selectinload(Competency.indicators),
                selectinload(Competency.competency_type),
                selectinload(Competency.educational_programs_assoc), # For filtering by Educational Program
                selectinload(Competency.based_on_labor_function) # For source_document_type
                    .selectinload(LaborFunction.generalized_labor_function)
                    .selectinload(GeneralizedLaborFunction.prof_standard) # For source_document_type
            ).filter(Competency.competency_type_id == pk_type.id).all()
            
            filtered_pk_competencies = []
            if educational_program:
                for pk_comp in pk_competencies:
                    if any(assoc.educational_program_id == educational_program.id for assoc in pk_comp.educational_programs_assoc):
                        filtered_pk_competencies.append(pk_comp)
                relevant_competencies.extend(filtered_pk_competencies)
            else:
                # If Educational Program is not found or not linked, but PKs exist, display all PKs (as in MVP)
                relevant_competencies.extend(pk_competencies)
        else: logger.warning(f"Competency type ПК not found in DB. Skipping ПК loading.")

        competencies_data = []; all_indicator_ids_for_matrix = set()
        comp_type_id_sort_order = {ct.id: i for i, ct_code in enumerate(['УК', 'ОПК', 'ПК']) for ct in comp_types_q if ct.code == ct_code}
        relevant_competencies.sort(key=lambda c: (comp_type_id_sort_order.get(c.competency_type_id, 999), c.code))

        for comp in relevant_competencies:
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"
            comp_dict = comp.to_dict(rules=['-indicators', '-competency_type', '-fgos', '-based_on_labor_function', '-matrix_entries', '-educational_programs_assoc'])
            comp_dict['type_code'] = type_code;
            comp_dict['indicators'] = []

            comp_dict['source_document_id'] = None
            comp_dict['source_document_code'] = None
            comp_dict['source_document_name'] = None
            comp_dict['source_document_type'] = None

            if comp.competency_type and comp.competency_type.code in ['УК', 'ОПК']:
                if comp.fgos:
                    comp_dict['source_document_id'] = comp.fgos.id
                    comp_dict['source_document_code'] = comp.fgos.direction_code
                    comp_dict['source_document_name'] = comp.fgos.direction_name
                    comp_dict['source_document_type'] = "ФГОС ВО"
            elif comp.competency_type and comp.competency_type.code == 'ПК':
                if comp.based_on_labor_function and \
                   comp.based_on_labor_function.generalized_labor_function and \
                   comp.based_on_labor_function.generalized_labor_function.prof_standard:
                    ps = comp.based_on_labor_function.generalized_labor_function.prof_standard
                    comp_dict['source_document_id'] = ps.id
                    comp_dict['source_document_code'] = ps.code
                    comp_dict['source_document_name'] = ps.name
                    comp_dict['source_document_type'] = "Профстандарт"
                else:
                    comp_dict['source_document_type'] = "Ручной ввод" # PK created manually, without TF/PS link
                    comp_dict['source_document_code'] = "N/A"
                    comp_dict['source_document_name'] = "Введено вручную"


            if comp.based_on_labor_function: # Still include this for form pre-fill
                 comp_dict['based_on_labor_function_id'] = comp.based_on_labor_function.id
                 comp_dict['based_on_labor_function_code'] = comp.based_on_labor_function.code
                 comp_dict['based_on_labor_function_name'] = comp.based_on_labor_function.name

            if comp.indicators:
                sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                for ind in sorted_indicators:
                    all_indicator_ids_for_matrix.add(ind.id)
                    ind_dict = ind.to_dict();
                    ind_dict['competency_code'] = comp.code; ind_dict['competency_name'] = comp.name
                    ind_dict['competency_type_code'] = comp_dict['type_code']
                    
                    ind_dict['source_document_id'] = comp_dict['source_document_id']
                    ind_dict['source_document_code'] = comp_dict['source_document_code']
                    ind_dict['source_document_name'] = comp_dict['source_document_name']
                    ind_dict['source_document_type'] = comp_dict['source_document_type']
                    ind_dict['selected_ps_elements_ids'] = ind.selected_ps_elements_ids


                    comp_dict['indicators'].append(ind_dict)
            competencies_data.append(comp_dict)
        matrix_response["competencies"] = competencies_data

        if matrix_response["disciplines"] and all_indicator_ids_for_matrix:
            discipline_source_aup_data_ids = [d['aup_data_id'] for d in matrix_response["disciplines"] if d.get('aup_data_id') is not None]
            if discipline_source_aup_data_ids:
                existing_links_db = session.query(CompetencyMatrix).filter(
                    CompetencyMatrix.aup_data_id.in_(discipline_source_aup_data_ids),
                    CompetencyMatrix.indicator_id.in_(list(all_indicator_ids_for_matrix))
                ).all()
                matrix_response["links"] = [link.to_dict(only=('aup_data_id', 'indicator_id', 'is_manual')) for link in existing_links_db]
            else: logger.debug("No valid aup_data_ids from disciplines to load links for.")
        else: logger.debug("No disciplines loaded or no indicators for matrix, local links will be empty.")
    
    if not local_aup_info_entry and not matrix_response["disciplines"] and matrix_response["source"] != "external_header_only":
        matrix_response["source"] = "not_found"
        logger.error(f"AUP with num_aup '{aup_num}' not found in local DB. External search also failed or yielded no disciplines.")
        current_error_details = matrix_response.get("error_details", "") or ""
        if not current_error_details: matrix_response["error_details"] = f"AUP {aup_num} not found in local or external DB, or disciplines could not be loaded."
        if not matrix_response.get("aup_info") and not matrix_response.get("disciplines"): return None

    return matrix_response

def update_matrix_link(aup_data_id: int, indicator_id: int, create: bool = True) -> Dict[str, Any]:
    """Creates or deletes a Discipline(AUP)-Indicator link in the matrix."""
    session: Session = local_db.session
    try:
        indicator_exists = session.query(exists().where(Indicator.id == indicator_id)).scalar()
        if not indicator_exists:
            message = f"Indicator with id {indicator_id} not found in local DB."
            logger.warning(message); return { 'success': False, 'status': 'error', 'message': message, 'error_type': 'indicator_not_found' }
        
        existing_link = session.query(CompetencyMatrix).filter_by(aup_data_id=aup_data_id, indicator_id=indicator_id).first()

        if create:
            if not existing_link:
                link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
                session.add(link); logger.info(f"Link created: External AupData ID {aup_data_id} <-> Indicator {indicator_id}")
                return { 'success': True, 'status': 'created', 'message': "Link created." }
            else:
                if not existing_link.is_manual:
                     existing_link.is_manual = True
                     session.add(existing_link); logger.info(f"Link updated to manual: External AupData ID {aup_data_id} <-> Indicator {indicator_id}")
                return { 'success': True, 'status': 'already_exists', 'message': "Link already exists." }
        else:  # delete
            if existing_link:
                session.delete(existing_link); logger.info(f"Link deleted: External AupData ID {aup_data_id} <-> Indicator {indicator_id}")
                return { 'success': True, 'status': 'deleted', 'message': "Link deleted." }
            else:
                logger.warning(f"Link not found for deletion: External AupData ID {aup_data_id} <-> Indicator {indicator_id}")
                return { 'success': True, 'status': 'not_found', 'message': "Link not found." }

    except SQLAlchemyError as e: logger.error(f"Database error updating matrix link: {e}", exc_info=True); raise
    except Exception as e: logger.error(f"Unexpected error updating matrix link: {e}", exc_info=True); raise

def get_all_competencies() -> List[Dict[str, Any]]:
    try:
        # Eagerly load related models to avoid N+1 queries
        competencies = local_db.session.query(Competency).options(
            joinedload(Competency.competency_type),
            joinedload(Competency.fgos), # For УК/ОПК source
            joinedload(Competency.based_on_labor_function) # For ПК source
                .joinedload(LaborFunction.generalized_labor_function)
                .joinedload(GeneralizedLaborFunction.prof_standard)
        ).all()
        result = []
        for comp in competencies:
            comp_dict = comp.to_dict(rules=['-indicators', '-fgos', '-based_on_labor_function', '-matrix_entries', '-educational_programs_assoc'])
            comp_dict['type_code'] = comp.competency_type.code if comp.competency_type else "UNKNOWN"
            
            comp_dict['source_document_id'] = None
            comp_dict['source_document_code'] = None
            comp_dict['source_document_name'] = None
            comp_dict['source_document_type'] = None

            if comp.competency_type and comp.competency_type.code in ['УК', 'ОПК']:
                if comp.fgos:
                    comp_dict['source_document_id'] = comp.fgos.id
                    comp_dict['source_document_code'] = comp.fgos.direction_code
                    comp_dict['source_document_name'] = comp.fgos.direction_name
                    comp_dict['source_document_type'] = "ФГОС ВО"
            elif comp.competency_type and comp.competency_type.code == 'ПК':
                if comp.based_on_labor_function and \
                   comp.based_on_labor_function.generalized_labor_function and \
                   comp.based_on_labor_function.generalized_labor_function.prof_standard:
                    ps = comp.based_on_labor_function.generalized_labor_function.prof_standard
                    comp_dict['source_document_id'] = ps.id
                    comp_dict['source_document_code'] = ps.code
                    comp_dict['source_document_name'] = ps.name
                    comp_dict['source_document_type'] = "Профстандарт"
                else:
                    # Manually created PK without direct PS link or link not found
                    comp_dict['source_document_type'] = "Ручной ввод"
                    comp_dict['source_document_code'] = "N/A"
                    comp_dict['source_document_name'] = "Введено вручную"

            if comp.based_on_labor_function: # Still include this for form pre-fill
                comp_dict['based_on_labor_function_id'] = comp.based_on_labor_function.id
                comp_dict['based_on_labor_function_code'] = comp.based_on_labor_function.code
                comp_dict['based_on_labor_function_name'] = comp.based_on_labor_function.name

            result.append(comp_dict)
        return result
    except Exception as e: logger.error(f"Error fetching all competencies with source info: {e}", exc_info=True); raise

def get_competency_details(comp_id: int) -> Optional[Dict[str, Any]]:
    try:
        competency = local_db.session.query(Competency).options(
            joinedload(Competency.competency_type),
            joinedload(Competency.indicators),
            joinedload(Competency.educational_programs_assoc).joinedload(CompetencyEducationalProgram.educational_program)
        ).get(comp_id)
        if not competency: logger.warning(f"Competency with id {comp_id} not found."); return None
        result = competency.to_dict(rules=['-fgos', '-based_on_labor_function'], include_indicators=True, include_type=True, include_educational_programs=True)
        if competency.based_on_labor_function:
            result['based_on_labor_function_id'] = competency.based_on_labor_function.id
            result['based_on_labor_function_code'] = competency.based_on_labor_function.code
            result['based_on_labor_function_name'] = competency.based_on_labor_function.name
        return result
    except Exception as e: logger.error(f"Error fetching competency {comp_id} details: {e}", exc_info=True); raise

def create_competency(data: Dict[str, Any], session: Session) -> Optional[Competency]:
    required_fields = ['type_code', 'code', 'name']
    if not all(field in data and data[field] is not None and str(data[field]).strip() for field in required_fields):
        raise ValueError("Отсутствуют обязательные поля: type_code, code, name.")
    if data['type_code'] != 'ПК': raise ValueError(f"Данный эндпоинт предназначен только для создания ПК. Получен тип '{data['type_code']}'.")

    educational_program_ids = data.get('educational_program_ids', [])
    if not isinstance(educational_program_ids, list):
         logger.warning(f"'educational_program_ids' is not a list. Ignoring or handling as error.")
         educational_program_ids = []
    
    based_on_labor_function_id = data.get('based_on_labor_function_id')
    
    try:
        comp_type = session.query(CompetencyType).filter_by(code=data['type_code']).first()
        if not comp_type: raise ValueError(f"Тип компетенции с кодом '{data['type_code']}' не найден.") # Corrected 'type_type' to 'type_code'
        
        existing_comp = session.query(Competency).filter_by(code=str(data['code']).strip(), competency_type_id=comp_type.id).first()
        if existing_comp: raise IntegrityError(f"Competency with code {data['code']} already exists for this type.", {}, None)
        
        labor_function = None
        if based_on_labor_function_id:
             labor_function = session.query(LaborFunction).get(based_on_labor_function_id)
             if not labor_function:
                 logger.warning(f"Labor function with ID {based_on_labor_function_id} not found. Skipping link.")
                 based_on_labor_function_id = None
        
        competency = Competency(
            competency_type_id=comp_type.id, code=str(data['code']).strip(),
            name=str(data['name']).strip(),
            description=str(data['description']).strip() if data.get('description') is not None else None,
            based_on_labor_function_id=based_on_labor_function_id
        )
        session.add(competency); session.flush()

        for ep_id in educational_program_ids:
            educational_program = session.query(EducationalProgram).get(ep_id)
            if educational_program:
                 assoc = CompetencyEducationalProgram(competency_id=competency.id, educational_program_id=ep_id)
                 session.add(assoc)
            else: logger.warning(f"Educational Program with ID {ep_id} not found. Skipping link for competency {competency.id}.")

        session.flush(); return competency
    except IntegrityError as e: logger.error(f"Database IntegrityError creating competency: {e}", exc_info=True); raise e
    except SQLAlchemyError as e: logger.error(f"Database error creating competency: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error creating competency: {e}", exc_info=True); raise e

def update_competency(comp_id: int, data: Dict[str, Any], session: Session) -> Optional[Dict[str, Any]]:
    if not data: raise ValueError("Отсутствуют данные для обновления.")
    educational_program_ids = data.get('educational_program_ids')
    try:
        competency = session.query(Competency).get(comp_id)
        if not competency: return None
        
        allowed_fields = {'name', 'description'}
        updated = False
        
        for field in data:
            if field in allowed_fields:
                 processed_value = str(data[field]).strip() if data[field] is not None else None
                 if field == 'description' and processed_value == '': processed_value = None
                 
                 if getattr(competency, field) != processed_value:
                     setattr(competency, field, processed_value)
                     updated = True
            else: logger.warning(f"Ignoring field '{field}' for update of comp {comp_id} as it is not allowed via this endpoint.")
        
        if educational_program_ids is not None:
            current_ep_ids = {assoc.educational_program_id for assoc in competency.educational_programs_assoc}
            new_ep_ids = set(educational_program_ids)

            to_delete_ids = current_ep_ids - new_ep_ids
            if to_delete_ids:
                session.query(CompetencyEducationalProgram).filter(
                    CompetencyEducationalProgram.competency_id == competency.id,
                    CompetencyEducationalProgram.educational_program_id.in_(to_delete_ids)
                ).delete(synchronize_session='fetch'); updated = True
            
            to_add_ids = new_ep_ids - current_ep_ids
            if to_add_ids:
                for ep_id in to_add_ids:
                    educational_program = session.query(EducationalProgram).get(ep_id)
                    if educational_program:
                        assoc = CompetencyEducationalProgram(competency_id=competency.id, educational_program_id=ep_id)
                        session.add(assoc); updated = True
                    else: logger.warning(f"Educational Program with ID {ep_id} not found when adding link for competency {comp_id}. Skipping.")
            session.flush()
        
        if updated:
            session.add(competency)
            session.flush()
        
        session.refresh(competency)
        return competency.to_dict(rules=['-indicators'], include_type=True, include_educational_programs=True)

    except IntegrityError as e: logger.error(f"Database IntegrityError updating competency {comp_id}: {e}", exc_info=True); raise e
    except SQLAlchemyError as e: logger.error(f"Database error updating competency {comp_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error updating competency {comp_id}: {e}", exc_info=True); raise e

def delete_competency(comp_id: int, session: Session) -> bool:
    try:
         comp_to_delete = session.query(Competency).get(comp_id)
         if not comp_to_delete: logger.warning(f"Competency {comp_id} not found for deletion."); return False
         
         session.delete(comp_to_delete)
         return True
    except SQLAlchemyError as e: logger.error(f"Database error deleting competency {comp_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error deleting competency {comp_id}: {e}", exc_info=True); raise e

def get_all_indicators() -> List[Dict[str, Any]]:
    try:
        indicators = local_db.session.query(Indicator).options(joinedload(Indicator.competency)).all()
        result = []
        for ind in indicators:
             ind_dict = ind.to_dict(rules=['-labor_functions', '-matrix_entries'])
             if ind.competency: ind_dict['competency_code'] = ind.competency.code; ind_dict['competency_name'] = ind.competency.name
             result.append(ind_dict)
        return result
    except Exception as e: logger.error(f"Error fetching all indicators: {e}", exc_info=True); raise

def get_indicator_details(ind_id: int) -> Optional[Dict[str, Any]]:
    try:
        indicator = local_db.session.query(Indicator).options(joinedload(Indicator.competency)).get(ind_id)
        if not indicator: logger.warning(f"Indicator with id {ind_id} not found."); return None
        result = indicator.to_dict(rules=['-competency', '-labor_functions', '-matrix_entries'])
        if indicator.competency: result['competency_code'] = indicator.competency.code; result['competency_name'] = indicator.competency.name
        return result
    except Exception as e: logger.error(f"Error fetching indicator {ind_id} details: {e}", exc_info=True); raise

def create_indicator(data: Dict[str, Any], session: Session) -> Optional[Indicator]:
    required_fields = ['competency_id', 'code', 'formulation']
    if not all(field in data and data[field] is not None and str(data[field]).strip() for field in required_fields):
        raise ValueError("Отсутствуют обязательные поля: competency_id, code, formulation.")
    try:
        competency = session.query(Competency).get(data['competency_id'])
        if not competency: raise ValueError(f"Родительская компетенция с ID '{data['competency_id']}' не найдена.")
        
        existing_indicator = session.query(Indicator).filter_by(code=str(data['code']).strip(), competency_id=data['competency_id']).first()
        if existing_indicator: raise IntegrityError(f"Indicator with code {data['code']} already exists for competency {data['competency_id']}.", {}, None)
        
        selected_ps_elements_ids = data.get('selected_ps_elements_ids')
        if selected_ps_elements_ids is not None and not isinstance(selected_ps_elements_ids, dict):
            logger.warning(f"Invalid format for selected_ps_elements_ids: {type(selected_ps_elements_ids)}. Must be a dict. Ignoring.")
            selected_ps_elements_ids = None # Or default to empty dict

        indicator = Indicator(
            competency_id=data['competency_id'], code=str(data['code']).strip(), formulation=str(data['formulation']).strip(),
            source=str(data['source']).strip() if data.get('source') is not None else None,
            selected_ps_elements_ids=selected_ps_elements_ids
        )
        session.add(indicator); session.flush(); return indicator
    except IntegrityError as e: logger.error(f"Database IntegrityError creating indicator: {e}", exc_info=True); raise e
    except SQLAlchemyError as e: logger.error(f"Database error creating indicator: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error creating indicator: {e}", exc_info=True); raise e

def update_indicator(ind_id: int, data: Dict[str, Any], session: Session) -> Optional[Indicator]:
    if not data: raise ValueError("Отсутствуют данные для обновления.")
    try:
        indicator = session.query(Indicator).get(ind_id)
        if not indicator: return None
        
        allowed_fields = {'code', 'formulation', 'source', 'selected_ps_elements_ids'}
        updated = False
        
        for field in data:
            if field in allowed_fields:
                 processed_value = str(data[field]).strip() if data[field] is not None else None
                 if field == 'source' and processed_value == '': processed_value = None
                 
                 if field == 'code' and processed_value != indicator.code:
                      existing_with_new_code = session.query(Indicator).filter_by(
                           code=processed_value, competency_id=indicator.competency_id
                      ).first()
                      if existing_with_new_code and existing_with_new_code.id != indicator.id:
                           raise IntegrityError(f"Indicator with code {processed_value} already exists for competency {indicator.competency_id}.", {}, None)
                 
                 if field == 'selected_ps_elements_ids':
                     if not isinstance(data[field], dict):
                         logger.warning(f"Invalid format for selected_ps_elements_ids received for indicator {ind_id}: {type(data[field])}. Must be a dict. Skipping update for this field.")
                         continue
                     if indicator.selected_ps_elements_ids != data[field]:
                         indicator.selected_ps_elements_ids = data[field]
                         updated = True
                 elif getattr(indicator, field) != processed_value:
                     setattr(indicator, field, processed_value)
                     updated = True
            else: logger.warning(f"Ignoring field '{field}' for update of ind {ind_id} as it is not allowed via this endpoint.")
        
        if updated:
            session.add(indicator); session.flush()
        
        session.refresh(indicator); return indicator

    except IntegrityError as e: logger.error(f"Database IntegrityError updating indicator {ind_id}: {e}", exc_info=True); raise e
    except SQLAlchemyError as e: logger.error(f"Database error updating indicator {ind_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error updating indicator {ind_id}: {e}", exc_info=True); raise e

def delete_indicator(ind_id: int, session: Session) -> bool:
    try:
         ind_to_delete = session.query(Indicator).get(ind_id)
         if not ind_to_delete: logger.warning(f"Indicator {ind_id} not found for deletion."); return False
         
         session.delete(ind_to_delete)
         return True
    except SQLAlchemyError as e: logger.error(f"Database error deleting indicator {ind_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error deleting indicator {ind_id}: {e}", exc_info=True); raise e

def parse_fgos_file(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    try:
        parsed_data = fgos_parser.parse_fgos_pdf(file_bytes, filename)
        if not parsed_data or not parsed_data.get('metadata'):
             logger.warning(f"Parsing failed or returned insufficient metadata for {filename}")
             if not parsed_data: raise ValueError("Parser returned empty data.")
             if not parsed_data.get('metadata'): raise ValueError("Failed to extract metadata from FGOS file.")
        return parsed_data
    except ValueError as e: logger.error(f"Parser ValueError for {filename}: {e}"); raise e
    except Exception as e: logger.error(f"Unexpected error parsing {filename}: {e}", exc_info=True); raise Exception(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")

def save_fgos_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[FgosVo]:
    if not parsed_data or not parsed_data.get('metadata'):
        logger.warning("No parsed data or metadata provided for saving."); return None
    
    metadata = parsed_data.get('metadata', {})
    fgos_number = metadata.get('order_number')
    fgos_date_str = metadata.get('order_date')

    fgos_date_obj = None
    if isinstance(fgos_date_str, str):
        fgos_date_obj = parse_date_string(fgos_date_str)
    elif isinstance(fgos_date_str, datetime.datetime):
        fgos_date_obj = fgos_date_str.date()
    elif isinstance(fgos_date_str, datetime.date):
        fgos_date_obj = fgos_date_str

    fgos_direction_code = metadata.get('direction_code')
    fgos_education_level = metadata.get('education_level')
    fgos_generation_raw = metadata.get('generation')
    
    fgos_generation = str(fgos_generation_raw).strip() if fgos_generation_raw is not None else ''
    # Костыль
    if not fgos_generation or fgos_generation.lower() != '3++':
        fgos_generation = '3++'
        logger.warning(f"FGOS generation was missing, empty or 'null' for '{filename}'. Defaulting to '{fgos_generation}'.")
    else:
        fgos_generation = str(fgos_generation)

    fgos_direction_name = metadata.get('direction_name')

    if not fgos_date_obj:
        logger.error(f"FGOS date '{fgos_date_str}' from parsed data could not be converted to a datetime.date object. Cannot save.")
        raise ValueError(f"FGOS date '{fgos_date_str}' is not in expected date format (YYYY-MM-DD) or invalid after re-parsing.")

    if not all((fgos_number, fgos_direction_code, fgos_education_level)):
        logger.error("Missing core metadata from parsed data for saving (number, direction_code, or education_level).")
        raise ValueError("Missing core FGOS metadata from parsed data for saving.")

    recommended_ps_raw_data = parsed_data.get('recommended_ps', [])
    if not isinstance(recommended_ps_raw_data, list) or \
       not all(isinstance(item, dict) for item in recommended_ps_raw_data):
        logger.warning("Parsed recommended_ps data is not a list of dictionaries. Skipping raw data storage.")
        recommended_ps_raw_data = []
    
    clean_recommended_ps_for_json = []
    for ps_item in recommended_ps_raw_data:
        clean_item = ps_item.copy()
        if 'approval_date' in clean_item and isinstance(clean_item['approval_date'], datetime.date):
            clean_item['approval_date'] = clean_item['approval_date'].isoformat()
        clean_recommended_ps_for_json.append(clean_item)

    try:
        existing_fgos = session.query(FgosVo).filter(
            FgosVo.direction_code == fgos_direction_code,
            FgosVo.education_level == fgos_education_level,
            FgosVo.number == fgos_number,
            FgosVo.date == fgos_date_obj
        ).first()
        
        fgos_vo = None
        if existing_fgos:
            if force_update:
                logger.info(f"Existing FGOS found ({existing_fgos.id}). Force update. Deleting old comps/links...")
                session.query(Competency).filter_by(fgos_vo_id=existing_fgos.id).delete(synchronize_session='fetch')
                session.query(FgosRecommendedPs).filter_by(fgos_vo_id=existing_fgos.id).delete(synchronize_session='fetch')
                session.flush()

                fgos_vo = existing_fgos
                fgos_vo.direction_name = fgos_direction_name or 'Not specified'
                fgos_vo.generation = fgos_generation
                fgos_vo.file_path = filename
                fgos_vo.recommended_ps_parsed_data = clean_recommended_ps_for_json
                session.add(fgos_vo)
                session.flush()
            else:
                logger.warning(f"FGOS with same key data already exists ({existing_fgos.id}). Skipping save.")
                raise IntegrityError("ФГОС с этим направлением, номером и датой уже существует.", {}, None)
        else:
            fgos_vo = FgosVo(
                number=fgos_number, date=fgos_date_obj, direction_code=fgos_direction_code,
                direction_name=fgos_direction_name or 'Not specified', education_level=fgos_education_level,
                generation=fgos_generation, file_path=filename,
                recommended_ps_parsed_data=clean_recommended_ps_for_json
            )
            session.add(fgos_vo)
            session.flush()

        comp_types_map = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
        if not comp_types_map:
            logger.error("CompetencyType (УК, ОПК) not found. Cannot save competencies.")
            raise ValueError("CompetencyType (УК, ОПК) not found. Please seed initial competency types.")
        
        saved_competencies_count = 0
        all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])
        
        for parsed_comp in all_parsed_competencies:
            comp_code = parsed_comp.get('code')
            comp_name = parsed_comp.get('name')
            comp_category_name = parsed_comp.get('category_name')
            
            if not comp_code or not comp_name:
                logger.warning(f"Skipping competency due to missing code/name: {parsed_comp}"); continue
            
            comp_prefix = comp_code.split('-')[0].upper()
            comp_type = comp_types_map.get(comp_prefix)
            
            if not comp_type:
                logger.warning(f"Skipping competency {comp_code}: Competency type {comp_prefix} not found (must be УК or ОПК)."); continue
            
            existing_comp_for_fgos = session.query(Competency).filter_by(
                code=comp_code, competency_type_id=comp_type.id, fgos_vo_id=fgos_vo.id
            ).first()
            if existing_comp_for_fgos:
                logger.warning(f"Competency {comp_code} already exists for FGOS {fgos_vo.id}. Skipping."); continue
            
            competency = Competency(
                competency_type_id=comp_type.id,
                fgos_vo_id=fgos_vo.id,
                code=comp_code,
                name=comp_name,
                category_name=comp_category_name
            )
            session.add(competency)
            session.flush()
            saved_competencies_count += 1
        
        logger.info(f"Saved {saved_competencies_count} competencies for FGOS {fgos_vo.id}.")
        
        if len(recommended_ps_raw_data) > 0:
             ps_codes_to_find = [ps_data['code'] for ps_data in recommended_ps_raw_data if ps_data.get('code')]
             existing_prof_standards = session.query(ProfStandard).filter(ProfStandard.code.in_(ps_codes_to_find)).all()
             ps_by_code = {ps.code: ps for ps in existing_prof_standards}
             
             linked_ps_count = 0
             for ps_data in recommended_ps_raw_data:
                ps_code = ps_data.get('code')
                ps_name_from_doc = ps_data.get('name')
                
                if not ps_code: continue
                
                prof_standard = ps_by_code.get(ps_code)
                if prof_standard:
                    existing_link = session.query(FgosRecommendedPs).filter_by(fgos_vo_id=fgos_vo.id, prof_standard_id=prof_standard.id).first()
                    if not existing_link:
                        link = FgosRecommendedPs(
                            fgos_vo_id=fgos_vo.id,
                            prof_standard_id=prof_standard.id,
                            is_mandatory=False,
                            description=ps_name_from_doc
                        )
                        session.add(link)
                        linked_ps_count += 1
                    else:
                        if existing_link.description != ps_name_from_doc:
                            existing_link.description = ps_name_from_doc
                            session.add(existing_link)
                else:
                    logger.warning(f"Recommended PS with code {ps_code} (name: {ps_name_from_doc}) not found in DB. Skipping link in FgosRecommendedPs.")
             logger.info(f"Queued {linked_ps_count} new recommended PS links for FGOS {fgos_vo.id}.")
        
        return fgos_vo
    except IntegrityError as e:
        logger.error(f"Integrity error for FGOS from '{filename}': {e}", exc_info=True)
        session.rollback()
        raise e
    except SQLAlchemyError as e:
        logger.error(f"Database error for FGOS from '{filename}': {e}", exc_info=True)
        session.rollback()
        raise e
    except Exception as e:
        logger.error(f"Unexpected error saving FGOS: {e}", exc_info=True)
        session.rollback()
        raise e

def get_fgos_list() -> List[FgosVo]:
    try: return local_db.session.query(FgosVo).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()
    except SQLAlchemyError as e: logger.error(f"Database error fetching FGOS list: {e}", exc_info=True); return []
    except Exception as e: logger.error(f"Unexpected error fetching FGOS list: {e}", exc_info=True); return []

def get_fgos_details(fgos_id: int) -> Optional[Dict[str, Any]]:
    try:
        session: Session = local_db.session
        fgos = session.query(FgosVo).options(
            selectinload(FgosVo.competencies).selectinload(Competency.indicators),
            selectinload(FgosVo.competencies).selectinload(Competency.competency_type),
            selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard)
        ).get(fgos_id)
        if not fgos: logger.warning(f"FGOS with id {fgos_id} not found."); return None
        
        details = fgos.to_dict(rules=['-competencies', '-recommended_ps_assoc', '-educational_programs'])
        
        # Process competencies (UK/OPK)
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
        
        recommended_ps_info_for_display = []
        parsed_recommended_ps_from_doc = fgos.recommended_ps_parsed_data
        
        if parsed_recommended_ps_from_doc and isinstance(parsed_recommended_ps_from_doc, list):
            loaded_ps_map = {assoc.prof_standard.code: assoc.prof_standard
                             for assoc in fgos.recommended_ps_assoc if assoc.prof_standard}
 
            for ps_data_from_doc in parsed_recommended_ps_from_doc:
                ps_code = ps_data_from_doc.get('code')
                if not ps_code: continue
 
                loaded_ps = loaded_ps_map.get(ps_code)
                
                item_to_add = {
                    'id': loaded_ps.id if loaded_ps else None,
                    'code': ps_code,
                    'name': loaded_ps.name if loaded_ps else ps_data_from_doc.get('name'), # Use loaded name if available, else parsed
                    'is_loaded': bool(loaded_ps),
                    'approval_date': ps_data_from_doc.get('approval_date')
                }
                recommended_ps_info_for_display.append(item_to_add)
            
            recommended_ps_info_for_display.sort(key=lambda x: x['code'])
        
        details['recommended_ps'] = recommended_ps_info_for_display
        return details
    except SQLAlchemyError as e: logger.error(f"Database error fetching FGOS {fgos_id} details: {e}", exc_info=True); return None
    except Exception as e: logger.error(f"Unexpected error fetching FGOS {fgos_id} details: {e}", exc_info=True); return None

def delete_fgos(fgos_id: int, session: Session, delete_related_competencies: bool = False) -> bool:
    try:
         fgos_to_delete = session.query(FgosVo).get(fgos_id)
         if not fgos_to_delete: logger.warning(f"FGOS with id {fgos_id} not found for deletion."); return False
         
         if delete_related_competencies:
             logger.info(f"Attempting to delete related competencies for FGOS {fgos_id}.")
             # SQLAlchemy will handle cascade delete for Competency because of cascade="all, delete-orphan" on FgosVo.competencies relationship.
             # However, if delete_related_competencies is optional, we might need to manually delete here if relationships aren't configured for it.
             # Assuming cascade is set, no explicit query needed here.
             pass

         session.delete(fgos_to_delete)
         return True
    except SQLAlchemyError as e: logger.error(f"Database error deleting FGOS {fgos_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error deleting FGOS {fgos_id}: {e}", exc_info=True); raise e

def handle_prof_standard_upload_parsing(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Handles the parsing of a PS file after upload. Calls the appropriate parser orchestrator."""
    return parsers.parse_prof_standard(file_bytes, filename)


def save_prof_standard_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[ProfStandard]:
    """Saves the parsed professional standard data (including structure) to the database."""
    ps_code = parsed_data.get('code'); ps_name = parsed_data.get('name'); generalized_labor_functions_data = parsed_data.get('generalized_labor_functions', [])
    if not ps_code or not ps_name: raise ValueError("Неполные данные ПС для сохранения: отсутствует код или название.")
    if not isinstance(generalized_labor_functions_data, list): raise ValueError("Неверный формат данных структуры ПС.")

    order_date_obj = parse_date_string(parsed_data.get('order_date')) if isinstance(parsed_data.get('order_date'), str) else parsed_data.get('order_date')
    if order_date_obj is None and parsed_data.get('order_date') is not None: logger.warning(f"Could not parse order_date '{parsed_data.get('order_date')}' to datetime.date object.")

    registration_date_obj = parse_date_string(parsed_data.get('registration_date')) if isinstance(parsed_data.get('registration_date'), str) else parsed_data.get('registration_date')
    if registration_date_obj is None and parsed_data.get('registration_date') is not None: logger.warning(f"Could not parse registration_date '{parsed_data.get('registration_date')}' to datetime.date object.")

    try:
        existing_ps = session.query(ProfStandard).filter_by(code=ps_code).first()
        current_ps = None

        if existing_ps:
            if force_update:
                logger.info(f"Existing PS found ({existing_ps.id}). Force update. Deleting old structure and updating metadata...")
                session.query(GeneralizedLaborFunction).filter_by(prof_standard_id=existing_ps.id).delete(synchronize_session='fetch')
                session.flush()

                existing_ps.name = ps_name
                existing_ps.order_number = parsed_data.get('order_number')
                existing_ps.order_date = order_date_obj
                existing_ps.registration_number = parsed_data.get('registration_number')
                existing_ps.registration_date = registration_date_obj
                existing_ps.activity_area_name = parsed_data.get('activity_area_name')
                existing_ps.activity_purpose = parsed_data.get('activity_purpose')

                session.add(existing_ps); current_ps = existing_ps
            else: raise IntegrityError(f"Профессиональный стандарт с кодом {ps_code} уже существует.", {}, None)
        else:
            current_ps = ProfStandard(
                code=ps_code, name=ps_name, order_number=parsed_data.get('order_number'), order_date=order_date_obj,
                registration_number=parsed_data.get('registration_number'), registration_date=registration_date_obj,
                activity_area_name=parsed_data.get('activity_area_name'), activity_purpose=parsed_data.get('activity_purpose')
            )
            session.add(current_ps); session.flush()

        for otf_data in generalized_labor_functions_data:
            otf_code = otf_data.get('code'); otf_name = otf_data.get('name'); otf_level = otf_data.get('qualification_level'); tf_list_data = otf_data.get('labor_functions', [])

            if not otf_code or not otf_name or not isinstance(tf_list_data, list): continue

            new_otf = GeneralizedLaborFunction(prof_standard_id=current_ps.id, code=otf_code, name=otf_name, qualification_level=otf_level)
            session.add(new_otf); session.flush()

            for tf_data in tf_list_data:
                tf_code = tf_data.get('code'); tf_name = tf_data.get('name'); tf_level = tf_data.get('qualification_level')
                la_list_data = tf_data.get('labor_actions', []); rs_list_data = tf_data.get('required_skills', []); rk_list_data = tf_data.get('required_knowledge', [])

                if not tf_code or not tf_name or not isinstance(la_list_data, list) or \
                   not isinstance(rs_list_data, list) or not isinstance(rk_list_data, list): continue

                new_tf = LaborFunction(generalized_labor_function_id=new_otf.id, code=tf_code, name=tf_name, qualification_level=tf_level)
                session.add(new_tf); session.flush()

                for i, la_data in enumerate(la_list_data):
                     la_description = la_data.get('description')
                     if la_description: session.add(LaborAction(labor_function_id=new_tf.id, description=la_description.strip(), order=la_data.get('order', i)))

                for i, rs_data in enumerate(rs_list_data):
                     rs_description = rs_data.get('description')
                     if rs_description: session.add(RequiredSkill(labor_function_id=new_tf.id, description=rs_description.strip(), order=rs_data.get('order', i)))
                                
                for i, rk_data in enumerate(rk_list_data):
                     rk_description = rk_data.get('description')
                     if rk_description: session.add(RequiredKnowledge(labor_function_id=new_tf.id, description=rk_description.strip(), order=rk_data.get('order', i)))

        return current_ps

    except IntegrityError as e: logger.error(f"Integrity error saving PS '{ps_code}': {e}", exc_info=True); raise
    except SQLAlchemyError as e: logger.error(f"Database error saving PS '{ps_code}': {e}", exc_info=True); raise
    except Exception as e: logger.error(f"Unexpected error saving PS '{ps_code}': {e}", exc_info=True); raise

def get_prof_standards_list() -> List[Dict[str, Any]]:
    """
    Fetches list of all professional standards, including information about
    which FGOS recommends them. Merges actual loaded PS with placeholders from FGOS recommendations.
    Returns a list of dictionaries for direct JSON serialization.
    """
    try:
        session = local_db.session
        
        saved_prof_standards_db = session.query(ProfStandard).options(
            selectinload(ProfStandard.fgos_assoc).selectinload(FgosRecommendedPs.fgos)
        ).all()
        
        saved_ps_map = {ps.code: ps for ps in saved_prof_standards_db}
        
        all_fgos = session.query(FgosVo).all()
        
        # Use a dictionary to combine all unique PS (actual + placeholders)
        # Value: A dict representing the combined PS, similar to ProfStandardListItem
        combined_ps_data: Dict[str, Dict[str, Any]] = {}

        for ps in saved_prof_standards_db:
            ps_dict = ps.to_dict(rules=['-fgos_assoc', '-generalized_labor_functions', '-educational_program_assoc'])
            ps_dict['is_loaded'] = True
            ps_dict['recommended_by_fgos'] = []
            combined_ps_data[ps.code] = ps_dict

        # Populate `recommended_by_fgos` for loaded PS from `fgos_assoc`
        for ps in saved_prof_standards_db:
            if ps.fgos_assoc:
                for assoc in ps.fgos_assoc:
                    if assoc.fgos:
                        fgos_info = {
                            'id': assoc.fgos.id,
                            'code': assoc.fgos.direction_code,
                            'name': assoc.fgos.direction_name,
                            'generation': assoc.fgos.generation,
                            'number': assoc.fgos.number,
                            'date': assoc.fgos.date.isoformat() if assoc.fgos.date else None,
                        }
                        combined_ps_data[ps.code]['recommended_by_fgos'].append(fgos_info)
            combined_ps_data[ps.code]['recommended_by_fgos'].sort(key=lambda x: (x['code'], x.get('date', '')))

        # Add placeholders from FGOS recommended lists
        for fgos in all_fgos:
            parsed_recommended_ps = fgos.recommended_ps_parsed_data
            if parsed_recommended_ps and isinstance(parsed_recommended_ps, list):
                for ps_item_from_fgos in parsed_recommended_ps:
                    ps_code = ps_item_from_fgos.get('code')
                    if not ps_code: continue

                    if ps_code not in combined_ps_data:
                        # This is a placeholder PS
                        combined_ps_data[ps_code] = {
                            'id': None,
                            'code': ps_code,
                            'name': ps_item_from_fgos.get('name'),
                            'order_number': None,
                            'order_date': ps_item_from_fgos.get('approval_date').isoformat() if isinstance(ps_item_from_fgos.get('approval_date'), datetime.date) else ps_item_from_fgos.get('approval_date'),
                            'registration_number': None,
                            'registration_date': None,
                            'is_loaded': False,
                            'recommended_by_fgos': []
                        }
                    # Add FGOS to recommended_by_fgos list for current PS (loaded or placeholder)
                    fgos_info_for_ps = {
                        'id': fgos.id,
                        'code': fgos.direction_code,
                        'name': fgos.direction_name,
                        'generation': fgos.generation,
                        'number': fgos.number,
                        'date': fgos.date.isoformat() if fgos.date else None,
                    }
                    # Avoid duplicate entries if the same FGOS recommends the same PS multiple times
                    # Check if fgos_info_for_ps (identified by id) is already in the recommended_by_fgos list for this PS code
                    if not any(entry['id'] == fgos_info_for_ps['id'] for entry in combined_ps_data[ps_code]['recommended_by_fgos']):
                        combined_ps_data[ps_code]['recommended_by_fgos'].append(fgos_info_for_ps)


        for ps_code in combined_ps_data:
            combined_ps_data[ps_code]['recommended_by_fgos'].sort(key=lambda x: (x['code'], x.get('date', '')))

        result = sorted(list(combined_ps_data.values()), key=lambda x: x['code'])
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching ProfStandards list: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching ProfStandards list: {e}", exc_info=True)
        return []

def get_prof_standard_details(ps_id: int) -> Optional[Dict[str, Any]]:
    try:
        session: Session = local_db.session
        ps = session.query(ProfStandard).options(
            selectinload(ProfStandard.generalized_labor_functions).selectinload(GeneralizedLaborFunction.labor_functions).selectinload(LaborFunction.labor_actions),
            selectinload(ProfStandard.generalized_labor_functions).selectinload(GeneralizedLaborFunction.labor_functions).selectinload(LaborFunction.required_skills),
            selectinload(ProfStandard.generalized_labor_functions).selectinload(GeneralizedLaborFunction.labor_functions).selectinload(LaborFunction.required_knowledge)
        ).get(ps_id)
        if not ps: logger.warning(f"PS with ID {ps_id} not found."); return None
        
        details = ps.to_dict(rules=['-generalized_labor_functions', '-fgos_assoc', '-educational_program_assoc'])
        
        otf_list = []
        if ps.generalized_labor_functions:
            sorted_otfs = sorted(ps.generalized_labor_functions, key=lambda otf_item: otf_item.code)
            for otf_item in sorted_otfs:
                otf_dict = otf_item.to_dict(rules=['-prof_standard', '-labor_functions'])
                otf_dict['labor_functions'] = []
                if otf_item.labor_functions:
                    sorted_tfs = sorted(otf_item.labor_functions, key=lambda tf_item: tf_item.code)
                    for tf_item in sorted_tfs:
                        tf_dict = tf_item.to_dict(rules=['-generalized_labor_function', '-labor_actions', '-required_skills', '-required_knowledge', '-indicators', '-competencies'])
                        tf_dict['labor_actions'] = sorted([la.to_dict() for la in tf_item.labor_actions], key=lambda x: x.get('order', 0) if x.get('order') is not None else float('inf'))
                        tf_dict['required_skills'] = sorted([rs.to_dict() for rs in tf_item.required_skills], key=lambda x: x.get('order', 0) if x.get('order') is not None else float('inf'))
                        tf_dict['required_knowledge'] = sorted([rk.to_dict() for rk in tf_item.required_knowledge], key=lambda x: x.get('order', 0) if x.get('order') is not None else float('inf'))
                        otf_dict['labor_functions'].append(tf_dict)
                otf_list.append(otf_dict)
        details['generalized_labor_functions'] = otf_list
        
        return details
    except SQLAlchemyError as e: logger.error(f"Database error fetching PS {ps_id} details: {e}", exc_info=True); return None
    except Exception as e: logger.error(f"Unexpected error fetching PS {ps_id} details: {e}", exc_info=True); return None

def delete_prof_standard(ps_id: int, session: Session) -> bool:
    try:
         ps_to_delete = session.query(ProfStandard).get(ps_id)
         if not ps_to_delete: logger.warning(f"ProfStandard {ps_id} not found for deletion."); return False
         
         session.delete(ps_to_delete)
         return True
    except SQLAlchemyError as e: logger.error(f"Database error deleting PS {ps_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error deleting PS {ps_id}: {e}", exc_info=True); raise e
