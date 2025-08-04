# filepath: competencies_matrix/logic/prof_standards.py
import datetime
import logging
from typing import Dict, List, Any, Optional

from sqlalchemy import cast, Integer, text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session, selectinload

from maps.models import db as local_db
from ..models import (
    ProfStandard, FgosVo, FgosRecommendedPs,
    GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
)

from .. import parsers
from .. import exports
from ..parsing_utils import parse_date_string
from .educational_programs import get_program_details
from .error_utils import handle_db_errors

logger = logging.getLogger(__name__)

def search_prof_standards(
    search_query: str,
    ps_ids: Optional[List[int]] = None,
    offset: int = 0,
    limit: int = 50,
    qualification_levels: Optional[List[int]] = None
) -> Dict[str, Any]:
    """Ищет в профстандартах, используя полнотекстовый поиск."""
    if not search_query and not qualification_levels and (ps_ids is None or len(ps_ids) == 0):
        raise ValueError("Необходимо указать поисковый запрос, выбрать уровни квалификации или выбрать конкретные профстандарты.")
    
    if search_query and len(search_query) < 2:
        raise ValueError("Поисковый запрос должен содержать минимум 2 символа.")

    try:
        session: Session = local_db.session
        
        initial_ps_ids_set: set
        if ps_ids:
            initial_ps_ids_set = set(ps_ids)
        else:
            initial_ps_ids_set = {ps.id for ps in session.query(ProfStandard.id).all()}

        level_filtered_ps_ids: Optional[set] = None
        if qualification_levels:
            level_query = session.query(ProfStandard.id).distinct().join(
                GeneralizedLaborFunction
            ).filter(
                cast(GeneralizedLaborFunction.qualification_level, Integer).in_(qualification_levels)
            )
            level_filtered_ps_ids = {r[0] for r in level_query.all()}
            if not level_filtered_ps_ids:
                return {"total": 0, "items": [], "search_query": search_query}

        text_filtered_ps_ids: Optional[set] = None
        if search_query and len(search_query) >= 2:
            boolean_search_query = ' '.join(f'+{word}*' for word in search_query.split())
            
            ps_ids_from_ps = {r[0] for r in session.query(ProfStandard.id).filter(text("MATCH(name) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}
            ps_ids_from_otf = {r[0] for r in session.query(GeneralizedLaborFunction.prof_standard_id).filter(text("MATCH(name) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}
            ps_ids_from_tf = {r[0] for r in session.query(GeneralizedLaborFunction.prof_standard_id).join(LaborFunction).filter(text("MATCH(competencies_labor_function.name) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}
            ps_ids_from_la = {r[0] for r in session.query(GeneralizedLaborFunction.prof_standard_id).join(LaborFunction).join(LaborAction).filter(text("MATCH(competencies_labor_action.description) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}
            ps_ids_from_rs = {r[0] for r in session.query(GeneralizedLaborFunction.prof_standard_id).join(LaborFunction).join(RequiredSkill).filter(text("MATCH(competencies_required_skill.description) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}
            ps_ids_from_rk = {r[0] for r in session.query(GeneralizedLaborFunction.prof_standard_id).join(LaborFunction).join(RequiredKnowledge).filter(text("MATCH(competencies_required_knowledge.description) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}

            text_filtered_ps_ids = ps_ids_from_ps.union(ps_ids_from_otf, ps_ids_from_tf, ps_ids_from_la, ps_ids_from_rs, ps_ids_from_rk)

            if not text_filtered_ps_ids:
                return {"total": 0, "items": [], "search_query": search_query}

        final_matching_ps_ids: set = initial_ps_ids_set

        if text_filtered_ps_ids is not None:
            final_matching_ps_ids = final_matching_ps_ids.intersection(text_filtered_ps_ids)
        
        if level_filtered_ps_ids is not None:
            final_matching_ps_ids = final_matching_ps_ids.intersection(level_filtered_ps_ids)
        
        if not final_matching_ps_ids:
            return {"total": 0, "items": [], "search_query": search_query}

        final_ps_ids_list = sorted(list(final_matching_ps_ids))
        total_results = len(final_ps_ids_list)
        paginated_ids_to_fetch = final_ps_ids_list[offset : offset + limit]
        
        all_ps_to_process = []
        if paginated_ids_to_fetch:
            base_query = session.query(ProfStandard).options(
                selectinload(ProfStandard.generalized_labor_functions)
                    .selectinload(GeneralizedLaborFunction.labor_functions)
                    .options(
                        selectinload(LaborFunction.labor_actions),
                        selectinload(LaborFunction.required_skills),
                        selectinload(LaborFunction.required_knowledge)
                    )
            )
            paginated_query = base_query.filter(ProfStandard.id.in_(paginated_ids_to_fetch)).order_by(ProfStandard.code)
            all_ps_to_process = paginated_query.all()
        
        all_matching_ps_details = []
        search_query_lower = search_query.lower() if search_query else ""

        for ps in all_ps_to_process:
            ps_details = ps.to_dict(rules=['-generalized_labor_functions'])
            ps_details['name'] = ps.name
            ps_details['code'] = ps.code
            
            filtered_generalized_labor_functions = []
            for otf in ps.generalized_labor_functions:
                if qualification_levels and otf.qualification_level and int(otf.qualification_level) not in qualification_levels:
                    continue

                otf_details = otf.to_dict(rules=['-labor_functions'])
                otf_details['name'] = otf.name
                otf_details['code'] = otf.code
                
                otf_details['has_match'] = search_query_lower and search_query_lower in otf.name.lower() or False
                
                filtered_labor_functions = []
                for tf in otf.labor_functions:
                    tf_details = tf.to_dict(rules=['-labor_actions', '-required_skills', '-required_knowledge'])
                    tf_details['name'] = tf.name
                    tf_details['code'] = tf.code
                    
                    tf_name_matches = search_query_lower and search_query_lower in tf.name.lower() or False
                    
                    for la in tf.labor_actions: la.has_match = search_query_lower and search_query_lower in la.description.lower() or False
                    for rs in tf.required_skills: rs.has_match = search_query_lower and search_query_lower in rs.description.lower() or False
                    for rk in tf.required_knowledge: rk.has_match = search_query_lower and search_query_lower in rk.description.lower() or False
                    
                    tf_has_child_match = any(la.has_match for la in tf.labor_actions) or \
                                    any(rs.has_match for rs in tf.required_skills) or \
                                    any(rk.has_match for rk in tf.required_knowledge)
                                    
                    tf_details['has_match'] = tf_name_matches or tf_has_child_match
                    
                    tf_details['labor_actions'] = [la.to_dict() for la in tf.labor_actions]
                    tf_details['required_skills'] = [rs.to_dict() for rs in tf.required_skills]
                    tf_details['required_knowledge'] = [rk.to_dict() for rk in tf.required_knowledge]
                    filtered_labor_functions.append(tf_details)

                otf_details['labor_functions'] = filtered_labor_functions
                
                filtered_generalized_labor_functions.append(otf_details)

            ps_details['generalized_labor_functions'] = filtered_generalized_labor_functions
            all_matching_ps_details.append(ps_details)

        logger.info(f"Found {total_results} matching PS for query '{search_query}' and levels {qualification_levels} and ps_ids {ps_ids}. Returning {len(all_matching_ps_details)} (offset {offset}, limit {limit}).")
        return {"total": total_results, "items": all_matching_ps_details, "search_query": search_query}

    except SQLAlchemyError as e:
        logger.error(f"Database error in search_prof_standards: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in search_prof_standards: {e}", exc_info=True)
        raise

def handle_prof_standard_upload_parsing(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Handles the parsing of a PS file after upload. Calls the appropriate parser orchestrator."""
    return parsers.parse_prof_standard(file_bytes, filename)


@handle_db_errors()
def save_prof_standard_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[ProfStandard]:
    """Saves the parsed professional standard data (including structure) to the database."""
    ps_code = parsed_data.get('code')
    ps_name = parsed_data.get('name')
    generalized_labor_functions_data = parsed_data.get('generalized_labor_functions', [])
    if not ps_code or not ps_name:
        raise ValueError("Неполные данные ПС для сохранения: отсутствует код или название.")
    if not isinstance(generalized_labor_functions_data, list):
        raise ValueError("Неверный формат данных структуры ПС.")

    order_date_obj = parse_date_string(parsed_data.get('order_date')) if isinstance(parsed_data.get('order_date'), str) else parsed_data.get('order_date')
    if order_date_obj is None and parsed_data.get('order_date') is not None:
        logger.warning(f"Could not parse order_date '{parsed_data.get('order_date')}' to datetime.date object.")

    registration_date_obj = parse_date_string(parsed_data.get('registration_date')) if isinstance(parsed_data.get('registration_date'), str) else parsed_data.get('registration_date')
    if registration_date_obj is None and parsed_data.get('registration_date') is not None:
        logger.warning(f"Could not parse registration_date '{parsed_data.get('registration_date')}' to datetime.date object.")

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

            session.add(existing_ps)
            current_ps = existing_ps
        else:
            raise IntegrityError(f"Профессиональный стандарт с кодом {ps_code} уже существует.", {}, None)
    else:
        current_ps = ProfStandard(
            code=ps_code, name=ps_name, order_number=parsed_data.get('order_number'), order_date=order_date_obj,
            registration_number=parsed_data.get('registration_number'), registration_date=registration_date_obj,
            activity_area_name=parsed_data.get('activity_area_name'), activity_purpose=parsed_data.get('activity_purpose')
        )
        session.add(current_ps)
        session.flush()

    for otf_data in generalized_labor_functions_data:
        otf_code = otf_data.get('code')
        otf_name = otf_data.get('name')
        otf_level = otf_data.get('qualification_level')
        tf_list_data = otf_data.get('labor_functions', [])

        if not otf_code or not otf_name or not isinstance(tf_list_data, list):
            logger.warning(f"Skipping OTF due to missing data or invalid TF list: code={otf_code}")
            continue

        new_otf = GeneralizedLaborFunction(prof_standard_id=current_ps.id, code=otf_code, name=otf_name, qualification_level=str(otf_level) if otf_level is not None else None)
        session.add(new_otf)
        session.flush()

        for tf_data in tf_list_data:
            tf_code = tf_data.get('code')
            tf_name = tf_data.get('name')
            tf_level = tf_data.get('qualification_level')
            la_list_data = tf_data.get('labor_actions', [])
            rs_list_data = tf_data.get('required_skills', [])
            rk_list_data = tf_data.get('required_knowledge', [])

            if not tf_code or not tf_name or not isinstance(la_list_data, list) or \
                not isinstance(rs_list_data, list) or not isinstance(rk_list_data, list):
                logger.warning(f"Skipping TF under OTF {otf_code} due to missing data or invalid sub-lists: code={tf_code}")
                continue

            new_tf = LaborFunction(generalized_labor_function_id=new_otf.id, code=tf_code, name=tf_name, qualification_level=str(tf_level) if tf_level is not None else None)
            session.add(new_tf)
            session.flush()

            for i, la_data in enumerate(la_list_data):
                la_description = la_data.get('description') if isinstance(la_data, dict) else str(la_data)
                la_order = la_data.get('order', i) if isinstance(la_data, dict) else i
                if la_description:
                    session.add(LaborAction(labor_function_id=new_tf.id, description=str(la_description).strip(), order=la_order))

            for i, rs_data in enumerate(rs_list_data):
                rs_description = rs_data.get('description') if isinstance(rs_data, dict) else str(rs_data)
                rs_order = rs_data.get('order', i) if isinstance(rs_data, dict) else i
                if rs_description:
                    session.add(RequiredSkill(labor_function_id=new_tf.id, description=str(rs_description).strip(), order=rs_order))
                            
            for i, rk_data in enumerate(rk_list_data):
                rk_description = rk_data.get('description') if isinstance(rk_data, dict) else str(rk_data)
                rk_order = rk_data.get('order', i) if isinstance(rk_data, dict) else i
                if rk_description:
                    session.add(RequiredKnowledge(labor_function_id=new_tf.id, description=str(rk_description).strip(), order=rk_order))
    session.flush()
    return current_ps


@handle_db_errors(default_return=[])
def get_prof_standards_list() -> List[Dict[str, Any]]:
    """
    Fetches list of all professional standards, including information about
    which FGOS recommends them. Merges actual loaded PS with placeholders from FGOS recommendations.
    Returns a list of dictionaries for direct JSON serialization.
    """
    session = local_db.session
    
    saved_prof_standards_db = session.query(ProfStandard).options(
        selectinload(ProfStandard.fgos_assoc).selectinload(FgosRecommendedPs.fgos)
    ).all()
    
    all_fgos = session.query(FgosVo).all()
    
    combined_ps_data: Dict[str, Dict[str, Any]] = {}

    for ps in saved_prof_standards_db:
        ps_dict = ps.to_dict(rules=['-fgos_assoc', '-generalized_labor_functions', '-educational_program_assoc'])
        ps_dict['is_loaded'] = True
        ps_dict['recommended_by_fgos'] = []
        
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
                    ps_dict['recommended_by_fgos'].append(fgos_info)
        combined_ps_data[ps.code] = ps_dict

    for fgos in all_fgos:
        parsed_recommended_ps = fgos.recommended_ps_parsed_data
        if parsed_recommended_ps and isinstance(parsed_recommended_ps, list):
            for ps_item_from_fgos_doc in parsed_recommended_ps:
                ps_code = ps_item_from_fgos_doc.get('code')
                if not ps_code: continue

                fgos_recommendation_info = {
                    'id': fgos.id,
                    'code': fgos.direction_code,
                    'name': fgos.direction_name,
                    'generation': fgos.generation,
                    'number': fgos.number,
                    'date': fgos.date.isoformat() if fgos.date else None,
                }
                
                approval_date_from_doc = ps_item_from_fgos_doc.get('approval_date')
                if isinstance(approval_date_from_doc, datetime.date):
                    approval_date_str = approval_date_from_doc.isoformat()
                elif isinstance(approval_date_from_doc, str):
                    try:
                        datetime.date.fromisoformat(approval_date_from_doc)
                        approval_date_str = approval_date_from_doc
                    except ValueError:
                        parsed_date = parse_date_string(approval_date_from_doc)
                        approval_date_str = parsed_date.isoformat() if parsed_date else None
                else:
                    approval_date_str = None


                if ps_code not in combined_ps_data:
                    combined_ps_data[ps_code] = {
                        'id': None,
                        'code': ps_code,
                        'name': ps_item_from_fgos_doc.get('name'),
                        'order_number': None,
                        'order_date': approval_date_str,
                        'registration_number': None,
                        'registration_date': None,
                        'is_loaded': False,
                        'recommended_by_fgos': [fgos_recommendation_info]
                    }
                else:
                    current_recommendations = combined_ps_data[ps_code]['recommended_by_fgos']
                    if not any(rec['id'] == fgos.id for rec in current_recommendations):
                        current_recommendations.append(fgos_recommendation_info)
    
    for ps_data_item in combined_ps_data.values():
        ps_data_item['recommended_by_fgos'].sort(key=lambda x: (x['code'] or "", x.get('date', "") or ""))

    result = sorted(list(combined_ps_data.values()), key=lambda x: x['code'])
    return result

@handle_db_errors()
def get_prof_standard_details(ps_id: int) -> Optional[Dict[str, Any]]:
    session: Session = local_db.session
    ps = session.query(ProfStandard).options(
        selectinload(ProfStandard.generalized_labor_functions).selectinload(GeneralizedLaborFunction.labor_functions).options(
            selectinload(LaborFunction.labor_actions),
            selectinload(LaborFunction.required_skills),
            selectinload(LaborFunction.required_knowledge)
        )
    ).get(ps_id)
    if not ps:
        logger.warning(f"PS with ID {ps_id} not found.")
        return None
    
    details = ps.to_dict(rules=['-generalized_labor_functions', '-fgos_assoc', '-educational_program_assoc'])
    
    otf_list = []
    if ps.generalized_labor_functions:
        sorted_otfs = sorted(ps.generalized_labor_functions, key=lambda otf_item: otf_item.code or "")
        for otf_item in sorted_otfs:
            otf_dict = otf_item.to_dict(rules=['-prof_standard', '-labor_functions'])
            otf_dict['labor_functions'] = []
            if otf_item.labor_functions:
                sorted_tfs = sorted(otf_item.labor_functions, key=lambda tf_item: tf_item.code or "")
                for tf_item in sorted_tfs:
                    tf_dict = tf_item.to_dict(rules=['-generalized_labor_function', '-labor_actions', '-required_skills', '-required_knowledge', '-indicators', '-competencies'])
                    tf_dict['labor_actions'] = sorted([la.to_dict() for la in tf_item.labor_actions], key=lambda x: x.get('order', float('inf')))
                    tf_dict['required_skills'] = sorted([rs.to_dict() for rs in tf_item.required_skills], key=lambda x: x.get('order', float('inf')))
                    tf_dict['required_knowledge'] = sorted([rk.to_dict() for rk in tf_item.required_knowledge], key=lambda x: x.get('order', float('inf')))
                    otf_dict['labor_functions'].append(tf_dict)
            otf_list.append(otf_dict)
    details['generalized_labor_functions'] = otf_list
    
    return details

@handle_db_errors(default_return=False)
def delete_prof_standard(ps_id: int, session: Session) -> bool:
    ps_to_delete = session.get(ProfStandard, ps_id)
    if not ps_to_delete:
        logger.warning(f"ProfStandard {ps_id} not found for deletion.")
        return False
    
    session.delete(ps_to_delete)
    return True

def generate_prof_standard_excel_export_logic(selected_data: Dict[str, Any], opop_id: Optional[int]) -> bytes:
    """
    Готовит данные и вызывает функцию генерации Excel.
    """
    if not selected_data or not selected_data.get('profStandards'):
        raise ValueError("Нет данных для экспорта.")

    opop_data = {'direction_code': '', 'direction_name': '', 'profile_name': ''}
    if opop_id:
        program_details = get_program_details(opop_id)
        if program_details:
            opop_data['direction_code'] = program_details.get('code', '')
            opop_data['direction_name'] = program_details.get('title', '')
            opop_data['profile_name'] = program_details.get('profile', '')
    
    try:
        excel_bytes = exports.generate_tf_list_excel_export(selected_data, opop_data)
        return excel_bytes
    except Exception as e:
        logger.error(f"Error generating Excel export for TF list: {e}", exc_info=True)
        raise RuntimeError(f"Не удалось сгенерировать Excel-файл: {e}")