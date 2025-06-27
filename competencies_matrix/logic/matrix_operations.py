import logging
from typing import Dict, List, Any, Optional

from sqlalchemy import exists
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload, joinedload

from maps.models import db as local_db
from maps.models import AupInfo as LocalAupInfo, AupData as LocalAupData, SprDiscipline

from ..models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramAup, EducationalProgramPs,
    CompetencyType, IndicatorPsLink,
    GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge,
    CompetencyEducationalProgram
)
from .aup_external import get_external_aups_list, get_external_aup_disciplines

logger = logging.getLogger(__name__)

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
                    selectinload(Competency.fgos)
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
                selectinload(Competency.educational_programs_assoc).selectinload(CompetencyEducationalProgram.educational_program),
                selectinload(Competency.based_on_labor_function)
                    .selectinload(LaborFunction.generalized_labor_function)
                    .selectinload(GeneralizedLaborFunction.prof_standard)
            ).filter(Competency.competency_type_id == pk_type.id).all()
            
            filtered_pk_competencies = []
            if educational_program:
                for pk_comp in pk_competencies:
                    if any(assoc.educational_program_id == educational_program.id for assoc in pk_comp.educational_programs_assoc):
                        filtered_pk_competencies.append(pk_comp)
                relevant_competencies.extend(filtered_pk_competencies)
            else:
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
                    comp_dict['source_document_type'] = "Ручной ввод"
                    comp_dict['source_document_code'] = "N/A"
                    comp_dict['source_document_name'] = "Введено вручную"


            if comp.based_on_labor_function:
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