import datetime
import logging
import io
from typing import Dict, List, Any, Optional

from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from maps.models import db as local_db
from ..models import FgosVo, Competency, CompetencyType, FgosRecommendedPs, ProfStandard

from .. import fgos_parser
from .. import nlp_logic
from ..parsing_utils import parse_date_string
from .uk_pk_generation import _shift_competency_codes

logger = logging.getLogger(__name__)

def parse_fgos_file(file_bytes: bytes, filename: str) -> dict:
    try:
        text_content = fgos_parser.extract_text(io.BytesIO(file_bytes))
        parsed_data = nlp_logic.parse_fgos_with_gemini(text_content)
        if not parsed_data or not parsed_data.get('metadata'):
            logger.warning(f"Parsing failed or returned insufficient metadata for {filename}")
            if not parsed_data: raise ValueError("Parser returned empty data.")
            if not parsed_data.get('metadata'): raise ValueError("Failed to extract metadata from FGOS file.")
        return parsed_data
    except ValueError as e:
        logger.error(f"Parser ValueError for {filename}: {e}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error parsing {filename}: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")

def save_fgos_data(parsed_data: dict, filename: str, session: Session, force_update: bool = False) -> FgosVo:
    if not parsed_data or not parsed_data.get('metadata'):
        logger.warning("No parsed data or metadata provided for saving.")
        return None
    
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
    if not fgos_generation or fgos_generation.lower() == 'null':
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
            session.flush() # Flush to get fgos_vo.id

        comp_types_map = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
        if not comp_types_map.get('УК') or not comp_types_map.get('ОПК'):
            logger.error("CompetencyType (УК, ОПК) not found. Cannot save competencies.")
            raise ValueError("CompetencyType (УК, ОПК) not found. Please seed initial competency types.")
        
        saved_competencies_count = 0
        all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])
        
        for parsed_comp in all_parsed_competencies:
            comp_code = parsed_comp.get('code')
            comp_name = parsed_comp.get('name')
            comp_category_name = parsed_comp.get('category_name')
            
            if not comp_code or not comp_name:
                logger.warning(f"Skipping competency due to missing code/name: {parsed_comp}")
                continue
            
            comp_prefix = comp_code.split('-')[0].upper()
            comp_type = comp_types_map.get(comp_prefix)
            
            if not comp_type:
                logger.warning(f"Skipping competency {comp_code}: Competency type {comp_prefix} not found (must be УК or ОПК).")
                continue
            
            existing_comp_for_fgos = session.query(Competency).filter_by(
                code=comp_code, competency_type_id=comp_type.id, fgos_vo_id=fgos_vo.id
            ).first()
            if existing_comp_for_fgos:
                logger.warning(f"Competency {comp_code} already exists for FGOS {fgos_vo.id}. Skipping.")
                continue
            
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
                    existing_link = session.query(FgosRecommendedPs).filter_by(
                        fgos_vo_id=fgos_vo.id, 
                        prof_standard_id=prof_standard.id
                    ).first()

                    if not existing_link:
                        link = FgosRecommendedPs(
                            fgos_vo_id=fgos_vo.id,
                            prof_standard_id=prof_standard.id,
                            is_mandatory=False,
                            description=ps_name_from_doc
                        )
                        session.add(link)
                        linked_ps_count += 1
                    elif existing_link.description != ps_name_from_doc :
                        existing_link.description = ps_name_from_doc
                        session.add(existing_link)
                else:
                    logger.warning(f"Recommended PS with code {ps_code} (name: {ps_name_from_doc}) not found in DB. Skipping link in FgosRecommendedPs for FGOS {fgos_vo.id}.")
            if linked_ps_count > 0:
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

def get_fgos_list() -> list:
    try:
        return local_db.session.query(FgosVo).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching FGOS list: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching FGOS list: {e}", exc_info=True)
        return []

def get_fgos_details(fgos_id: int) -> dict:
    try:
        session: Session = local_db.session
        fgos = session.query(FgosVo).options(
            selectinload(FgosVo.competencies).selectinload(Competency.indicators),
            selectinload(FgosVo.competencies).selectinload(Competency.competency_type),
            selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard)
        ).get(fgos_id)
        if not fgos:
            logger.warning(f"FGOS with id {fgos_id} not found.")
            return None
        
        details = fgos.to_dict(rules=['-competencies', '-recommended_ps_assoc', '-educational_programs'])
        
        uk_competencies_data = []
        opk_competencies_data = []

        def sort_key_competency(c):
            type_code_order = {'УК': 1, 'ОПК': 2}.get(c.competency_type.code if c.competency_type else 'ZZZ', 99)
            return (type_code_order, c.code)

        sorted_competencies = sorted(fgos.competencies, key=sort_key_competency)

        for comp in sorted_competencies:
            if comp.competency_type and comp.competency_type.code in ['УК', 'ОПК']:
                comp_dict = comp.to_dict(rules=['-fgos', '-based_on_labor_function', '-indicators', '-competency_type', '-matrix_entries', '-educational_programs_assoc'])
                comp_dict['type_code'] = comp.competency_type.code
                comp_dict['indicators'] = []
                if comp.indicators:
                    sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                    comp_dict['indicators'] = [ind.to_dict(rules=['-competency', '-labor_functions', '-matrix_entries']) for ind in sorted_indicators]
                
                if comp.competency_type.code == 'УК':
                    uk_competencies_data.append(comp_dict)
                elif comp.competency_type.code == 'ОПК':
                    opk_competencies_data.append(comp_dict)
        details['uk_competencies'] = uk_competencies_data
        details['opk_competencies'] = opk_competencies_data
        
        recommended_ps_info_for_display = []
        parsed_recommended_ps_from_doc = fgos.recommended_ps_parsed_data
        
        if parsed_recommended_ps_from_doc and isinstance(parsed_recommended_ps_from_doc, list):
            loaded_ps_map = {assoc.prof_standard.code: assoc.prof_standard
                             for assoc in fgos.recommended_ps_assoc if assoc.prof_standard}
 
            for ps_data_from_doc in parsed_recommended_ps_from_doc:
                ps_code = ps_data_from_doc.get('code')
                if not ps_code: continue
 
                loaded_ps = loaded_ps_map.get(ps_code)
                
                approval_date_from_doc = ps_data_from_doc.get('approval_date')
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

                item_to_add = {
                    'id': loaded_ps.id if loaded_ps else None,
                    'code': ps_code,
                    'name': loaded_ps.name if loaded_ps else ps_data_from_doc.get('name'),
                    'is_loaded': bool(loaded_ps),
                    'approval_date': approval_date_str
                }
                recommended_ps_info_for_display.append(item_to_add)
            
            recommended_ps_info_for_display.sort(key=lambda x: x['code'])
        
        details['recommended_ps'] = recommended_ps_info_for_display
        return details
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching FGOS {fgos_id} details: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching FGOS {fgos_id} details: {e}", exc_info=True)
        return None

def delete_fgos(fgos_id: int, session: Session, delete_related_competencies: bool = False) -> bool:
    try:
        fgos_to_delete = session.query(FgosVo).get(fgos_id)
        if not fgos_to_delete:
            logger.warning(f"FGOS with id {fgos_id} not found for deletion.")
            return False

        if delete_related_competencies:
            logger.info(f"FGOS {fgos_id} will be deleted. Related competencies (if cascade is set) and recommended PS links will also be deleted.")
        session.delete(fgos_to_delete)
        return True
    except SQLAlchemyError as e:
        logger.error(f"Database error deleting FGOS {fgos_id}: {e}", exc_info=True)
        raise e