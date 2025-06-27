import datetime
import logging
from typing import Dict, List, Any, Optional

from flask import current_app
from sqlalchemy import create_engine, select, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from maps.models import db as local_db, SprDiscipline
from maps.models import (
    AupInfo as LocalAupInfo, AupData as LocalAupData,
    SprFaculty, Department, SprDegreeEducation, SprFormEducation
)
from ..models import EducationalProgramAup
from ..utils import find_or_create_lookup, find_or_create_name_op
from ..external_models import (
    ExternalAupInfo, ExternalNameOP, ExternalSprOKCO, ExternalSprFormEducation,
    ExternalSprDegreeEducation, ExternalAupData, ExternalSprDiscipline, ExternalSprFaculty,
    ExternalDepartment
)

logger = logging.getLogger(__name__)

_external_db_engine = None

def get_external_db_engine():
    """Initializes and returns the engine for the external KD DB."""
    global _external_db_engine
    if _external_db_engine is None:
        db_url = current_app.config.get('EXTERNAL_KD_DATABASE_URL')
        if not db_url:
            raise RuntimeError("EXTERNAL_KD_DATABASE_URL is not configured.")
        try:
            _external_db_engine = create_engine(db_url)
        except Exception as e:
            logger.error(f"Failed to create external DB engine: {e}", exc_info=True)
            raise RuntimeError(f"Failed to create external DB engine: {e}")
    return _external_db_engine

def _clone_external_aup_to_local(
    external_aup_data: Dict[str, Any], session: Session
) -> Optional[LocalAupInfo]:
    """
    Клонирует данные о АУП и его дисциплинах из внешнего источника (словаря) в локальную БД.
    Возвращает созданный или найденный локальный объект AupInfo.
    """
    aup_num = external_aup_data.get('num_aup')
    if not aup_num:
        logger.error("Внешние данные АУП не содержат 'num_aup'. Клонирование невозможно.")
        return None

    # 1. Проверяем, может АУП уже есть локально
    local_aup = session.query(LocalAupInfo).filter_by(num_aup=aup_num).first()
    if local_aup:
        logger.info(f"Локальный АУП {aup_num} уже существует. Возвращаем существующую запись.")
        return local_aup

    logger.info(f"Клонирование внешнего АУП {aup_num} в локальную БД.")
    try:
        # 2. Клонируем связанные справочные сущности (факультет, кафедра и т.д.)
        # Используем утилиты, скопированные из maps/logic/save_excel_data.py
        faculty = find_or_create_lookup(SprFaculty, {'name_faculty': external_aup_data.get("faculty_name")}, {'id_branch': 1}, session)
        department = find_or_create_lookup(Department, {'name_department': external_aup_data.get("department_name")}, {}, session)
        degree = find_or_create_lookup(SprDegreeEducation, {'name_deg': external_aup_data.get("degree_education_name")}, {}, session)
        form = find_or_create_lookup(SprFormEducation, {'form': external_aup_data.get("form_education_name")}, {}, session)
        name_op = find_or_create_name_op(external_aup_data.get("program_code"), external_aup_data.get("name_spec"), external_aup_data.get("name_okco"), session)

        if not all([faculty, degree, form, name_op]):
            raise ValueError("Не удалось найти или создать обязательные связанные сущности для клонирования.")

        # 3. Создаем саму запись AupInfo
        is_actual = datetime.datetime.today().year <= (external_aup_data.get('year_end') or 0)
        new_local_aup = LocalAupInfo(
            num_aup=aup_num, id_faculty=faculty.id_faculty, id_degree=degree.id_degree,
            id_form=form.id_form, id_spec=name_op.id_spec,
            id_department=department.id_department if department else None,
            year_beg=external_aup_data.get('year_beg'), year_end=external_aup_data.get('year_end'),
            qualification=external_aup_data.get('qualification'), type_standard=external_aup_data.get('type_standard'),
            base=external_aup_data.get('base'), period_educ=external_aup_data.get('period_educ'),
            years=external_aup_data.get('years'), months=external_aup_data.get('months'),
            is_actual=is_actual, is_delete=False, file=f"cloned_from_kd_{aup_num}"
        )
        session.add(new_local_aup)
        session.flush() # Получаем ID для new_local_aup

        # 4. Получаем и клонируем дисциплины (AupData)
        external_disciplines = get_external_aup_disciplines(external_aup_data.get('id_aup'))
        cloned_disciplines_count = 0
        for disc_data in external_disciplines:
            spr_discipline = find_or_create_lookup(SprDiscipline, {'title': disc_data['title']}, {}, session)
            if not spr_discipline:
                logger.warning(f"Не удалось найти или создать SprDiscipline для '{disc_data['title']}'. Пропуск.")
                continue

            new_local_aup_data = LocalAupData(
                id_aup=new_local_aup.id_aup, shifr=disc_data.get('shifr'), id_discipline=spr_discipline.id,
                _discipline_from_table=disc_data['title'], id_period=disc_data.get('semester'),
                id_type_record=disc_data.get('id_type_record'), zet=int((disc_data.get('zet', 0) or 0) * 100),
                amount=disc_data.get('amount'), id_type_control=disc_data.get('id_type_control')
            )
            session.add(new_local_aup_data)
            cloned_disciplines_count += 1
        
        logger.info(f"Склонировано {cloned_disciplines_count} дисциплин для АУП {aup_num}.")
        session.flush()
        logger.info(f"Успешно склонирован внешний АУП {aup_num} в локальную БД с ID {new_local_aup.id_aup}.")
        return new_local_aup

    except Exception as e:
        logger.error(f"Ошибка при клонировании внешнего АУП {aup_num} в локальную БД: {e}", exc_info=True)
        return None

def get_external_aups_list(
    program_code: Optional[str] = None, profile_num: Optional[str] = None, profile_name: Optional[str] = None,
    form_education_name: Optional[str] = None, year_beg: Optional[int] = None, degree_education_name: Optional[str] = None,
    search_query: Optional[str] = None, offset: int = 0, limit: Optional[int] = 20
) -> Dict[str, Any]:
    """Fetches AUP list from external KD DB with filters and pagination."""
    engine = get_external_db_engine()
    with Session(engine) as session:
        try:
            query = session.query(ExternalAupInfo).options(
                joinedload(ExternalAupInfo.spec).joinedload(ExternalNameOP.okco),
                joinedload(ExternalAupInfo.form), joinedload(ExternalAupInfo.degree),
                joinedload(ExternalAupInfo.faculty), joinedload(ExternalAupInfo.department)
            )

            filters = []
            if program_code: filters.append(ExternalSprOKCO.program_code == program_code)
            
            profile_filters_or = []
            if profile_num: profile_filters_or.append(ExternalNameOP.num_profile == profile_num)
            if profile_name: profile_filters_or.append(ExternalNameOP.name_spec.ilike(f"%{profile_name}%"))
            if profile_filters_or: filters.append(or_(*profile_filters_or))

            if form_education_name: filters.append(ExternalSprFormEducation.form == form_education_name)
            if year_beg: filters.append(ExternalAupInfo.year_beg == year_beg)
            if degree_education_name: filters.append(ExternalAupInfo.degree.has(ExternalSprDegreeEducation.name_deg == degree_education_name))

            query = query.join(ExternalAupInfo.spec, isouter=True)\
                         .join(ExternalNameOP.okco, isouter=True)
            query = query.join(ExternalAupInfo.form, isouter=True)
            query = query.join(ExternalAupInfo.degree, isouter=True)
            query = query.join(ExternalAupInfo.faculty, isouter=True)
            query = query.join(ExternalAupInfo.department, isouter=True)

            if filters: query = query.filter(and_(*filters))

            if search_query:
                 search_pattern = f"%{search_query}%"
                 search_conditions = [
                     ExternalAupInfo.num_aup.ilike(search_pattern), ExternalNameOP.name_spec.ilike(search_pattern),
                     ExternalSprOKCO.program_code.ilike(search_pattern), ExternalSprFaculty.name_faculty.ilike(search_pattern),
                     ExternalDepartment.name_department.ilike(search_pattern),
                 ]
                 query = query.filter(or_(*search_conditions))

            total_count = query.count()
            query = query.order_by(ExternalAupInfo.year_beg.desc(), ExternalAupInfo.num_aup)
            if limit is not None: query = query.offset(offset).limit(limit)
            external_aups = query.all()
            result_items = []
            for aup in external_aups:
                aup_dict = aup.as_dict()
                if aup.qualification: aup_dict['qualification'] = aup.qualification
                if aup.degree and aup.degree.name_deg: aup_dict['education_level'] = aup.degree.name_deg
                result_items.append(aup_dict)
            logger.info(f"Fetched {len(result_items)} of {total_count} AUPs from external KD DB.")
            return {"total": total_count, "items": result_items}

        except Exception as e: logger.error(f"Error fetching external AUPs: {e}", exc_info=True); raise

def get_external_aup_disciplines(aup_id: int) -> List[Dict[str, Any]]:
    """Fetches discipline entries (AupData) for a specific AUP from external KD DB."""
    engine = get_external_db_engine()
    with Session(engine) as session:
        try:
            aup_data_entries = session.query(ExternalAupData).filter(ExternalAupData.id_aup == aup_id)\
                .order_by(ExternalAupData.id_period, ExternalAupData.shifr, ExternalAupData.id).all()

            result = []
            for entry in aup_data_entries:
                 result.append({
                     'aup_data_id': entry.id, 'id_aup': entry.id_aup, 'discipline_id': entry.id_discipline,
                     'title': entry.discipline, 'semester': entry.id_period, 'shifr': entry.shifr,
                     'id_type_record': entry.id_type_record, 'zet': (entry.zet / 100) if entry.zet is not None else 0,
                     'amount': entry.amount, 'id_type_control': entry.id_type_control
                 })
            return result
        except Exception as e: logger.error(f"Error fetching external AupData for external AUP ID {aup_id}: {e}", exc_info=True); raise