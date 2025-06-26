# filepath: competencies_matrix/utils.py
import logging
import traceback
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import pandas as pd

# Импортируем модели из maps, чтобы не зависеть от них напрямую в logic.py
from maps.models import db, NameOP, SprOKCO, SprFaculty, Department, SprDegreeEducation, SprFormEducation

logger = logging.getLogger(__name__)

def find_or_create_lookup(model, filter_criteria: Dict[str, Any], defaults: Dict[str, Any], session: Session) -> Optional[Any]:
    """
    (СКОПИРОВАНО ИЗ maps/logic/save_excel_data.py)
    Находит или создает запись в справочной таблице.
    """
    clean_filter = {k: v for k, v in filter_criteria.items() if v is not None and (not isinstance(v, str) or v.strip())}
    clean_defaults = {k: v for k, v in defaults.items() if v is not None and (not isinstance(v, str) or v.strip())}

    instance = None
    if clean_filter:
        try:
            instance = session.query(model).filter_by(**clean_filter).first()
            if instance:
                return instance
        except SQLAlchemyError as e:
            logger.error(f"DB Error finding {model.__name__} with {clean_filter}: {e}")
            pass

    create_data = {**clean_defaults, **clean_filter}
    if not create_data:
        return None

    try:
        with session.begin_nested():
            instance = model(**create_data)
            session.add(instance)
            session.flush()
            return instance
    except IntegrityError:
        if clean_filter:
             try:
                instance = session.query(model).filter_by(**clean_filter).first()
                if instance:
                    return instance
                else:
                    return None
             except SQLAlchemyError as e_refetch:
                  logger.error(f"DB Error refetching {model.__name__} after integrity error: {e_refetch}")
                  return None
        else:
             logger.error(f"Integrity error creating {model.__name__} with no filter criteria. Data: {create_data}")
             return None
    except Exception as e:
        logger.error(f"Unexpected error creating {model.__name__} with data {create_data}: {e}")
        traceback.print_exc()
        return None


def find_or_create_name_op(program_code: Optional[str], profile_name: Optional[str], okso_name: Optional[str], session: Session) -> Optional[NameOP]:
    """
    (СКОПИРОВАНО ИЗ maps/logic/save_excel_data.py)
    Находит или создает запись NameOP (профиль) и связанный SprOKCO.
    """
    program_code_clean = str(program_code).strip() if program_code and not pd.isna(program_code) else None
    if not program_code_clean:
        return None

    profile_name_clean = str(profile_name).strip() if profile_name and not pd.isna(profile_name) and str(profile_name).strip() else f"Основная ОП ({program_code_clean})"
    okso_name_clean = str(okso_name).strip() if okso_name and not pd.isna(okso_name) and str(okso_name).strip() else f"Направление {program_code_clean}"

    okso = find_or_create_lookup(SprOKCO, {'program_code': program_code_clean}, {'name_okco': okso_name_clean}, session)
    if not okso:
        return None

    name_op_filter = {'program_code': program_code_clean, 'name_spec': profile_name_clean}
    name_op = session.query(NameOP).filter_by(**name_op_filter).first()
    if name_op:
         if not name_op.okco:
             name_op.okco = okso
             session.add(name_op)
         return name_op

    max_num = session.query(db.func.max(NameOP.num_profile)).filter_by(program_code=program_code_clean).scalar()
    try:
        next_num_int = int(max_num) + 1 if max_num and str(max_num).isdigit() else 1
        num_profile_str = f"{next_num_int:02}"
    except Exception as e:
        num_profile_str = '01'

    name_op_defaults = {'num_profile': num_profile_str, 'okco': okso}
    new_name_op = find_or_create_lookup(NameOP, name_op_filter, name_op_defaults, session)

    if new_name_op and not new_name_op.okco:
         new_name_op.okco = okso
         session.add(new_name_op)

    return new_name_op