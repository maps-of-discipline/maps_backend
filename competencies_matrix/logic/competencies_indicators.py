# filepath: competencies_matrix/logic/competencies_indicators.py
import logging
from typing import Dict, List, Any, Optional

from sqlalchemy.orm import Session, joinedload, selectinload

from maps.models import db as local_db

from ..models import (
    Competency, Indicator, CompetencyType,
    LaborFunction, GeneralizedLaborFunction,
    CompetencyEducationalProgram
)
from .error_utils import handle_db_errors

logger = logging.getLogger(__name__)


@handle_db_errors(default_return=[])
def get_all_competencies() -> List[Dict[str, Any]]:
    """Fetches a list of all competencies with their essential source information."""
    competencies = local_db.session.query(Competency).options(
        joinedload(Competency.competency_type),
        joinedload(Competency.fgos),
        joinedload(Competency.based_on_labor_function)
            .joinedload(LaborFunction.generalized_labor_function)
            .joinedload(GeneralizedLaborFunction.prof_standard)
    ).all()
    
    result = [
        comp.to_dict(
            rules=['-indicators', '-fgos', '-based_on_labor_function', '-matrix_entries', '-educational_programs_assoc'], 
            include_type=True
        ) for comp in competencies
    ]
    return result

@handle_db_errors()
def get_competency_details(comp_id: int) -> Optional[Dict[str, Any]]:
    """Fetches detailed information for a single competency, including indicators and program links."""
    competency = local_db.session.query(Competency).options(
        joinedload(Competency.competency_type),
        joinedload(Competency.indicators),
        joinedload(Competency.fgos),
        joinedload(Competency.based_on_labor_function)
            .joinedload(LaborFunction.generalized_labor_function)
            .joinedload(GeneralizedLaborFunction.prof_standard),
        selectinload(Competency.educational_programs_assoc)
            .selectinload(CompetencyEducationalProgram.educational_program)
    ).get(comp_id)
    
    if not competency:
        logger.warning(f"Competency with id {comp_id} not found.")
        return None
    
    return competency.to_dict(
        rules=['-fgos', '-based_on_labor_function', '-matrix_entries'],
        include_indicators=True, 
        include_type=True, 
        include_educational_programs=True
    )

@handle_db_errors()
def create_competency(data: Dict[str, Any], session: Session) -> Competency:
    """Creates a new competency, primarily for Professional Competencies (ПК)."""
    required_fields = ['type_code', 'code', 'name']
    if not all(field in data and data.get(field) for field in required_fields):
        raise ValueError("Отсутствуют обязательные поля: type_code, code, name.")

    if data['type_code'] != 'ПК':
        raise ValueError(f"Этот эндпоинт предназначен только для создания ПК, получен тип '{data['type_code']}'.")

    comp_type = session.query(CompetencyType).filter_by(code=data['type_code']).first()
    if not comp_type:
        raise ValueError(f"Тип компетенции с кодом '{data['type_code']}' не найден.")

    competency = Competency(
        competency_type_id=comp_type.id,
        code=str(data['code']).strip(),
        name=str(data['name']).strip(),
        description=str(data.get('description', '')).strip() or None,
        based_on_labor_function_id=data.get('based_on_labor_function_id')
    )
    session.add(competency)
    session.flush()

    educational_program_ids = data.get('educational_program_ids', [])
    if educational_program_ids:
        for ep_id in educational_program_ids:
            assoc = CompetencyEducationalProgram(competency_id=competency.id, educational_program_id=ep_id)
            session.add(assoc)
    
    session.flush()
    return competency

@handle_db_errors()
def update_competency(comp_id: int, data: Dict[str, Any], session: Session) -> Optional[Dict[str, Any]]:
    """Updates an existing competency."""
    if not data:
        raise ValueError("Отсутствуют данные для обновления.")

    competency = session.query(Competency).options(
        selectinload(Competency.educational_programs_assoc)
    ).get(comp_id)
    if not competency:
        return None

    allowed_fields = {'name', 'description'}
    for field, value in data.items():
        if field in allowed_fields:
            setattr(competency, field, str(value).strip() if value else None)

    if 'educational_program_ids' in data:
        new_ep_ids = set(data['educational_program_ids'])
        current_ep_ids = {assoc.educational_program_id for assoc in competency.educational_programs_assoc}

        to_add = new_ep_ids - current_ep_ids
        to_delete = current_ep_ids - new_ep_ids

        if to_delete:
            session.query(CompetencyEducationalProgram).filter(
                CompetencyEducationalProgram.competency_id == comp_id,
                CompetencyEducationalProgram.educational_program_id.in_(to_delete)
            ).delete(synchronize_session=False)

        if to_add:
            for ep_id in to_add:
                session.add(CompetencyEducationalProgram(competency_id=comp_id, educational_program_id=ep_id))

    session.flush()
    session.refresh(competency)
    return competency.to_dict(
        rules=['-indicators', '-fgos', '-based_on_labor_function'],
        include_type=True,
        include_educational_programs=True
    )

@handle_db_errors(default_return=False)
def delete_competency(comp_id: int, session: Session) -> bool:
    """Deletes a competency by its ID."""
    comp_to_delete = session.get(Competency, comp_id)
    if not comp_to_delete:
        logger.warning(f"Competency {comp_id} not found for deletion.")
        return False
    
    session.delete(comp_to_delete)
    logger.info(f"Competency {comp_id} marked for deletion.")
    return True

@handle_db_errors(default_return=[])
def get_all_indicators() -> List[Dict[str, Any]]:
    """Fetches a list of all indicators."""
    indicators = local_db.session.query(Indicator).options(joinedload(Indicator.competency)).all()
    return [
        ind.to_dict(rules=['-labor_functions', '-matrix_entries'], include_competency=True)
        for ind in indicators
    ]

@handle_db_errors()
def get_indicator_details(ind_id: int) -> Optional[Dict[str, Any]]:
    """Fetches detailed information for a single indicator."""
    indicator = local_db.session.query(Indicator).options(joinedload(Indicator.competency)).get(ind_id)
    if not indicator:
        logger.warning(f"Indicator with id {ind_id} not found.")
        return None
    return indicator.to_dict(rules=['-competency', '-labor_functions', '-matrix_entries'], include_competency=True)

@handle_db_errors()
def create_indicator(data: Dict[str, Any], session: Session) -> Indicator:
    """Creates a new indicator."""
    required_fields = ['competency_id', 'code', 'formulation']
    if not all(data.get(field) for field in required_fields):
        raise ValueError(f"Отсутствуют обязательные поля: {', '.join(required_fields)}.")

    indicator = Indicator(
        competency_id=data['competency_id'],
        code=str(data['code']).strip(),
        formulation=str(data['formulation']).strip(),
        source=str(data.get('source', '')).strip() or None,
        selected_ps_elements_ids=data.get('selected_ps_elements_ids', {})
    )
    session.add(indicator)
    session.flush()
    return indicator

@handle_db_errors()
def update_indicator(ind_id: int, data: Dict[str, Any], session: Session) -> Optional[Indicator]:
    """Updates an existing indicator."""
    if not data:
        raise ValueError("Отсутствуют данные для обновления.")

    indicator = session.get(Indicator, ind_id)
    if not indicator:
        return None

    allowed_fields = {'code', 'formulation', 'source', 'selected_ps_elements_ids'}
    for field, value in data.items():
        if field in allowed_fields:
            processed_value = value
            if isinstance(value, str):
                processed_value = value.strip()
            if field == 'source' and not processed_value:
                processed_value = None
            
            setattr(indicator, field, processed_value)

    session.flush()
    session.refresh(indicator)
    return indicator

@handle_db_errors(default_return=False)
def delete_indicator(ind_id: int, session: Session) -> bool:
    """Deletes an indicator by its ID."""
    ind_to_delete = session.get(Indicator, ind_id)
    if not ind_to_delete:
        logger.warning(f"Indicator {ind_id} not found for deletion.")
        return False
    
    session.delete(ind_to_delete)
    logger.info(f"Indicator {ind_id} marked for deletion.")
    return True