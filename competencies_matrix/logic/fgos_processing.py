# filepath: competencies_matrix/logic/fgos_processing.py
import datetime
import logging
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from maps.models import db as local_db
from ..models import FgosVo, Competency, CompetencyType, FgosRecommendedPs, ProfStandard

from .. import fgos_parser
from ..parsing_utils import parse_date_string
from .error_utils import handle_db_errors

logger = logging.getLogger(__name__)


def parse_fgos_file(file_bytes: bytes, filename: str) -> dict:
    """
    Оркестрирует парсинг файла ФГОС, делегируя всю работу модулю fgos_parser.
    """
    try:
        data = fgos_parser.parse_fgos_file(file_bytes, filename)
        return data
    except ValueError as e:
        logger.error(f"FGOS Processing: Parser raised ValueError for {filename}: {e}")
        raise
    except Exception as e:
        logger.error(f"FGOS Processing: Unexpected error during parsing of {filename}: {e}", exc_info=True)
        raise ValueError(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")


@handle_db_errors()
def save_fgos_data(data: dict, filename: str, session: Session, force_update: bool = False) -> Optional[FgosVo]:
    """Saves parsed FGOS data to the database."""
    if not data or not data.get('metadata'):
        logger.warning("No parsed data or metadata provided for saving.")
        return None

    meta = data.get('metadata', {})
    order_number = meta.get('order_number')
    date_str = meta.get('order_date')

    order_date = None
    if isinstance(date_str, str):
        order_date = parse_date_string(date_str)
    elif isinstance(date_str, datetime.datetime):
        order_date = date_str.date()
    elif isinstance(date_str, datetime.date):
        order_date = date_str

    if not order_date:
        logger.error(f"FGOS date '{date_str}' could not be converted to a date object. Cannot save.")
        raise ValueError(f"FGOS date '{date_str}' is invalid or not in the expected format.")

    direction_code = meta.get('direction_code')
    education_level = meta.get('education_level')

    if not all((order_number, direction_code, education_level)):
        logger.error("Missing core metadata (order_number, direction_code, or education_level).")
        raise ValueError("Missing core FGOS metadata from parsed data for saving.")

    generation_raw = meta.get('generation')
    generation = str(generation_raw).strip() if generation_raw is not None else ''
    if not generation or generation.lower() == 'null':
        generation = '3++'
        logger.warning(f"FGOS generation was missing for '{filename}'. Defaulting to '{generation}'.")

    raw_ps_list = data.get('recommended_ps', [])
    if not isinstance(raw_ps_list, list) or not all(isinstance(item, dict) for item in raw_ps_list):
        logger.warning("Parsed 'recommended_ps' data is not a list of dictionaries. Skipping.")
        raw_ps_list = []

    cleaned_ps_list = []
    for ps_item in raw_ps_list:
        clean_item = ps_item.copy()
        if 'approval_date' in clean_item and isinstance(clean_item['approval_date'], datetime.date):
            clean_item['approval_date'] = clean_item['approval_date'].isoformat()
        cleaned_ps_list.append(clean_item)

    existing_fgos = session.query(FgosVo).filter_by(
        direction_code=direction_code,
        education_level=education_level,
        number=order_number,
        date=order_date
    ).first()

    if existing_fgos:
        if force_update:
            logger.info(f"Updating existing FGOS {existing_fgos.id} for file '{filename}'.")
            fgos = existing_fgos
            fgos.direction_name = meta.get('direction_name') or 'Not specified'
            fgos.generation = generation
            fgos.file_path = filename
            fgos.recommended_ps_parsed_data = cleaned_ps_list
        else:
            logger.info(f"FGOS for '{filename}' already exists (ID: {existing_fgos.id}) and force_update is False. Skipping.")
            return existing_fgos
    else:
        logger.info(f"Creating new FGOS for file '{filename}'.")
        fgos = FgosVo(
            number=order_number,
            date=order_date,
            direction_code=direction_code,
            direction_name=meta.get('direction_name') or 'Not specified',
            education_level=education_level,
            generation=generation,
            file_path=filename,
            recommended_ps_parsed_data=cleaned_ps_list
        )
        session.add(fgos)
        session.flush()

    _sync_competencies(session, fgos, data)
    _sync_recommended_ps(session, fgos, raw_ps_list)

    return fgos


def _sync_competencies(session: Session, fgos: FgosVo, data: dict):
    """Helper to synchronize competencies for an FGOS instance."""
    comp_types = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
    if 'УК' not in comp_types or 'ОПК' not in comp_types:
        raise ValueError("Competency types 'УК' and 'ОПК' not found in the database.")

    parsed_comps = data.get('uk_competencies', []) + data.get('opk_competencies', [])
    saved_count = 0
    for comp_data in parsed_comps:
        code = comp_data.get('code')
        name = comp_data.get('name')
        category = comp_data.get('category_name')

        if not code or not name:
            logger.warning(f"Skipping competency with missing code or name: {comp_data}")
            continue

        comp_type = comp_types.get(code.split('-')[0])
        if not comp_type:
            logger.warning(f"Skipping competency with unknown type: {code}")
            continue

        comp = session.query(Competency).filter_by(code=code, fgos_vo_id=fgos.id).first()
        if not comp:
            comp = Competency(
                code=code,
                name=name,
                category_name=category,
                competency_type_id=comp_type.id,
                fgos_vo_id=fgos.id
            )
            session.add(comp)
            saved_count += 1
        else:
            comp.name = name
            comp.category_name = category
            comp.competency_type_id = comp_type.id

    if saved_count > 0:
        logger.info(f"Saved {saved_count} new competencies for FGOS {fgos.id}.")


def _sync_recommended_ps(session: Session, fgos: FgosVo, raw_ps_list: list):
    """Helper to synchronize recommended professional standards for an FGOS instance."""
    if not raw_ps_list:
        return

    session.query(FgosRecommendedPs).filter_by(fgos_vo_id=fgos.id).delete()

    for ps_data in raw_ps_list:
        ps_code = ps_data.get('code')
        if not ps_code:
            continue

        prof_standard = session.query(ProfStandard).filter_by(code=ps_code).first()
        if prof_standard:
            assoc = FgosRecommendedPs(fgos_vo_id=fgos.id, prof_standard_id=prof_standard.id)
            session.add(assoc)
        else:
            logger.warning(f"ProfStandard with code '{ps_code}' not found. Cannot link to FGOS {fgos.id}.")

    logger.info(f"Synced recommended PS for FGOS {fgos.id}.")


@handle_db_errors(default_return=[])
def get_fgos_list() -> list:
    """Fetches a list of all FGOS from the database."""
    return local_db.session.query(FgosVo).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()


@handle_db_errors()
def get_fgos_details(fgos_id: int) -> Optional[dict]:
    """Fetches detailed information for a single FGOS."""
    session: Session = local_db.session
    fgos = session.query(FgosVo).options(
        selectinload(FgosVo.competencies).selectinload(Competency.indicators),
        selectinload(FgosVo.competencies).selectinload(Competency.competency_type),
        selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard)
    ).get(fgos_id)
    if not fgos:
        return None

    details = fgos.to_dict(rules=['-competencies', '-recommended_ps_assoc', '-educational_programs'])

    uk_competencies = []
    opk_competencies = []

    def competency_sort_key(c: Competency):
        try:
            return int(c.code.split('-')[-1])
        except (ValueError, IndexError):
            return float('inf')

    sorted_competencies = sorted(fgos.competencies, key=competency_sort_key)

    for comp in sorted_competencies:
        comp_dict = comp.to_dict(rules=['-fgos', '-competency_type', '-indicators.competency'])
        comp_dict['type'] = comp.competency_type.code
        if comp.competency_type.code == 'УК':
            uk_competencies.append(comp_dict)
        elif comp.competency_type.code == 'ОПК':
            opk_competencies.append(comp_dict)

    details['uk_competencies'] = uk_competencies
    details['opk_competencies'] = opk_competencies

    recommended_ps = []
    parsed_recommended_ps = fgos.recommended_ps_parsed_data or []

    if parsed_recommended_ps and isinstance(parsed_recommended_ps, list):
        for ps_data in parsed_recommended_ps:
            ps_code = ps_data.get('code')
            prof_standard = next((assoc.prof_standard for assoc in fgos.recommended_ps_assoc if assoc.prof_standard and assoc.prof_standard.code == ps_code), None)
            recommended_ps.append({
                "code": ps_code,
                "name": ps_data.get("name"),
                "approval_date": ps_data.get("approval_date"),
                "registration_number": ps_data.get("registration_number"),
                "is_linked": prof_standard is not None,
                "id": prof_standard.id if prof_standard else None
            })

    details['recommended_ps'] = recommended_ps
    return details


@handle_db_errors(default_return=False)
def delete_fgos(fgos_id: int, session: Session, delete_related_competencies: bool = True) -> bool:
    """Deletes an FGOS and its related data from the database."""
    fgos = session.get(FgosVo, fgos_id)
    if not fgos:
        logger.warning(f"Delete failed: FGOS with ID {fgos_id} not found.")
        return False

    logger.info(f"Deleting FGOS {fgos_id} ('{fgos.direction_code} - {fgos.direction_name}')...")
    
    if delete_related_competencies:
        session.query(Competency).filter(Competency.fgos_vo_id == fgos_id).delete(synchronize_session=False)
        logger.info(f"Deleted related competencies for FGOS {fgos_id}.")

    session.delete(fgos)
    logger.info(f"FGOS {fgos_id} and related data marked for deletion.")
    return True