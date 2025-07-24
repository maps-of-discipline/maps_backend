# filepath: competencies_matrix/logic/matrix_operations.py

import logging
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy import exists, exc
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session, selectinload, joinedload

from maps.models import db as local_db
from maps.models import AupInfo as LocalAupInfo, AupData as LocalAupData, D_Period, SprDiscipline

# Импорты моделей модуля Компетенций
from ..models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    FgosVo, EducationalProgramAup, CompetencyType,
    LaborFunction, GeneralizedLaborFunction, ProfStandard,
    CompetencyEducationalProgram
)

logger = logging.getLogger(__name__)

def get_matrix_for_aup(aup_num: str) -> Dict[str, Any]:
    """
    Собирает данные для матрицы компетенций.
    Возвращает только дисциплины и связи. Компетенции загружаются отдельно через get_program_details.
    """
    logger.info(f"Запрос на построение матрицы для АУП: {aup_num}.")
    session: Session = local_db.session

    response_data: Dict[str, Any] = {
        "status": "error",
        "error": "Неизвестная ошибка при загрузке матрицы.",
        "disciplines": [],
        "competencies": [], # Это поле больше не заполняется здесь. Оно будет пустым.
        "links": [],
        "aup_info": None,
        "program_info": None,
    }
    
    local_aup = session.query(LocalAupInfo).filter_by(num_aup=aup_num).first()

    if not local_aup:
        response_data["status"] = "not_imported"
        response_data["error"] = f"АУП '{aup_num}' не импортирован в систему. Пожалуйста, импортируйте его."
        logger.warning(f"Matrix data requested for non-imported AUP: {aup_num}")
        return response_data
    
    program_assoc = session.query(EducationalProgramAup).filter_by(aup_id=local_aup.id_aup).first()
    if not program_assoc:
        response_data["error"] = f"АУП '{aup_num}' существует, но не привязан к образовательной программе."
        logger.warning(f"Matrix data requested for AUP {aup_num} which is not linked to any program.")
        return response_data
    program = program_assoc.educational_program

    local_disciplines_results = session.query(LocalAupData, D_Period.title.label("period_title")).join(
        D_Period, LocalAupData.id_period == D_Period.id
    ).options(
        joinedload(LocalAupData.discipline)
    ).filter(LocalAupData.id_aup == local_aup.id_aup).order_by(LocalAupData.id_period, LocalAupData.shifr).all()
    
    disciplines_data = [{
        'aup_data_id': entry.id,
        'id_aup': entry.id_aup,
        'shifr': entry.shifr,
        'title': entry.discipline.title if entry.discipline else entry._discipline,
        'semester': entry.id_period,
        'period_title': period_title
    } for entry, period_title in local_disciplines_results]
    
    response_data["disciplines"] = disciplines_data
    local_aup_data_ids = [d['aup_data_id'] for d in disciplines_data]

    links_db = session.query(CompetencyMatrix).filter(
        CompetencyMatrix.aup_data_id.in_(local_aup_data_ids)
    ).all()
    links_data = [{'aup_data_id': link.aup_data_id, 'indicator_id': link.indicator_id, 'is_manual': link.is_manual} for link in links_db]
    
    response_data["links"] = links_data

    response_data["status"] = "ok"
    response_data["aup_info"] = local_aup.as_dict()
    response_data["program_info"] = program.to_dict(rules=['-aup_assoc', '-competencies_assoc', '-selected_ps_assoc'])
    response_data.pop("error")

    logger.debug(f"Successfully prepared matrix data for AUP {aup_num}.")
    return response_data

def update_matrix_link(aup_data_id: int, indicator_id: int, create: bool = True) -> Dict[str, Any]:
    """
    Creates or deletes a link entry in the CompetencyMatrix table.
    """
    session: Session = local_db.session
    try:
        if not session.query(exists().where(LocalAupData.id == aup_data_id)).scalar():
            raise ValueError(f"Дисциплина с ID {aup_data_id} не найдена в локальной БД.")

        if not session.query(exists().where(Indicator.id == indicator_id)).scalar():
            raise ValueError(f"Индикатор с ID {indicator_id} не найден в локальной БД.")

        existing_link = session.query(CompetencyMatrix).filter_by(
            aup_data_id=aup_data_id,
            indicator_id=indicator_id
        ).first()

        if create:
            if existing_link:
                logger.warning(f"Попытка создать уже существующую связь: AupData={aup_data_id}, Indicator={indicator_id}")
                return {'success': True, 'status': 'already_exists', 'message': "Связь уже существует."}
            else:
                link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
                session.add(link)
                logger.info(f"Связь создана: AupData ID {aup_data_id} <-> Indicator ID {indicator_id}")
                session.commit()
                return {'success': True, 'status': 'created', 'message': "Связь успешно создана."}
        else:
            if existing_link:
                session.delete(existing_link)
                logger.info(f"Связь удалена: AupData ID {aup_data_id} <-> Indicator ID {indicator_id}")
                session.commit()
                return {'success': True, 'status': 'deleted', 'message': "Связь успешно удалена."}
            else:
                logger.warning(f"Связь для удаления не найдена: AupData ID {aup_data_id} <-> Indicator ID {indicator_id}")
                return {'success': True, 'status': 'not_found', 'message': "Связь не найдена."}

    except ValueError as e:
        session.rollback()
        logger.error(f"Ошибка данных при обновлении матрицы: {e}", exc_info=True)
        raise e
    except IntegrityError as e: # Может возникнуть при конкурентной вставке
        session.rollback()
        logger.error(f"Ошибка целостности при обновлении матрицы: {e}", exc_info=True)
        raise e
    except Exception as e:
        session.rollback()
        logger.error(f"Неожиданная ошибка при обновлении матрицы: {e}", exc_info=True)
        raise e