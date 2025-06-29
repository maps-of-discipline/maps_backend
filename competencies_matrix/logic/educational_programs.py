import datetime
import logging
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session, selectinload

from maps.models import db as local_db
from maps.models import (
    AupInfo as LocalAupInfo, AupData as LocalAupData,
    SprFaculty, Department, SprDegreeEducation, SprFormEducation
)

from ..models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    FgosVo, EducationalProgramAup, EducationalProgramPs,
    CompetencyEducationalProgram
)

# НОВЫЙ ИМПОРТ: Теперь импорт AUP вынесен в aup_external.py
from .aup_external import get_external_aups_list, import_aup_from_external_db 

from ..utils import find_or_create_lookup, find_or_create_name_op

logger = logging.getLogger(__name__)

def get_educational_programs_list() -> List[EducationalProgram]:
    """Fetches list of all educational programs."""
    try:
        return local_db.session.query(EducationalProgram).options(selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup)).order_by(EducationalProgram.title).all()
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching programs list: {e}")
        return []

def get_program_details(program_id: int) -> Optional[Dict[str, Any]]:
    """Fetches detailed information about an educational program."""
    try:
        program = local_db.session.query(EducationalProgram).options(
            selectinload(EducationalProgram.fgos),
            selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
            selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard),
            selectinload(EducationalProgram.competencies_assoc).selectinload(CompetencyEducationalProgram.competency).selectinload(Competency.competency_type)
        ).get(program_id)

        if not program:
            logger.warning(f"Program with id {program_id} not found.")
            return None
        
        details = program.to_dict(
            include_fgos=True, include_aup_list=True, include_selected_ps_list=True,
            include_recommended_ps_list=True, include_competencies_list=True
        )
        return details

    except AttributeError as ae:
        logger.error(f"AttributeError for program_id {program_id}: {ae}", exc_info=True)
        return None
    except SQLAlchemyError as e:
        logger.error(f"Database error for program_id {program_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error for program_id {program_id}: {e}", exc_info=True)
        return None

def create_educational_program(
    data: Dict[str, Any], session: Session
) -> EducationalProgram:
    """
    (ИСПРАВЛЕНО v4)
    Создает ОПОП. БЛОК АВТОМАТИЧЕСКОГО СОЗДАНИЯ ПУСТЫХ СВЯЗЕЙ УДАЛЕН.
    """
    required_fields = ['title', 'code', 'enrollment_year', 'form_of_education']
    if not all(data.get(field) for field in required_fields):
        raise ValueError(f"Обязательные поля не заполнены: {', '.join(required_fields)}.")

    existing_program = session.query(EducationalProgram).filter_by(
        code=data['code'], profile=data.get('profile'),
        enrollment_year=data.get('enrollment_year'), form_of_education=data.get('form_of_education')
    ).first()
    if existing_program:
        raise IntegrityError(f"Образовательная программа с такими параметрами уже существует (ID: {existing_program.id}).", {}, None)

    fgos_vo = session.query(FgosVo).get(data['fgos_id']) if data.get('fgos_id') else None

    new_program = EducationalProgram(
        title=data['title'], code=data['code'], profile=data.get('profile'),
        qualification=data.get('qualification'), form_of_education=data.get('form_of_education'),
        enrollment_year=data.get('enrollment_year'), fgos=fgos_vo
    )
    session.add(new_program)
    session.flush()

    aup_info = None
    if data.get('num_aup'):
        aup_num_to_link = data['num_aup']
        aup_info = session.query(LocalAupInfo).filter_by(num_aup=aup_num_to_link).first()

        if not aup_info:
            logger.warning(f"АУП '{aup_num_to_link}' не найден локально. Попытка импорта...")
            try:
                import_result = import_aup_from_external_db(aup_num_to_link, new_program.id, session)
                if import_result.get("aup_id"):
                    aup_info = session.query(LocalAupInfo).get(import_result.get("aup_id"))
                else:
                    raise RuntimeError("Импорт АУП не вернул ID, не удалось продолжить.")
            except Exception as e_import:
                logger.error(f"Исключение при импорте АУП '{aup_num_to_link}' во время создания ОП: {e_import}", exc_info=True)
                raise RuntimeError(f"Не удалось импортировать связанный АУП '{aup_num_to_link}'. Создание ОП прервано.")

    if aup_info:
        logger.info(f"АУП (ID: {aup_info.id_aup}) успешно связан с новой ОП (ID: {new_program.id}).")

    # # =========================================================================
    # # ======================== ГЛАВНОЕ ИСПРАВЛЕНИЕ ========================
    # # =========================================================================
    # # БЛОК АВТОМАТИЧЕСКОГО СОЗДАНИЯ ПУСТЫХ СВЯЗЕЙ В МАТРИЦЕ ПОЛНОСТЬЮ УДАЛЕН.
    # # Матрица будет создаваться пустой, связи будут добавляться только по действию пользователя.
    # logger.info("Пропуск автоматического создания пустой матрицы. Связи будут создаваться по требованию.")
    # # =========================================================================
    
    session.refresh(new_program)
    return new_program

def delete_educational_program(program_id: int, delete_cloned_aups: bool, session: Session) -> bool:
    """
    Удаляет образовательную программу и, опционально, связанные с ней
    ЛОКАЛЬНЫЕ клонированные АУПы.
    """
    try:
        program_to_delete = session.query(EducationalProgram).options(
            selectinload(EducationalProgram.aup_assoc)
        ).get(program_id)

        if not program_to_delete:
            logger.warning(f"Educational Program with id {program_id} not found for deletion.")
            return False

        if delete_cloned_aups:
            # Находим все АУПы, связанные с этой программой
            aup_ids_to_delete = [assoc.aup_id for assoc in program_to_delete.aup_assoc]
            if aup_ids_to_delete:
                logger.info(f"Cascading delete for program {program_id}: Deleting associated local AUPs with IDs: {aup_ids_to_delete}")
                # Удаляем сами записи АУП, каскадное удаление (в maps.models) должно удалить aup_data и др.
                session.query(LocalAupInfo).filter(LocalAupInfo.id_aup.in_(aup_ids_to_delete)).delete(synchronize_session=False)

        # Удаляем саму программу. Связи в EducationalProgramAup, EducationalProgramPs, CompetencyEducationalProgram
        # удалятся каскадно, если настроено в моделях.
        session.delete(program_to_delete)
        logger.info(f"Successfully marked Educational Program ID {program_id} for deletion.")
        return True

    except SQLAlchemyError as e:
        logger.error(f"Database error deleting Educational Program {program_id}: {e}", exc_info=True)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error deleting Educational Program {program_id}: {e}", exc_info=True)
        raise e
