# filepath: competencies_matrix/logic/educational_programs.py
import logging
from typing import Dict, List, Any, Optional

from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from sqlalchemy.orm import Session, selectinload

from maps.models import db as local_db
from maps.models import AupInfo as LocalAupInfo
from ..external_models import ExternalAupInfo

from ..models import (
    EducationalProgram, Competency, CompetencyMatrix,
    FgosVo, EducationalProgramAup, EducationalProgramPs, CompetencyType,
    CompetencyEducationalProgram
)

from .aup_external import import_aup_from_external_db
from .error_utils import (
    handle_db_errors, ErrorResponse, external_db_session, 
    safe_get_program, handle_aup_import_error
)

logger = logging.getLogger(__name__)


class EducationalProgramError(Exception):
    """Base exception for educational program operations."""
    pass


class EducationalProgramNotFoundError(EducationalProgramError):
    """Raised when an educational program is not found."""
    pass


class AupImportError(EducationalProgramError):
    """Raised when AUP import fails."""
    pass


class FgosNotFoundError(EducationalProgramError):
    """Raised when FGOS is not found."""
    pass

def check_aup_version(program_id: int, session: Session) -> Dict[str, Any]:
    """
    Проверяет актуальность основного АУП для образовательной программы.
    TODO: Сделать правильную проверку версии АУП, используя внешнюю БД.
    """
    program = session.query(EducationalProgram).options(
        selectinload(EducationalProgram.aup_assoc)
        .selectinload(EducationalProgramAup.aup)
    ).get(program_id)

    if not program:
        return ErrorResponse.not_found("Образовательная программа")

    primary_aup_assoc = next((assoc for assoc in program.aup_assoc if assoc.is_primary), None)
    if not primary_aup_assoc or not primary_aup_assoc.aup:
        return {"status": "no_primary_aup", "message": "Для данной ОПОП не назначен основной АУП."}

    local_aup = primary_aup_assoc.aup
    local_import_timestamp = primary_aup_assoc.created_at

    try:
        with external_db_session() as external_session:
            query = external_session.query(ExternalAupInfo).filter(
                ExternalAupInfo.id_spec == local_aup.id_spec,
                ExternalAupInfo.id_form == local_aup.id_form,
                ExternalAupInfo.year_beg == local_aup.year_beg
            )

            if hasattr(ExternalAupInfo, 'last_update'):
                latest_external_aup = query.order_by(ExternalAupInfo.last_update.desc()).first()
                if latest_external_aup and latest_external_aup.last_update and latest_external_aup.last_update > local_import_timestamp:
                    return {
                        "status": "update_available",
                        "message": f"Доступна более новая версия АУП (от {latest_external_aup.last_update.strftime('%d.%m.%Y %H:%M')}).",
                        "local_version_date": local_import_timestamp.isoformat(),
                        "external_version_date": latest_external_aup.last_update.isoformat()
                    }
            else:
                logger.warning("Model 'ExternalAupInfo' does not have 'last_update' attribute. Falling back to 'id_aup'.")
                latest_external_aup = query.order_by(ExternalAupInfo.id_aup.desc()).first()
            
            if not latest_external_aup:
                return {"status": "not_found_externally", "message": "Аналог этого АУП не найден во внешней БД для сравнения."}

            if latest_external_aup.id_aup > local_aup.id_aup:
                return {
                    "status": "update_available",
                    "message": "Доступна более новая версия АУП (определено по ID). Рекомендуется обновить.",
                    "local_version_date": f"ID: {local_aup.id_aup}",
                    "external_version_date": f"ID: {latest_external_aup.id_aup}"
                }
            
            return {"status": "latest", "message": "Используется последняя версия АУП."}

    except OperationalError:
        return ErrorResponse.external_db_connection_error()
    except (IntegrityError, SQLAlchemyError, AttributeError) as e:
        logger.error(f"Database/model error checking AUP version for program {program_id}: {e}")
        return ErrorResponse.internal_error("проверке версии АУП")
    except Exception:
        logger.exception(f"Unexpected error checking AUP version for program {program_id}")
        return ErrorResponse.internal_error("проверке версии АУП")


@handle_db_errors(default_return=[])
def get_educational_programs_list() -> List[EducationalProgram]:
    """Получает список всех образовательных программ."""
    return local_db.session.query(EducationalProgram).options(
        selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup)
    ).order_by(EducationalProgram.title).all()

@handle_db_errors()
def get_program_details(program_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает детальную информацию об образовательной программе,
    активно собирая полный список соответствующих компетенций.
    """
    logger.debug(f"Fetching details for program ID: {program_id}")
    session: Session = local_db.session

    program = session.query(EducationalProgram).options(
        selectinload(EducationalProgram.fgos),
        selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
        selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard),
    ).get(program_id)

    if not program:
        logger.warning(f"Program with id {program_id} not found.")
        return None

    details = program.to_dict(
        include_fgos=True, include_aup_list=True, include_selected_ps_list=True,
        include_recommended_ps_list=True, include_competencies_list=False
    )

    # Load competencies
    relevant_competencies = []
    comp_types_q = session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК', 'ПК'])).all()
    comp_types = {ct.code: ct for ct in comp_types_q}

    # Load УК/ОПК from FGOS
    if program.fgos:
        uk_opk_types = [comp_types.get(code) for code in ['УК', 'ОПК'] if comp_types.get(code)]
        if uk_opk_types:
            uk_opk_competencies = session.query(Competency).options(
                selectinload(Competency.indicators),
                selectinload(Competency.competency_type)
            ).filter(
                Competency.fgos_vo_id == program.fgos.id,
                Competency.competency_type_id.in_([ct.id for ct in uk_opk_types])
            ).all()
            relevant_competencies.extend(uk_opk_competencies)
            logger.debug(f"Loaded {len(uk_opk_competencies)} УК/ОПК competencies from FGOS ID {program.fgos.id}.")

    # Load ПК competencies
    pk_type = comp_types.get('ПК')
    if pk_type:
        pk_competencies = session.query(Competency).join(CompetencyEducationalProgram).options(
            selectinload(Competency.indicators),
            selectinload(Competency.competency_type)
        ).filter(
            Competency.competency_type_id == pk_type.id,
            CompetencyEducationalProgram.educational_program_id == program_id
        ).all()
        relevant_competencies.extend(pk_competencies)
        logger.debug(f"Loaded {len(pk_competencies)} ПК competencies linked to Program ID {program_id}.")
    
    details['competencies_list'] = [
        comp.to_dict(rules=['-indicators'], include_type=True, include_indicators=True)
        for comp in relevant_competencies
    ]
    
    logger.debug(f"Program {program_id} details assembled with {len(details['competencies_list'])} competencies.")
    return details

def create_educational_program(
    data: Dict[str, Any], session: Session
) -> EducationalProgram:
    """
    Создает ОПОП.
    """
    required_fields = ['title', 'code', 'enrollment_year', 'form_of_education']
    if not all(data.get(field) for field in required_fields):
        raise ValueError(f"Обязательные поля не заполнены: {', '.join(required_fields)}.")

    existing_program = session.query(EducationalProgram).filter_by(
        code=data['code'], profile=data.get('profile'),
        enrollment_year=data.get('enrollment_year'), form_of_education=data.get('form_of_education')
    ).first()
    if existing_program:
        raise IntegrityError(f"Образовательная программа с такими параметрами (код, профиль, год, форма) уже существует (ID: {existing_program.id}).", {}, None)

    fgos_vo = session.query(FgosVo).get(data['fgos_id']) if data.get('fgos_id') else None

    new_program = EducationalProgram(
        title=data['title'], code=data['code'], profile=data.get('profile'),
        qualification=data.get('qualification'), form_of_education=data.get('form_of_education'),
        enrollment_year=data.get('enrollment_year'), fgos=fgos_vo
    )
    session.add(new_program)
    session.flush()

    # Handle AUP linking
    if data.get('num_aup'):
        _link_aup_to_program(session, new_program.id, data['num_aup'], is_creation=True)

    session.refresh(new_program)
    return new_program


def _link_aup_to_program(session: Session, program_id: int, aup_num: str, is_creation: bool = False):
    """Helper function to link AUP to program with proper error handling."""
    aup_info = session.query(LocalAupInfo).filter_by(num_aup=aup_num).first()

    if not aup_info:
        logger.warning(f"АУП '{aup_num}' не найден локально. Попытка импорта...")
        
        @handle_aup_import_error("импорта", aup_num)
        def import_aup():
            import_result = import_aup_from_external_db(aup_num, program_id, session)
            if not import_result.get("aup_id"):
                raise RuntimeError("Импорт АУП не вернул ID")
            return import_result.get("aup_id")
        
        aup_id = import_aup()
        aup_info = session.query(LocalAupInfo).get(aup_id)

    # Set as primary AUP
    session.query(EducationalProgramAup).filter_by(
        educational_program_id=program_id, is_primary=True
    ).update({"is_primary": False})
    
    existing_link = session.query(EducationalProgramAup).filter_by(
        educational_program_id=program_id, aup_id=aup_info.id_aup
    ).first()
    
    if existing_link:
        existing_link.is_primary = True
        session.add(existing_link)
    else:
        new_link = EducationalProgramAup(
            educational_program_id=program_id, aup_id=aup_info.id_aup, is_primary=True
        )
        session.add(new_link)
    
    operation = "создании" if is_creation else "обновлении"
    logger.info(f"АУП (ID: {aup_info.id_aup}) успешно связан как основной с ОП (ID: {program_id}) при {operation}.")

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
        raise EducationalProgramNotFoundError(f"Educational Program with ID {program_id} not found")

    logger.info(f"Updating Educational Program ID {program_id} with data: {data}")

    allowed_fields = ['title', 'code', 'profile', 'qualification', 'form_of_education', 'enrollment_year']
    updated = False

    for field in allowed_fields:
        if field in data and getattr(program, field) != data[field]:
            setattr(program, field, data[field])
            updated = True

    if 'fgos_id' in data:
        new_fgos_id = data['fgos_id']
        if program.fgos_vo_id != new_fgos_id:
            fgos_vo = None
            if new_fgos_id:
                fgos_vo = session.query(FgosVo).get(new_fgos_id)
                if not fgos_vo:
                    raise FgosNotFoundError(f"ФГОС ВО с ID {new_fgos_id} не найден.")
            program.fgos = fgos_vo
            updated = True
            logger.info(f"Updated FGOS for program {program_id} to ID {new_fgos_id}.")

    if 'num_aup' in data:
        new_num_aup = data['num_aup']
        current_primary_aup_num = next((assoc.aup.num_aup for assoc in program.aup_assoc if assoc.is_primary and assoc.aup), None)
        
        if current_primary_aup_num != new_num_aup:
            logger.info(f"Changing primary AUP for program {program_id} from '{current_primary_aup_num}' to '{new_num_aup}'.")
            
            # Remove current primary AUP
            session.query(EducationalProgramAup).filter_by(
                educational_program_id=program.id, is_primary=True
            ).update({"is_primary": False})
            
            if new_num_aup:
                _link_aup_to_program(session, program.id, new_num_aup, is_creation=False)
            
            updated = True
            
    if updated:
        session.add(program)
        session.flush()

    session.refresh(program)
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
    program_to_delete = session.query(EducationalProgram).options(
        selectinload(EducationalProgram.aup_assoc)
    ).get(program_id)

    if not program_to_delete:
        logger.warning(f"Educational Program with id {program_id} not found for deletion.")
        raise EducationalProgramNotFoundError(f"Educational Program with ID {program_id} not found")

    if delete_cloned_aups:
        aup_ids_to_delete = [assoc.aup_id for assoc in program_to_delete.aup_assoc]
        if aup_ids_to_delete:
            logger.info(f"Cascading delete for program {program_id}: Deleting associated local AUPs with IDs: {aup_ids_to_delete}")
            session.query(LocalAupInfo).filter(LocalAupInfo.id_aup.in_(aup_ids_to_delete)).delete(synchronize_session=False)

    session.delete(program_to_delete)
    logger.info(f"Successfully marked Educational Program ID {program_id} for deletion.")
    return True