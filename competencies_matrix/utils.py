# competencies_matrix/utils.py
import logging
import traceback
from typing import Dict, Any, Optional

import pandas as pd

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, NoResultFound, MultipleResultsFound

# Импортируем модели из maps, чтобы не зависеть от них напрямую в logic.py
from maps.models import db, NameOP, SprOKCO, SprFaculty, Department, SprDegreeEducation, SprFormEducation

logger = logging.getLogger(__name__)

def find_or_create_lookup(model, filter_criteria: Dict[str, Any], defaults: Dict[str, Any], session: Session) -> Optional[Any]:
    """
    (УЛУЧШЕНО) Находит или создает запись в справочной таблице.
    Теперь более устойчив к PendingRollbackError и конкурентным вставкам.
    """
    clean_filter = {k: v for k, v in filter_criteria.items() if v is not None and (not isinstance(v, str) or v.strip())}
    clean_defaults = {k: v for k, v in defaults.items() if v is not None and (not isinstance(v, str) or v.strip())}

    # Если clean_filter пуст, но модель требует обязательных полей, это будет проблема.
    # В таких случаях нужно убедиться, что defaults содержат все необходимое.
    if not clean_filter and not all(k in clean_defaults for k in model.__table__.columns if not model.__table__.columns[k].nullable and not model.__table__.columns[k].primary_key and not model.__table__.columns[k].default and not model.__table__.columns[k].onupdate):
        if not clean_defaults:
            logger.warning(f"find_or_create_lookup: Called for {model.__name__} with empty filter and defaults. Skipping.")
            return None

    # Попытка найти существующую запись
    try:
        instance = session.query(model).filter_by(**clean_filter).first()
        if instance:
            return instance
    except (SQLAlchemyError, Exception) as e:
        logger.error(f"DB Error finding {model.__name__} with {clean_filter}: {e}", exc_info=True)
        session.rollback() # Откат при ошибке запроса
        return None

    # Если не нашли, пытаемся создать
    create_data = {**clean_defaults, **clean_filter}
    
    try:
        # Важно: begin_nested() требует активной внешней транзакции.
        # Если внешняя транзакция уже отвалилась (PendingRollbackError), begin_nested() тоже упадет.
        # В таком случае, весь AUP-клон должен быть откачен.
        instance = model(**create_data)
        session.add(instance)
        session.flush() # flush() для попытки записи и получения ID
        return instance
    except IntegrityError:
        # Это может произойти, если запись была создана между .first() и .add() (конкурентная вставка)
        logger.warning(f"IntegrityError creating {model.__name__} with {create_data}. Retrying find.")
        session.rollback() # Откатываем вложенную транзакцию или текущую, если не вложена
        try:
            # Повторная попытка найти после отката
            instance = session.query(model).filter_by(**clean_filter).first()
            if instance:
                return instance
            else:
                logger.error(f"IntegrityError creating {model.__name__} but could not find after rollback. Data: {create_data}")
                return None
        except (SQLAlchemyError, Exception) as e_refetch:
            logger.error(f"DB Error refetching {model.__name__} after IntegrityError: {e_refetch}", exc_info=True)
            session.rollback() # Откат, если и повторный поиск провалился
            return None
    except SQLAlchemyError as e:
        logger.error(f"DB Error creating {model.__name__} with {create_data}: {e}", exc_info=True)
        session.rollback() # Откат при других ошибках SQLAlchemy
        return None
    except Exception as e:
        logger.error(f"Unexpected error creating {model.__name__} with data {create_data}: {e}", exc_info=True)
        session.rollback() # Откат при других непредвиденных ошибках
        return None


def find_or_create_name_op(program_code: Optional[str], profile_name: Optional[str], okso_name: Optional[str], session: Session) -> Optional[NameOP]:
    """
    Находит или создает запись NameOP (профиль) и связанный SprOKCO.
    """
    program_code_clean = str(program_code).strip() if program_code is not None and (not isinstance(program_code, float) or not pd.isna(program_code)) else None # Updated check for NaN
    if not program_code_clean:
        logger.warning("find_or_create_name_op: program_code is empty or invalid. Cannot proceed.")
        return None

    profile_name_clean = str(profile_name).strip() if profile_name is not None and (not isinstance(profile_name, float) or not pd.isna(profile_name)) and str(profile_name).strip() else f"Основная ОП ({program_code_clean})"
    okso_name_clean = str(okso_name).strip() if okso_name is not None and (not isinstance(okso_name, float) or not pd.isna(okso_name)) and str(okso_name).strip() else f"Направление {program_code_clean}"

    # Use find_or_create_lookup for SprOKCO
    okso = find_or_create_lookup(SprOKCO, {'program_code': program_code_clean}, {'name_okco': okso_name_clean}, session)
    if not okso:
        logger.error(f"find_or_create_name_op: Failed to find or create SprOKCO for program_code '{program_code_clean}'.")
        return None

    name_op_filter = {'program_code': program_code_clean, 'name_spec': profile_name_clean}
    name_op = session.query(NameOP).filter_by(**name_op_filter).first()
    if name_op:
         if not name_op.okco: # Link OKCO if it's missing (can happen if NameOP was created without OKCO)
             name_op.okco = okso
             session.add(name_op)
         return name_op

    # Generate num_profile
    max_num = session.query(db.func.max(NameOP.num_profile)).filter_by(program_code=program_code_clean).scalar()
    num_profile_str = '01' # Default
    try:
        if max_num and str(max_num).isdigit():
            next_num_int = int(max_num) + 1
            num_profile_str = f"{next_num_int:02}"
        else:
            logger.debug(f"max_num for {program_code_clean} is not a digit or None: '{max_num}'. Using default '01'.")
    except Exception as e:
        logger.warning(f"Error generating next num_profile for {program_code_clean}: {e}. Using default '01'.")

    # Use find_or_create_lookup for NameOP
    name_op_defaults = {'num_profile': num_profile_str, 'okco': okso}
    new_name_op = find_or_create_lookup(NameOP, name_op_filter, name_op_defaults, session)

    if new_name_op and not new_name_op.okco: # Ensure OKCO is linked if NameOP was just created
         new_name_op.okco = okso
         session.add(new_name_op)

    return new_name_op