import logging
from typing import Dict, List, Any, Optional

from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from maps.models import db as local_db

from ..models import (
    EducationalProgram, Competency, Indicator, CompetencyType,
    LaborFunction, GeneralizedLaborFunction, ProfStandard,
    CompetencyEducationalProgram
)

logger = logging.getLogger(__name__)

def get_all_competencies() -> List[Dict[str, Any]]:
    try:
        competencies = local_db.session.query(Competency).options(
            joinedload(Competency.competency_type),
            joinedload(Competency.fgos),
            joinedload(Competency.based_on_labor_function)
                .joinedload(LaborFunction.generalized_labor_function)
                .joinedload(GeneralizedLaborFunction.prof_standard)
        ).all()
        result = []
        for comp in competencies:
            # Убираем `include_source_info=True`. Теперь `to_dict` сам добавит нужные поля.
            # Мы также передаем include_type=True, чтобы `type_code` был в ответе.
            comp_dict = comp.to_dict(
                rules=['-indicators', '-fgos', '-based_on_labor_function', '-matrix_entries', '-educational_programs_assoc'], 
                include_type=True
            )
            # source_document_* и based_on_labor_function_* поля теперь добавляются методом to_dict модели Competency
            result.append(comp_dict)
        return result
    except Exception as e:
        logger.error(f"Error fetching all competencies with source info: {e}", exc_info=True)
        raise

def get_competency_details(comp_id: int) -> Optional[Dict[str, Any]]:
    try:
        competency = local_db.session.query(Competency).options(
            joinedload(Competency.competency_type), # Добавлено для получения type_code
            joinedload(Competency.indicators),
            joinedload(Competency.fgos), # Добавлено для source_document_type
            joinedload(Competency.based_on_labor_function) # Добавлено для source_document_type
                .joinedload(LaborFunction.generalized_labor_function)
                .joinedload(GeneralizedLaborFunction.prof_standard)
        ).get(comp_id)
        if not competency:
            logger.warning(f"Competency with id {comp_id} not found.")
            return None
        
        # Теперь все source_* и based_on_labor_function_* поля генерируются в to_dict
        result = competency.to_dict(
            rules=['-fgos', '-based_on_labor_function', '-matrix_entries', '-educational_programs_assoc'], # Исключаем отношения, чтобы не было рекурсии
            include_indicators=True, 
            include_type=True, 
            include_educational_programs=True
        )
        return result
    except Exception as e:
        logger.error(f"Error fetching competency {comp_id} details: {e}", exc_info=True)
        raise

def create_competency(data: Dict[str, Any], session: Session) -> Optional[Competency]:
    required_fields = ['type_code', 'code', 'name']
    if not all(field in data and data[field] is not None and str(data[field]).strip() for field in required_fields):
        raise ValueError("Отсутствуют обязательные поля: type_code, code, name.")
    if data['type_code'] != 'ПК': # Сейчас этот эндпоинт только для ПК
        raise ValueError(f"Данный эндпоинт предназначен только для создания ПК. Получен тип '{data['type_code']}'.")

    educational_program_ids = data.get('educational_program_ids', [])
    if not isinstance(educational_program_ids, list):
         logger.warning(f"'educational_program_ids' is not a list. Ignoring or handling as error.")
         educational_program_ids = []
    
    based_on_labor_function_id = data.get('based_on_labor_function_id')
    
    try:
        comp_type = session.query(CompetencyType).filter_by(code=data['type_code']).first()
        if not comp_type:
            raise ValueError(f"Тип компетенции с кодом '{data['type_code']}' не найден.")
        
        existing_comp = session.query(Competency).filter_by(code=str(data['code']).strip(), competency_type_id=comp_type.id).first()
        if existing_comp:
            raise IntegrityError(f"Competency with code {data['code']} already exists for this type.", {}, None)
        
        labor_function = None
        if based_on_labor_function_id:
             labor_function = session.query(LaborFunction).get(based_on_labor_function_id)
             if not labor_function:
                 logger.warning(f"Labor function with ID {based_on_labor_function_id} not found. Skipping link.")
                 based_on_labor_function_id = None
        
        competency = Competency(
            competency_type_id=comp_type.id, code=str(data['code']).strip(),
            name=str(data['name']).strip(),
            description=str(data['description']).strip() if data.get('description') is not None else None,
            fgos_vo_id=data.get('fgos_id') if data.get('type_code') in ['УК', 'ОПК'] else None, # Если это УК/ОПК, привязываем к ФГОС
            based_on_labor_function_id=based_on_labor_function_id if data.get('type_code') == 'ПК' else None # Если это ПК, привязываем к ТФ
        )
        session.add(competency)
        session.flush()

        for ep_id in educational_program_ids:
            educational_program = session.query(EducationalProgram).get(ep_id)
            if educational_program:
                 assoc = CompetencyEducationalProgram(competency_id=competency.id, educational_program_id=ep_id)
                 session.add(assoc)
            else:
                logger.warning(f"Educational Program with ID {ep_id} not found. Skipping link for competency {competency.id}.")

        session.flush()
        return competency
    except IntegrityError as e:
        logger.error(f"Database IntegrityError creating competency: {e}", exc_info=True)
        raise e
    except SQLAlchemyError as e:
        logger.error(f"Database error creating competency: {e}", exc_info=True)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error creating competency: {e}", exc_info=True)
        raise e

def update_competency(comp_id: int, data: Dict[str, Any], session: Session) -> Optional[Dict[str, Any]]:
    if not data:
        raise ValueError("Отсутствуют данные для обновления.")
    educational_program_ids = data.get('educational_program_ids')
    try:
        competency = session.query(Competency).options(
            selectinload(Competency.educational_programs_assoc)
        ).get(comp_id)
        if not competency:
            return None
        
        # Разрешаем редактировать название и описание для всех типов,
        # но привязка к ФГОС/ТФ только через отдельный эндпоинт, если потребуется
        allowed_fields = {'name', 'description'}
        updated = False
        
        for field in data:
            if field in allowed_fields:
                 processed_value = str(data[field]).strip() if data[field] is not None else None
                 if field == 'description' and processed_value == '':
                     processed_value = None
                 
                 if getattr(competency, field) != processed_value:
                     setattr(competency, field, processed_value)
                     updated = True
            elif field == 'educational_program_ids': # Обрабатываем отдельно
                pass
            else:
                logger.warning(f"Ignoring field '{field}' for update of comp {comp_id} as it is not allowed via this endpoint.")
        
        if educational_program_ids is not None:
            if not isinstance(educational_program_ids, list):
                logger.warning(f"educational_program_ids for competency {comp_id} is not a list. Skipping update of associations.")
            else:
                current_ep_ids = {assoc.educational_program_id for assoc in competency.educational_programs_assoc}
                new_ep_ids = set(educational_program_ids)

                to_delete_ids = current_ep_ids - new_ep_ids
                if to_delete_ids:
                    session.query(CompetencyEducationalProgram).filter(
                        CompetencyEducationalProgram.competency_id == competency.id,
                        CompetencyEducationalProgram.educational_program_id.in_(to_delete_ids)
                    ).delete(synchronize_session='fetch')
                    updated = True
                
                to_add_ids = new_ep_ids - current_ep_ids
                if to_add_ids:
                    for ep_id in to_add_ids:
                        educational_program = session.query(EducationalProgram).get(ep_id)
                        if educational_program:
                            assoc = CompetencyEducationalProgram(competency_id=competency.id, educational_program_id=ep_id)
                            session.add(assoc)
                            updated = True
                        else:
                            logger.warning(f"Educational Program with ID {ep_id} not found when adding link for competency {comp_id}. Skipping.")
                if to_delete_ids or to_add_ids:
                    session.flush() # Применяем изменения связей немедленно
        
        if updated:
            session.add(competency)
            session.flush()
        
        session.refresh(competency)
        # Теперь все source_* и based_on_labor_function_* поля генерируются в to_dict
        return competency.to_dict(rules=['-indicators', '-fgos', '-based_on_labor_function'], include_type=True, include_educational_programs=True)

    except IntegrityError as e:
        logger.error(f"Database IntegrityError updating competency {comp_id}: {e}", exc_info=True)
        raise e
    except SQLAlchemyError as e:
        logger.error(f"Database error updating competency {comp_id}: {e}", exc_info=True)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error updating competency {comp_id}: {e}", exc_info=True)
        raise e

def delete_competency(comp_id: int, session: Session) -> bool:
    try:
         comp_to_delete = session.query(Competency).get(comp_id)
         if not comp_to_delete:
             logger.warning(f"Competency {comp_id} not found for deletion.")
             return False
         
         session.delete(comp_to_delete)
         return True
    except SQLAlchemyError as e:
        logger.error(f"Database error deleting competency {comp_id}: {e}", exc_info=True)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error deleting competency {comp_id}: {e}", exc_info=True)
        raise e

def get_all_indicators() -> List[Dict[str, Any]]:
    try:
        indicators = local_db.session.query(Indicator).options(joinedload(Indicator.competency)).all()
        result = []
        for ind in indicators:
             ind_dict = ind.to_dict(rules=['-labor_functions', '-matrix_entries'], include_competency=True) # include_competency=True для получения code/name
             result.append(ind_dict)
        return result
    except Exception as e:
        logger.error(f"Error fetching all indicators: {e}", exc_info=True)
        raise

def get_indicator_details(ind_id: int) -> Optional[Dict[str, Any]]:
    try:
        indicator = local_db.session.query(Indicator).options(joinedload(Indicator.competency)).get(ind_id)
        if not indicator:
            logger.warning(f"Indicator with id {ind_id} not found.")
            return None
        result = indicator.to_dict(rules=['-competency', '-labor_functions', '-matrix_entries'], include_competency=True)
        return result
    except Exception as e:
        logger.error(f"Error fetching indicator {ind_id} details: {e}", exc_info=True)
        raise

def create_indicator(data: Dict[str, Any], session: Session) -> Optional[Indicator]:
    required_fields = ['competency_id', 'code', 'formulation']
    if not all(field in data and data[field] is not None and str(data[field]).strip() for field in required_fields):
        raise ValueError("Отсутствуют обязательные поля: competency_id, code, formulation.")
    try:
        competency = session.query(Competency).get(data['competency_id'])
        if not competency:
            raise ValueError(f"Родительская компетенция с ID '{data['competency_id']}' не найдена.")
        
        selected_ps_elements_ids = data.get('selected_ps_elements_ids')
        if selected_ps_elements_ids is not None and not isinstance(selected_ps_elements_ids, dict):
            logger.warning(f"Invalid format for selected_ps_elements_ids: {type(selected_ps_elements_ids)}. Must be a dict. Ignoring.")
            selected_ps_elements_ids = None
        elif selected_ps_elements_ids is None:
            selected_ps_elements_ids = {}

        existing_indicator = session.query(Indicator).filter_by(code=str(data['code']).strip(), competency_id=data['competency_id']).first()
        if existing_indicator:
            raise IntegrityError(f"Индикатор с кодом '{data['code']}' уже существует для компетенции '{competency.code}'.", {}, None)

        indicator = Indicator(
            competency_id=data['competency_id'], code=str(data['code']).strip(), formulation=str(data['formulation']).strip(),
            source=str(data['source']).strip() if data.get('source') is not None else None,
            selected_ps_elements_ids=selected_ps_elements_ids
        )
        session.add(indicator)
        session.flush()
        return indicator
    except IntegrityError as e:
        logger.error(f"Database IntegrityError creating indicator: {e}", exc_info=True)
        raise e
    except SQLAlchemyError as e:
        logger.error(f"Database error creating indicator: {e}", exc_info=True)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error creating indicator: {e}", exc_info=True)
        raise e

def update_indicator(ind_id: int, data: Dict[str, Any], session: Session) -> Optional[Indicator]:
    if not data:
        raise ValueError("Отсутствуют данные для обновления.")
    try:
        indicator = session.query(Indicator).options(
            selectinload(Indicator.competency) # Загружаем для получения кода/названия в to_dict
        ).get(ind_id)
        if not indicator:
            return None
        
        allowed_fields = {'code', 'formulation', 'source', 'selected_ps_elements_ids'}
        updated = False
        
        for field in data:
            if field in allowed_fields:
                 processed_value = str(data[field]).strip() if data[field] is not None and field != 'selected_ps_elements_ids' else data[field]
                 if field == 'source' and processed_value == '':
                     processed_value = None
                 
                 if field == 'code' and processed_value != indicator.code:
                      existing_with_new_code = session.query(Indicator).filter_by(
                           code=processed_value, competency_id=indicator.competency_id
                      ).first()
                      if existing_with_new_code and existing_with_new_code.id != indicator.id:
                           raise IntegrityError(f"Indicator with code {processed_value} already exists for competency {indicator.competency_id}.", {}, None)
                 
                 if field == 'selected_ps_elements_ids':
                     if data[field] is not None and not isinstance(data[field], dict):
                         logger.warning(f"Invalid format for selected_ps_elements_ids received for indicator {ind_id}: {type(data[field])}. Must be a dict or None. Skipping update for this field.")
                         continue
                     if indicator.selected_ps_elements_ids != data[field]:
                         indicator.selected_ps_elements_ids = data[field]
                         updated = True
                 elif getattr(indicator, field) != processed_value:
                     setattr(indicator, field, processed_value)
                     updated = True
            else:
                logger.warning(f"Ignoring field '{field}' for update of ind {ind_id} as it is not allowed via this endpoint.")
        
        if updated:
            session.add(indicator)
            session.flush()
        
        session.refresh(indicator)
        return indicator.to_dict(include_competency=True) # Включаем компетенцию для фронтенда

    except IntegrityError as e:
        logger.error(f"Database IntegrityError updating indicator {ind_id}: {e}", exc_info=True)
        raise e
    except SQLAlchemyError as e:
        logger.error(f"Database error updating indicator {ind_id}: {e}", exc_info=True)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error updating indicator {ind_id}: {e}", exc_info=True)
        raise e

def delete_indicator(ind_id: int, session: Session) -> bool:
    try:
         ind_to_delete = session.query(Indicator).get(ind_id)
         if not ind_to_delete:
             logger.warning(f"Indicator {ind_id} not found for deletion.")
             return False
         
         session.delete(ind_to_delete)
         return True
    except SQLAlchemyError as e:
        logger.error(f"Database error deleting indicator {ind_id}: {e}", exc_info=True)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error deleting indicator {ind_id}: {e}", exc_info=True)
        raise e