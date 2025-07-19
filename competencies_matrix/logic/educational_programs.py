# filepath: competencies_matrix/logic/educational_programs.py
import datetime
import logging
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session, selectinload, joinedload

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
                # В случае, если AUP не найден локально, но есть в внешней БД, импортируем его.
                # Это вызывает import_aup_from_external_db, который создает LocalAupInfo и связывает с new_program
                # Если aup_info не будет найдено, то new_program останется без primary_aup_num, но это нормально.
                import_result = import_aup_from_external_db(aup_num_to_link, new_program.id, session)
                if import_result.get("aup_id"):
                    aup_info = session.query(LocalAupInfo).get(import_result.get("aup_id"))
                else:
                    raise RuntimeError("Импорт АУП не вернул ID, не удалось продолжить.")
            except Exception as e_import:
                logger.error(f"Исключение при импорте АУП '{aup_num_to_link}' во время создания ОП: {e_import}", exc_info=True)
                raise RuntimeError(f"Не удалось импортировать связанный АУП '{aup_num_to_link}'. Создание ОП прервано.")
    
    if aup_info: # Если AUP найден или успешно импортирован, устанавливаем его как основной.
        # Удаляем старые primary связи для этой ОП, если они есть.
        session.query(EducationalProgramAup).filter_by(
            educational_program_id=new_program.id, is_primary=True
        ).update({"is_primary": False})
        
        # Создаем или обновляем связь, чтобы она была основной
        existing_link = session.query(EducationalProgramAup).filter_by(
            educational_program_id=new_program.id, aup_id=aup_info.id_aup
        ).first()
        
        if existing_link:
            existing_link.is_primary = True
            session.add(existing_link)
        else:
            new_link = EducationalProgramAup(
                educational_program_id=new_program.id, aup_id=aup_info.id_aup, is_primary=True
            )
            session.add(new_link)
        
        logger.info(f"АУП (ID: {aup_info.id_aup}) успешно связан как основной с новой ОП (ID: {new_program.id}).")
    else:
        logger.info(f"ОП (ID: {new_program.id}) создана без основного АУП.")

    session.refresh(new_program)
    return new_program

# НОВАЯ ФУНКЦИЯ ДЛЯ ОБНОВЛЕНИЯ ОПОП
def update_educational_program(program_id: int, data: Dict[str, Any], session: Session) -> Optional[EducationalProgram]:
    """
    Обновляет существующую образовательную программу.
    Позволяет изменять основные поля, привязывать/отвязывать ФГОС и основной АУП.
    """
    program = session.query(EducationalProgram).options(
        selectinload(EducationalProgram.aup_assoc)
    ).get(program_id)

    if not program:
        logger.warning(f"Educational Program with ID {program_id} not found for update.")
        return None

    logger.info(f"Updating Educational Program ID {program_id} with data: {data}")

    # Разрешенные поля для прямого обновления
    allowed_fields = ['title', 'code', 'profile', 'qualification', 'form_of_education', 'enrollment_year']
    updated = False

    for field in allowed_fields:
        if field in data and getattr(program, field) != data[field]:
            setattr(program, field, data[field])
            updated = True

    # Обновление ФГОС
    if 'fgos_id' in data:
        new_fgos_id = data['fgos_id']
        if program.fgos_vo_id != new_fgos_id:
            fgos_vo = None
            if new_fgos_id:
                fgos_vo = session.query(FgosVo).get(new_fgos_id)
                if not fgos_vo:
                    raise ValueError(f"ФГОС ВО с ID {new_fgos_id} не найден.")
            program.fgos = fgos_vo
            updated = True
            logger.info(f"Updated FGOS for program {program_id} to ID {new_fgos_id}.")

    # Обновление основного АУП
    if 'num_aup' in data:
        new_num_aup = data['num_aup']
        current_primary_aup_num = next((assoc.aup.num_aup for assoc in program.aup_assoc if assoc.is_primary and assoc.aup), None)
        
        if current_primary_aup_num != new_num_aup:
            logger.info(f"Changing primary AUP for program {program_id} from '{current_primary_aup_num}' to '{new_num_aup}'.")
            
            # Удаляем старые primary связи для этой ОП
            session.query(EducationalProgramAup).filter_by(
                educational_program_id=program.id, is_primary=True
            ).update({"is_primary": False})
            
            if new_num_aup:
                aup_info = session.query(LocalAupInfo).filter_by(num_aup=new_num_aup).first()
                if not aup_info:
                    # Если AUP не найден локально, пытаемся импортировать.
                    logger.warning(f"АУП '{new_num_aup}' не найден локально. Попытка импорта при обновлении ОП.")
                    try:
                        import_result = import_aup_from_external_db(new_num_aup, program.id, session)
                        if import_result.get("aup_id"):
                            aup_info = session.query(LocalAupInfo).get(import_result.get("aup_id"))
                        else:
                            raise RuntimeError(f"Импорт АУП '{new_num_aup}' не вернул ID, не удалось связать.")
                    except Exception as e_import:
                        logger.error(f"Исключение при импорте АУП '{new_num_aup}' во время обновления ОП: {e_import}", exc_info=True)
                        raise ValueError(f"Не удалось импортировать связанный АУП '{new_num_aup}'. Обновление ОП прервано.")

                # Создаем или обновляем связь, чтобы она была основной
                existing_link = session.query(EducationalProgramAup).filter_by(
                    educational_program_id=program.id, aup_id=aup_info.id_aup
                ).first()
                
                if existing_link:
                    existing_link.is_primary = True
                    session.add(existing_link)
                else:
                    new_link = EducationalProgramAup(
                        educational_program_id=program.id, aup_id=aup_info.id_aup, is_primary=True
                    )
                    session.add(new_link)
                updated = True
                logger.info(f"АУП '{new_num_aup}' связан как основной с ОП ID {program_id}.")
            else: # new_num_aup is None, meaning primary AUP is being removed
                updated = True
                logger.info(f"Основной АУП для ОП ID {program_id} был удален.")
            
    if updated:
        session.add(program)
        session.flush() # Flush to apply changes before refresh

    session.refresh(program)
    # Перезагружаем связи для корректного to_dict
    session.expire(program, ['aup_assoc', 'fgos']) 
    program = session.query(EducationalProgram).options(
        selectinload(EducationalProgram.fgos),
        selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
    ).get(program_id)

    return program.to_dict(include_aup_list=True, include_fgos=True)


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