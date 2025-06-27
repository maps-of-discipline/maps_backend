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

from .aup_external import get_external_aups_list, _clone_external_aup_to_local
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
    Создает ОПОП. Если АУП не найден локально, клонирует его из внешней БД.
    Затем создает пустую матрицу.
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

    fgos_vo = None
    if data.get('fgos_id'):
        fgos_vo = session.query(FgosVo).get(data['fgos_id'])
        if not fgos_vo:
            logger.warning(f"FGOS с ID {data['fgos_id']} не найден.")

    new_program = EducationalProgram(
        title=data['title'], code=data['code'], profile=data.get('profile'),
        qualification=data.get('qualification'), form_of_education=data.get('form_of_education'),
        enrollment_year=data.get('enrollment_year'), fgos=fgos_vo
    )
    session.add(new_program)
    session.flush()

    aup_info = None
    if data.get('num_aup'):
        # --- НОВЫЙ БЛОК ЛОГИКИ С КЛОНИРОВАНИЕМ ---
        aup_num_to_link = data['num_aup']
        # 1. Ищем АУП в локальной БД
        aup_info = session.query(LocalAupInfo).filter_by(num_aup=aup_num_to_link).first()

        if not aup_info:
            logger.warning(f"АУП с номером '{aup_num_to_link}' не найден в локальной БД. Попытка клонирования из внешней БД...")
            # 2. Если не нашли локально, ищем во внешней и клонируем
            external_aups_list = get_external_aups_list(search_query=aup_num_to_link, limit=1)
            if external_aups_list.get('items'):
                external_aup_data = external_aups_list['items'][0]
                aup_info = _clone_external_aup_to_local(external_aup_data, session)
            else:
                logger.error(f"АУП {aup_num_to_link} не найден и во внешней БД. Невозможно создать связь.")
        # --- КОНЕЦ НОВОГО БЛОКА ---

        if aup_info:
            has_primary_aup = session.query(EducationalProgramAup).filter_by(educational_program_id=new_program.id, is_primary=True).count() > 0
            link = EducationalProgramAup(educational_program_id=new_program.id, aup_id=aup_info.id_aup, is_primary=(not has_primary_aup))
            session.add(link)
            logger.info(f"Связь ОПОП (ID: {new_program.id}) с АУП (ID: {aup_info.id_aup}) создана.")
        else:
            logger.error(f"Не удалось ни найти, ни склонировать АУП {data.get('num_aup')}. Связь с ОПОП не создана.")


    # --- Блок создания пустой матрицы (остается без изменений) ---
    if aup_info and fgos_vo:
        # ... (код создания пустой матрицы)
        # ... (он теперь будет работать, так как aup_info - это локальный объект)
        logger.info(f"Начинаем автоматическое создание пустой матрицы для АУП {aup_info.num_aup}")
        try:
            # 1. Получаем все дисциплины (aup_data_id) для данного АУП
            discipline_entries = session.query(LocalAupData.id).filter_by(id_aup=aup_info.id_aup).all()
            aup_data_ids = {entry.id for entry in discipline_entries}

            # 2. Получаем все индикаторы, релевантные для этой ОП
            # УК/ОПК из связанного ФГОС + ПК из самой ОП
            relevant_competency_ids = session.query(Competency.id).filter(
                (Competency.fgos_vo_id == fgos_vo.id) | # УК и ОПК
                (Competency.educational_programs_assoc.any(educational_program_id=new_program.id)) # ПК
            ).subquery()
            
            relevant_indicator_ids = {
                indicator.id for indicator in session.query(Indicator.id).filter(Indicator.competency_id.in_(relevant_competency_ids)).all()
            }

            if not aup_data_ids or not relevant_indicator_ids:
                logger.warning("Не найдены дисциплины или индикаторы для создания матрицы. Пропускаем.")
            else:
                # 3. Создаем "пустые" связи для каждой дисциплины и каждого индикатора
                matrix_links_to_create = []
                for aup_data_id in aup_data_ids:
                    for indicator_id in relevant_indicator_ids:
                        matrix_links_to_create.append(
                            CompetencyMatrix(
                                aup_data_id=aup_data_id,
                                indicator_id=indicator_id,
                                is_manual=False, # По умолчанию связь не ручная
                                relevance_score=None
                            )
                        )
                
                if matrix_links_to_create:
                    session.bulk_save_objects(matrix_links_to_create)
                    logger.info(f"Успешно создано {len(matrix_links_to_create)} пустых связей для матрицы АУП {aup_info.num_aup}")

        except Exception as e:
            logger.error(f"Ошибка при автоматическом создании матрицы для АУП {aup_info.num_aup}: {e}", exc_info=True)
            # Не прерываем основной процесс создания ОПОП из-за ошибки в создании матрицы
            # Можно добавить логику для отката только этой части, если нужно

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