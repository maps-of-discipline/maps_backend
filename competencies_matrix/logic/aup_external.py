import datetime
import logging
from typing import Dict, List, Any, Optional

from flask import current_app
from sqlalchemy import create_engine, select, and_, or_, exc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from maps.models import db as local_db
from maps.models import (
    AupInfo as LocalAupInfo, AupData as LocalAupData,
    SprFaculty, Department, SprDegreeEducation, SprFormEducation,
    D_Blocks, D_Part, D_Modules, Groups, D_TypeRecord, D_ControlType, D_EdIzmereniya, D_Period, NameOP, SprOKCO,
    SprDiscipline # <-- ДОБАВЛЕНО
)

from ..models import EducationalProgramAup, EducationalProgram, CompetencyMatrix, Competency, Indicator

from ..external_models import (
    ExternalAupInfo, ExternalNameOP, ExternalSprOKCO, ExternalSprFormEducation,
    ExternalSprDegreeEducation, ExternalAupData, ExternalSprDiscipline as ExternalSprDisciplineModel, 
    ExternalSprFaculty,
    ExternalDepartment,
    ExternalDBlocks, ExternalDPart, ExternalDModules, ExternalGroups,
    ExternalDTypeRecord, ExternalDControlType, ExternalDEdIzmereniya, ExternalDPeriod
)

from ..utils import find_or_create_lookup, find_or_create_name_op

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

def import_aup_from_external_db(aup_num: str, program_id: int, session: Session) -> Dict[str, Any]:
    """
    Импортирует АУП и его дисциплины из внешней БД в локальную,
    а затем привязывает его к указанной образовательной программе.
    Операции добавления/обновления справочников `d_*` и `spr_*` теперь
    происходят на лету во время клонирования дисциплин.

    Args:
        aup_num (str): Номер АУП для импорта.
        program_id (int): ID образовательной программы, к которой привязывать АУП.
        session (Session): Сессия SQLAlchemy для локальной БД.

    Returns:
        Dict[str, Any]: Результат операции, включая ID импортированного АУП.

    Raises:
        FileNotFoundError: Если АУП не найден во внешней БД.
        ValueError: Если ОП не найдена или другие проблемы с данными.
        RuntimeError: Внутренние ошибки при клонировании.
    """
    logger.info(f"Начало импорта АУП '{aup_num}' для ОП ID {program_id}.")

    program = session.query(EducationalProgram).get(program_id)
    if not program:
        raise ValueError(f"Образовательная программа с ID {program_id} не найдена.")

    existing_local_aup = session.query(LocalAupInfo).filter_by(num_aup=aup_num).first()
    if existing_local_aup:
        existing_link = session.query(EducationalProgramAup).filter_by(
            educational_program_id=program_id,
            aup_id=existing_local_aup.id_aup
        ).first()
        if not existing_link:
            new_link = EducationalProgramAup(educational_program_id=program_id, aup_id=existing_local_aup.id_aup)
            session.add(new_link)
            logger.info(f"Существующий локальный АУП '{aup_num}' привязан к ОП ID {program_id}.")
        else:
            logger.info(f"Связь существующего локального АУП '{aup_num}' с ОП ID {program_id} уже существует.")
        return {"success": True, "message": "АУП уже был импортирован и успешно привязан к программе.", "aup_id": existing_local_aup.id_aup}

    external_engine = get_external_db_engine()
    with Session(external_engine) as external_session:
        external_aup = external_session.query(ExternalAupInfo).options(
            joinedload(ExternalAupInfo.spec).joinedload(ExternalNameOP.okco),
            joinedload(ExternalAupInfo.form), joinedload(ExternalAupInfo.degree),
            joinedload(ExternalAupInfo.faculty), joinedload(ExternalAupInfo.department)
        ).filter_by(num_aup=aup_num).first()
        if not external_aup:
            raise FileNotFoundError(f"АУП с номером '{aup_num}' не найден во внешней базе данных.")

        external_disciplines_query = external_session.query(ExternalAupData).options(
            joinedload(ExternalAupData.spr_discipline),
            joinedload(ExternalAupData.block), joinedload(ExternalAupData.part),
            joinedload(ExternalAupData.module), joinedload(ExternalAupData.type_record_rel),
            joinedload(ExternalAupData.type_control_rel), joinedload(ExternalAupData.ed_izmereniya_rel),
            joinedload(ExternalAupData.group_rel), joinedload(ExternalAupData.period_rel)
        ).filter_by(id_aup=external_aup.id_aup).order_by(
            ExternalAupData.id_period, ExternalAupData.shifr, ExternalAupData.id
        ).all()
        
    try:
        local_faculty = find_or_create_lookup(SprFaculty, {'name_faculty': external_aup.faculty.name_faculty}, {'id_branch': 1}, session) if external_aup.faculty else None
        local_department = find_or_create_lookup(Department, {'name_department': external_aup.department.name_department}, {}, session) if external_aup.department else None
        local_degree = find_or_create_lookup(SprDegreeEducation, {'name_deg': external_aup.degree.name_deg}, {}, session) if external_aup.degree else None
        local_form = find_or_create_lookup(SprFormEducation, {'form': external_aup.form.form}, {}, session) if external_aup.form else None
        
        local_name_op = find_or_create_name_op(
            external_aup.spec.okco.program_code if external_aup.spec and external_aup.spec.okco else None,
            external_aup.spec.name_spec if external_aup.spec else None,
            external_aup.spec.okco.name_okco if external_aup.spec and external_aup.spec.okco else None,
            session
        )
        
        if not all([local_faculty, local_degree, local_form, local_name_op]):
            raise ValueError("Не удалось найти или создать обязательные связанные сущности для AupInfo (факультет, степень, форма, ОП).")

        new_local_aup = LocalAupInfo(
            num_aup=aup_num,
            id_faculty=local_faculty.id_faculty,
            id_degree=local_degree.id_degree,
            id_form=local_form.id_form,
            id_spec=local_name_op.id_spec,
            id_department=local_department.id_department if local_department else None,
            year_beg=external_aup.year_beg,
            year_end=external_aup.year_end,
            qualification=external_aup.qualification,
            type_standard=external_aup.type_standard,
            base=external_aup.base,
            period_educ=external_aup.period_educ,
            years=external_aup.years,
            months=external_aup.months,
            is_actual=external_aup.is_actual,
            is_delete=False, 
            file=f"imported_from_kd_{aup_num}"
        )
        session.add(new_local_aup)
        session.flush()

        cloned_disciplines_count = 0
        for ext_disc_data in external_disciplines_query:
            try:
                local_spr_discipline = find_or_create_lookup(SprDiscipline, {'title': ext_disc_data.discipline}, {'title': ext_disc_data.discipline}, session)
                if not local_spr_discipline:
                    logger.warning(f"Пропуск дисциплины '{ext_disc_data.discipline}' из-за невозможности создать SprDiscipline.")
                    continue

                local_period = find_or_create_lookup(D_Period, {'id': ext_disc_data.id_period}, {'title': ext_disc_data.period_rel.title if ext_disc_data.period_rel else f"Период {ext_disc_data.id_period}"}, session)
                local_type_record = find_or_create_lookup(D_TypeRecord, {'id': ext_disc_data.id_type_record}, {'title': ext_disc_data.type_record_rel.title if ext_disc_data.type_record_rel else f"Тип записи {ext_disc_data.id_type_record}"}, session)
                local_type_control = find_or_create_lookup(D_ControlType, {'id': ext_disc_data.id_type_control}, {'title': ext_disc_data.type_control_rel.title if ext_disc_data.type_control_rel else f"Тип контроля {ext_disc_data.id_type_control}"}, session)
                local_edizm = find_or_create_lookup(D_EdIzmereniya, {'id': ext_disc_data.id_edizm}, {'title': ext_disc_data.ed_izmereniya_rel.title if ext_disc_data.ed_izmereniya_rel else f"Ед. изм. {ext_disc_data.id_edizm}"}, session)
                
                local_block = find_or_create_lookup(D_Blocks, {'id': ext_disc_data.id_block}, {'title': ext_disc_data.block.title if ext_disc_data.block else "Без блока"}, session) if ext_disc_data.id_block else None
                local_part = find_or_create_lookup(D_Part, {'id': ext_disc_data.id_part}, {'title': ext_disc_data.part.title if ext_disc_data.part else "Без части"}, session) if ext_disc_data.id_part else None
                local_module = find_or_create_lookup(D_Modules, {'id': ext_disc_data.id_module}, {'title': ext_disc_data.module.title if ext_disc_data.module else "Без названия", 'color': ext_disc_data.module.color if ext_disc_data.module else "#CCCCCC"}, session) if ext_disc_data.id_module else None
                local_group = find_or_create_lookup(Groups, {'id_group': ext_disc_data.id_group}, {'name_group': ext_disc_data.group_rel.name_group if ext_disc_data.group_rel else "Без названия", 'color': ext_disc_data.group_rel.color if ext_disc_data.group_rel else "#CCCCCC"}, session) if ext_disc_data.id_group else None

                if not all([local_period, local_type_record, local_type_control, local_edizm]):
                    logger.warning(f"Пропуск дисциплины '{ext_disc_data.discipline}' из-за отсутствия обязательных справочников.")
                    continue

                new_local_aup_data = LocalAupData(
                    id_aup=new_local_aup.id_aup,
                    shifr=ext_disc_data.shifr,
                    id_discipline=local_spr_discipline.id,
                    _discipline=ext_disc_data.discipline,
                    id_period=local_period.id,
                    num_row=ext_disc_data.num_row,
                    zet=int((ext_disc_data.zet or 0) * 100),
                    amount=ext_disc_data.amount,
                    used_for_report=ext_disc_data.used_for_report,
                    id_block=local_block.id if local_block else None,
                    id_part=local_part.id if local_part else None,
                    id_module=local_module.id if local_module else None,
                    id_group=local_group.id_group if local_group else None,
                    id_type_record=local_type_record.id,
                    id_type_control=local_type_control.id,
                    id_edizm=local_edizm.id
                )
                session.add(new_local_aup_data)
                cloned_disciplines_count += 1
            except exc.IntegrityError as e_inner_integrity:
                logger.error(f"IntegrityError при клонировании дисциплины '{ext_disc_data.discipline}': {e_inner_integrity.orig.args[1]}", exc_info=True)
                session.rollback()
                raise RuntimeError(f"Ошибка целостности при клонировании дисциплины: {e_inner_integrity.orig.args[1]}")
            except Exception as e_inner:
                logger.error(f"Непредвиденная ошибка при клонировании дисциплины '{ext_disc_data.discipline}': {e_inner}", exc_info=True)
                session.rollback()
                raise RuntimeError(f"Неизвестная ошибка при клонировании дисциплины: {e_inner}")

        link = EducationalProgramAup(educational_program_id=program_id, aup_id=new_local_aup.id_aup)
        session.add(link)

        logger.info(f"Успешно импортирован АУП '{aup_num}' ({cloned_disciplines_count} дисциплин) и привязан к ОП ID {program_id}.")
        return {"success": True, "message": "АУП успешно импортирован.", "aup_id": new_local_aup.id_aup}

    except SQLAlchemyError as e:
        logger.error(f"Ошибка БД при импорте АУП '{aup_num}': {e}", exc_info=True)
        raise RuntimeError(f"Ошибка БД при импорте АУП: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при импорте АУП '{aup_num}': {e}", exc_info=True)
        raise RuntimeError(f"Неизвестная ошибка при импорте АУП: {e}")


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
    """
    Fetches discipline entries (AupData) for a specific AUP from external KD DB.
    Includes titles/names of all related lookup tables.
    """
    engine = get_external_db_engine()
    with Session(engine) as session:
        try:
            query = session.query(ExternalAupData).filter(ExternalAupData.id_aup == aup_id)\
                .order_by(ExternalAupData.id_period, ExternalAupData.shifr, ExternalAupData.id)

            query = query.options(
                joinedload(ExternalAupData.spr_discipline),
                joinedload(ExternalAupData.block),
                joinedload(ExternalAupData.part),
                joinedload(ExternalAupData.module),
                joinedload(ExternalAupData.type_record_rel),
                joinedload(ExternalAupData.type_control_rel),
                joinedload(ExternalAupData.ed_izmereniya_rel),
                joinedload(ExternalAupData.group_rel),
                joinedload(ExternalAupData.period_rel)
            )

            aup_data_entries = query.all()

            result = []
            for entry in aup_data_entries:
                result.append(entry.as_dict())
            return result
        except Exception as e: logger.error(f"Error fetching external AupData for external AUP ID {aup_id}: {e}", exc_info=True); raise