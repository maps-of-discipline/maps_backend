# filepath: competencies_matrix/logic/matrix_operations.py
import logging
from typing import Dict, Any

from sqlalchemy.orm import Session, joinedload

from maps.models import db as local_db
from maps.models import AupInfo as LocalAupInfo, AupData as LocalAupData, D_Period

from ..models import EducationalProgramAup, Indicator, CompetencyMatrix
from .educational_programs import get_program_details
from .error_utils import handle_db_errors

logger = logging.getLogger(__name__)

@handle_db_errors()
def get_matrix_for_aup(aup_num: str) -> Dict[str, Any]:
    """Собирает данные для матрицы компетенций из локальных данных."""
    logger.info(f"Строится матрица АУП: {aup_num}.")
    session: Session = local_db.session

    local_aup = session.query(LocalAupInfo).filter_by(num_aup=aup_num).first()
    if not local_aup:
        return {"status": "not_imported", "error": f"АУП '{aup_num}' не импортирован в систему."}
    
    program_assoc = session.query(EducationalProgramAup).filter_by(aup_id=local_aup.id_aup).first()
    if not program_assoc:
        return {"status": "error", "error": f"АУП '{aup_num}' существует, но не привязан к ОПОП."}
    program = program_assoc.educational_program

    program_details = get_program_details(program.id)
    if not program_details:
        return {"status": "error", "error": f"Не удалось получить детали ОПОП с ID {program.id}."}

    disciplines_q = session.query(LocalAupData, D_Period.title.label("period_title")).join(
        D_Period, LocalAupData.id_period == D_Period.id
    ).options(
        joinedload(LocalAupData.discipline)
    ).filter(LocalAupData.id_aup == local_aup.id_aup).order_by(LocalAupData.id_period, LocalAupData.shifr).all()
    
    disciplines = [{
        'aup_data_id': entry.id,
        'title': entry.discipline.title if entry.discipline else entry._discipline,
        'semester': entry.id_period, 'period_title': period_title
    } for entry, period_title in disciplines_q]
    
    aup_data_ids = [d['aup_data_id'] for d in disciplines]
    links = session.query(CompetencyMatrix).filter(
        CompetencyMatrix.aup_data_id.in_(aup_data_ids)
    ).all()
    
    return {
        "status": "ok",
        "disciplines": disciplines,
        "links": [{'aup_data_id': l.aup_data_id, 'indicator_id': l.indicator_id, 'is_manual': l.is_manual} for l in links],
        "aup_info": local_aup.as_dict(),
        "program_info": program.to_dict(rules=['-aup_assoc', '-competencies_assoc', '-selected_ps_assoc']),
        "competencies_list": program_details.get("competencies_list", [])
    }

@handle_db_errors()
def update_matrix_link(aup_data_id: int, indicator_id: int, create: bool = True) -> Dict[str, Any]:
    """Создает или удаляет связь 'Дисциплина-Индикатор'."""
    session: Session = local_db.session

    if not session.get(LocalAupData, aup_data_id):
        raise ValueError(f"Дисциплина с ID {aup_data_id} не найдена в локальной БД.")

    if not session.get(Indicator, indicator_id):
        raise ValueError(f"Индикатор с ID {indicator_id} не найден в локальной БД.")

    existing_link = session.query(CompetencyMatrix).filter_by(
        aup_data_id=aup_data_id, indicator_id=indicator_id
    ).first()

    if create:
        if existing_link:
            return {'status': 'already_exists', 'message': "Связь уже существует."}
        link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
        session.add(link)
        session.commit()
        return {'status': 'created', 'message': "Связь успешно создана."}
    else:
        if existing_link:
            session.delete(existing_link)
            session.commit()
            return {'status': 'deleted', 'message': "Связь успешно удалена."}
        else:
            return {'status': 'not_found', 'message': "Связь не найдена."}