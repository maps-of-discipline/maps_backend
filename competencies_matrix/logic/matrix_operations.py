# filepath: competencies_matrix/logic/matrix_operations.py

import logging
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy import exists, exc
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session, selectinload, joinedload

from maps.models import db as local_db
from maps.models import AupInfo as LocalAupInfo, AupData as LocalAupData, D_Period, SprDiscipline

# --- Импорты моделей модуля Компетенций ---
from ..models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    FgosVo, EducationalProgramAup, CompetencyType,
    LaborFunction, GeneralizedLaborFunction, ProfStandard,
    CompetencyEducationalProgram
)

logger = logging.getLogger(__name__)

def get_matrix_for_aup(aup_num: str) -> Dict[str, Any]:
    """
    Collects all data for the competency matrix.
    """
    logger.info(f"Запрос на построение матрицы для АУП: {aup_num}.")
    session: Session = local_db.session

    # Инициализируем структуру ответа по умолчанию
    response_data: Dict[str, Any] = {
        "status": "error",
        "aup_info": None,
        "program_info": None,
        "disciplines": [],
        "competencies": [],
        "links": [],
        "error": f"АУП '{aup_num}' не найден в системе или не привязан к ОП."
    }
    
    # 1. Ищем АУП в локальной БД
    local_aup = session.query(LocalAupInfo).options(
        selectinload(LocalAupInfo.educational_program_links)
            .selectinload(EducationalProgramAup.educational_program)
            .selectinload(EducationalProgram.fgos)
    ).filter_by(num_aup=aup_num).first()

    if not local_aup:
        response_data["status"] = "not_imported"
        response_data["error"] = f"АУП '{aup_num}' не импортирован в систему. Пожалуйста, импортируйте его."
        return response_data

    # 2. Находим связанную образовательную программу
    program = next((assoc.educational_program for assoc in local_aup.educational_program_links if assoc.is_primary), 
                   local_aup.educational_program_links[0].educational_program if local_aup.educational_program_links else None)
    
    if not program:
        # АУП есть, но не связан. Это ошибка конфигурации.
        response_data["error"] = f"АУП '{aup_num}' существует, но не привязан к образовательной программе."
        return response_data

    # 3. Загружаем ЛОКАЛЬНЫЕ дисциплины для этого АУП
    local_disciplines_results = session.query(LocalAupData, D_Period.title.label("period_title")).join(
        D_Period, LocalAupData.id_period == D_Period.id
    ).options(
        joinedload(LocalAupData.discipline), joinedload(LocalAupData.block), joinedload(LocalAupData.part),
        joinedload(LocalAupData.module), joinedload(LocalAupData.group), joinedload(LocalAupData.type_record),
        joinedload(LocalAupData.type_control), joinedload(LocalAupData.ed_izmereniya)
    ).filter(LocalAupData.id_aup == local_aup.id_aup).order_by(LocalAupData.id_period, LocalAupData.shifr).all()
    
    # 4. Формируем список дисциплин
    disciplines_data = []
    for entry, period_title in local_disciplines_results:
        disciplines_data.append({
            'id': entry.id, 'aup_data_id': entry.id, 'id_aup': entry.id_aup, 'shifr': entry.shifr,
            'id_discipline': entry.id_discipline, 'title': entry.discipline.title if entry.discipline else entry._discipline,
            'semester': entry.id_period, 'period_title': period_title, 'num_row': entry.num_row,
            'zet': (entry.zet / 100) if entry.zet is not None else 0, 'amount': entry.amount,
            'id_type_control': entry.id_type_control, 'type_control_title': entry.type_control.title if entry.type_control else None,
            'id_edizm': entry.id_edizm, 'ed_izmereniya_title': entry.ed_izmereniya.title if entry.ed_izmereniya else None,
            'id_block': entry.id_block, 'block_title': entry.block.title if entry.block else None,
            'id_part': entry.id_part, 'part_title': entry.part.title if entry.part else None,
            'id_module': entry.id_module, 'module_title': entry.module.title if entry.module else None, 'module_color': entry.module.color if entry.module else None,
            'id_group': entry.id_group, 'group_name': entry.group.name_group if entry.group else None, 'group_color': entry.group.color if entry.group else None,
        })
    
    if not disciplines_data:
        logger.warning(f"Для локального АУП ID {local_aup.id_aup} не найдено дисциплин.")
        
    response_data["disciplines"] = disciplines_data
    local_aup_data_ids = [d['id'] for d in disciplines_data]

    # 5. Получаем релевантные компетенции и индикаторы
    competencies_data, all_indicator_ids = _get_relevant_competencies_for_program(session, program)
    response_data["competencies"] = competencies_data

    # 6. Получаем существующие связи в матрице
    links_data = []
    if local_aup_data_ids and all_indicator_ids:
        links_db = session.query(CompetencyMatrix).filter(
            CompetencyMatrix.aup_data_id.in_(local_aup_data_ids),
            CompetencyMatrix.indicator_id.in_(list(all_indicator_ids))
        ).all()
        links_data = [{'aup_data_id': link.aup_data_id, 'indicator_id': link.indicator_id, 'is_manual': link.is_manual} for link in links_db]
    response_data["links"] = links_data

    # 7. Финализируем успешный ответ
    response_data["status"] = "ok"
    response_data["aup_info"] = local_aup.as_dict()
    response_data["program_info"] = program.to_dict(rules=['-aup_assoc'])
    response_data.pop("error") # Убираем ключ ошибки при успехе

    return response_data

def _get_relevant_competencies_for_program(session: Session, program: EducationalProgram) -> Tuple[List[Dict], set]:
    """
    Helper function to retrieve all relevant competencies (UK, OPK, PK)
    and their indicators for a given educational program.
    """
    relevant_competencies = []
    
    # 1. Загрузка УК и ОПК, связанных с ФГОС программы
    if program.fgos:
        uk_opk_competencies = session.query(Competency).options(
            selectinload(Competency.indicators),
            selectinload(Competency.competency_type)
        ).filter(
            Competency.fgos_vo_id == program.fgos.id,
            Competency.competency_type.has(CompetencyType.code.in_(['УК', 'ОПК']))
        ).all()
        relevant_competencies.extend(uk_opk_competencies)
        logger.debug(f"Загружено {len(uk_opk_competencies)} УК/ОПК для ФГОС ID {program.fgos.id}.")
    else:
        logger.warning(f"ОП ID {program.id} не связана с ФГОС. УК/ОПК не будут загружены.")

    # 2. Загрузка ПК, связанных с данной образовательной программой
    pk_competencies = session.query(Competency).options(
        selectinload(Competency.indicators),
        selectinload(Competency.competency_type),
        # ИСПРАВЛЕНИЕ: Правильная цепочка отношений для загрузки ProfStandard
        selectinload(Competency.based_on_labor_function)
            .selectinload(LaborFunction.generalized_labor_function)
            .selectinload(GeneralizedLaborFunction.prof_standard)
    ).join(Competency.educational_programs_assoc).filter(
        CompetencyEducationalProgram.educational_program_id == program.id,
        Competency.competency_type.has(CompetencyType.code == 'ПК')
    ).all()
    relevant_competencies.extend(pk_competencies)
    logger.debug(f"Загружено {len(pk_competencies)} ПК для ОП ID {program.id}.")

    # 3. Форматирование результата
    competencies_data = []
    all_indicator_ids_for_matrix = set()

    all_comp_types = session.query(CompetencyType).all()
    comp_type_id_sort_order = {ct.id: i for i, ct_code in enumerate(['УК', 'ОПК', 'ПК']) for ct in all_comp_types if ct.code == ct_code}
    
    relevant_competencies.sort(key=lambda c: (comp_type_id_sort_order.get(c.competency_type_id, 999), c.code))

    for comp in relevant_competencies:
        comp_dict = comp.to_dict(
            rules=['-indicators', '-competency_type', '-fgos', '-based_on_labor_function', '-matrix_entries', '-educational_programs_assoc']
        )
        comp_dict['type_code'] = comp.competency_type.code if comp.competency_type else "UNKNOWN"
        comp_dict['indicators'] = []

        comp_dict['source_document_id'] = None
        comp_dict['source_document_code'] = None
        comp_dict['source_document_name'] = None
        comp_dict['source_document_type'] = None

        if comp.competency_type and comp.competency_type.code in ['УК', 'ОПК']:
            if comp.fgos:
                comp_dict['source_document_id'] = comp.fgos.id
                comp_dict['source_document_code'] = comp.fgos.direction_code
                comp_dict['source_document_name'] = comp.fgos.direction_name
                comp_dict['source_document_type'] = "ФГОС ВО"
        elif comp.competency_type and comp.competency_type.code == 'ПК':
            if comp.based_on_labor_function and \
               comp.based_on_labor_function.generalized_labor_function and \
               comp.based_on_labor_function.generalized_labor_function.prof_standard:
                ps = comp.based_on_labor_function.generalized_labor_function.prof_standard
                comp_dict['source_document_id'] = ps.id
                comp_dict['source_document_code'] = ps.code
                comp_dict['source_document_name'] = ps.name
                comp_dict['source_document_type'] = "Профстандарт"
            else:
                comp_dict['source_document_type'] = "Ручной ввод"
                comp_dict['source_document_code'] = "N/A"
                comp_dict['source_document_name'] = "Введено вручную"

        if comp.based_on_labor_function:
            comp_dict['based_on_labor_function_id'] = comp.based_on_labor_function.id
            comp_dict['based_on_labor_function_code'] = comp.based_on_labor_function.code
            comp_dict['based_on_labor_function_name'] = comp.based_on_labor_function.name

        if comp.indicators:
            sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
            for ind in sorted_indicators:
                all_indicator_ids_for_matrix.add(ind.id)
                ind_dict = ind.to_dict();
                ind_dict['competency_code'] = comp.code; ind_dict['competency_name'] = comp.name
                ind_dict['competency_type_code'] = comp_dict['type_code']
                
                ind_dict['source_document_id'] = comp_dict['source_document_id']
                ind_dict['source_document_code'] = comp_dict['source_document_code']
                ind_dict['source_document_name'] = comp_dict['source_document_name']
                ind_dict['source_document_type'] = comp_dict['source_document_type']
                ind_dict['selected_ps_elements_ids'] = ind.selected_ps_elements_ids


                comp_dict['indicators'].append(ind_dict)
        competencies_data.append(comp_dict)
    
    return competencies_data, all_indicator_ids_for_matrix


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