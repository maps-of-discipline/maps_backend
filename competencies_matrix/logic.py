# filepath: competencies_matrix/logic.py
from typing import Dict, List, Any, Optional, Tuple # Добавлено Tuple
import datetime
import traceback
import logging
import json
import re
import io

from flask import current_app
from sqlalchemy import create_engine, select, exists, and_, or_, cast, Integer, text, union_all
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session, aliased, joinedload, selectinload

from maps.models import db as local_db, SprDiscipline
from maps.models import AupInfo as LocalAupInfo, AupData as LocalAupData

from .models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramAup, EducationalProgramPs,
    CompetencyType, IndicatorPsLink,
    GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge,
    CompetencyEducationalProgram
)
from .external_models import (
    ExternalAupInfo, ExternalNameOP, ExternalSprOKCO, ExternalSprFormEducation,
    ExternalSprDegreeEducation, ExternalAupData, ExternalSprDiscipline, ExternalSprFaculty,
    ExternalDepartment
)

from . import fgos_parser
from . import parsers
from . import exports
from . import nlp_logic

from .parsing_utils import parse_date_string


logger = logging.getLogger(__name__)

_external_db_engine = None

def get_external_db_engine():
    """Initializes and returns the engine for the external KD DB."""
    global _external_db_engine
    if _external_db_engine is None:
        db_url = current_app.config.get('EXTERNAL_KD_DATABASE_URL')
        if not db_url: raise RuntimeError("EXTERNAL_KD_DATABASE_URL is not configured.")
        try: _external_db_engine = create_engine(db_url)
        except Exception as e: logger.error(f"Failed to create external DB engine: {e}", exc_info=True); raise RuntimeError(f"Failed to create external DB engine: {e}")
    return _external_db_engine

def search_prof_standards(
    search_query: str,
    ps_ids: Optional[List[int]] = None,
    offset: int = 0,
    limit: int = 50,
    qualification_levels: Optional[List[int]] = None
) -> Dict[str, Any]:
    """(Оптимизированная версия) Ищет в профстандартах, используя полнотекстовый поиск."""
    if not search_query and not qualification_levels and (ps_ids is None or len(ps_ids) == 0):
        raise ValueError("Необходимо указать поисковый запрос, выбрать уровни квалификации или выбрать конкретные профстандарты.")
    
    if search_query and len(search_query) < 2:
        raise ValueError("Поисковый запрос должен содержать минимум 2 символа.")

    session: Session = local_db.session
    
    initial_ps_ids_set: set
    if ps_ids:
        initial_ps_ids_set = set(ps_ids)
    else:
        initial_ps_ids_set = {ps.id for ps in session.query(ProfStandard.id).all()}

    level_filtered_ps_ids: Optional[set] = None
    if qualification_levels:
        level_query = session.query(ProfStandard.id).distinct().join(
            GeneralizedLaborFunction
        ).filter(
            cast(GeneralizedLaborFunction.qualification_level, Integer).in_(qualification_levels)
        )
        level_filtered_ps_ids = {r[0] for r in level_query.all()}
        if not level_filtered_ps_ids:
            return {"total": 0, "items": [], "search_query": search_query}

    text_filtered_ps_ids: Optional[set] = None
    if search_query and len(search_query) >= 2:
        boolean_search_query = ' '.join(f'+{word}*' for word in search_query.split())
        
        ps_ids_from_ps = {r[0] for r in session.query(ProfStandard.id).filter(text("MATCH(name) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}
        ps_ids_from_otf = {r[0] for r in session.query(GeneralizedLaborFunction.prof_standard_id).filter(text("MATCH(name) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}
        ps_ids_from_tf = {r[0] for r in session.query(GeneralizedLaborFunction.prof_standard_id).join(LaborFunction).filter(text("MATCH(competencies_labor_function.name) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}
        ps_ids_from_la = {r[0] for r in session.query(GeneralizedLaborFunction.prof_standard_id).join(LaborFunction).join(LaborAction).filter(text("MATCH(competencies_labor_action.description) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}
        ps_ids_from_rs = {r[0] for r in session.query(GeneralizedLaborFunction.prof_standard_id).join(LaborFunction).join(RequiredSkill).filter(text("MATCH(competencies_required_skill.description) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}
        ps_ids_from_rk = {r[0] for r in session.query(GeneralizedLaborFunction.prof_standard_id).join(LaborFunction).join(RequiredKnowledge).filter(text("MATCH(competencies_required_knowledge.description) AGAINST (:query IN BOOLEAN MODE)").bindparams(query=boolean_search_query)).all()}

        text_filtered_ps_ids = ps_ids_from_ps.union(ps_ids_from_otf, ps_ids_from_tf, ps_ids_from_la, ps_ids_from_rs, ps_ids_from_rk)

        if not text_filtered_ps_ids:
            return {"total": 0, "items": [], "search_query": search_query}

    final_matching_ps_ids: set = initial_ps_ids_set

    if text_filtered_ps_ids is not None:
        final_matching_ps_ids = final_matching_ps_ids.intersection(text_filtered_ps_ids)
    
    if level_filtered_ps_ids is not None:
        final_matching_ps_ids = final_matching_ps_ids.intersection(level_filtered_ps_ids)
    
    if not final_matching_ps_ids:
        return {"total": 0, "items": [], "search_query": search_query}

    final_ps_ids_list = sorted(list(final_matching_ps_ids))
    total_results = len(final_ps_ids_list)
    paginated_ids_to_fetch = final_ps_ids_list[offset : offset + limit]
    
    all_ps_to_process = []
    if paginated_ids_to_fetch:
        base_query = session.query(ProfStandard).options(
            selectinload(ProfStandard.generalized_labor_functions)
                .selectinload(GeneralizedLaborFunction.labor_functions)
                .options(
                    selectinload(LaborFunction.labor_actions),
                    selectinload(LaborFunction.required_skills),
                    selectinload(LaborFunction.required_knowledge)
                )
        )
        paginated_query = base_query.filter(ProfStandard.id.in_(paginated_ids_to_fetch)).order_by(ProfStandard.code)
        all_ps_to_process = paginated_query.all()
    
    all_matching_ps_details = []
    search_query_lower = search_query.lower() if search_query else ""

    for ps in all_ps_to_process:
        ps_details = ps.to_dict(rules=['-generalized_labor_functions'])
        ps_details['name'] = ps.name
        ps_details['code'] = ps.code
        
        filtered_generalized_labor_functions = []
        for otf in ps.generalized_labor_functions:
            if qualification_levels and otf.qualification_level and int(otf.qualification_level) not in qualification_levels:
                continue

            otf_details = otf.to_dict(rules=['-labor_functions'])
            otf_details['name'] = otf.name
            otf_details['code'] = otf.code
            
            otf_details['has_match'] = search_query_lower and search_query_lower in otf.name.lower() or False
            
            filtered_labor_functions = []
            for tf in otf.labor_functions:
                tf_details = tf.to_dict(rules=['-labor_actions', '-required_skills', '-required_knowledge'])
                tf_details['name'] = tf.name
                tf_details['code'] = tf.code
                
                tf_name_matches = search_query_lower and search_query_lower in tf.name.lower() or False
                
                for la in tf.labor_actions: la.has_match = search_query_lower and search_query_lower in la.description.lower() or False
                for rs in tf.required_skills: rs.has_match = search_query_lower and search_query_lower in rs.description.lower() or False
                for rk in tf.required_knowledge: rk.has_match = search_query_lower and search_query_lower in rk.description.lower() or False
                
                tf_has_child_match = any(la.has_match for la in tf.labor_actions) or \
                                   any(rs.has_match for rs in tf.required_skills) or \
                                   any(rk.has_match for rk in tf.required_knowledge)
                                   
                tf_details['has_match'] = tf_name_matches or tf_has_child_match
                
                tf_details['labor_actions'] = [la.to_dict() for la in tf.labor_actions]
                tf_details['required_skills'] = [rs.to_dict() for rs in tf.required_skills]
                tf_details['required_knowledge'] = [rk.to_dict() for rk in tf.required_knowledge]
                filtered_labor_functions.append(tf_details)

            otf_details['labor_functions'] = filtered_labor_functions
            
            filtered_generalized_labor_functions.append(otf_details)

        ps_details['generalized_labor_functions'] = filtered_generalized_labor_functions
        all_matching_ps_details.append(ps_details)

    logger.info(f"Found {total_results} matching PS for query '{search_query}' and levels {qualification_levels} and ps_ids {ps_ids}. Returning {len(all_matching_ps_details)} (offset {offset}, limit {limit}).")
    return {"total": total_results, "items": all_matching_ps_details, "search_query": search_query}

def get_educational_programs_list() -> List[EducationalProgram]:
    """Fetches list of all educational programs."""
    try: return EducationalProgram.query.options(selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup)).order_by(EducationalProgram.title).all()
    except SQLAlchemyError as e: logger.error(f"Database error fetching programs list: {e}"); return []

def get_program_details(program_id: int) -> Optional[Dict[str, Any]]:
    """Fetches detailed information about an educational program."""
    try:
        program = EducationalProgram.query.options(
            selectinload(EducationalProgram.fgos),
            selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
            selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard),
            selectinload(EducationalProgram.competencies_assoc).selectinload(CompetencyEducationalProgram.competency).selectinload(Competency.competency_type)
        ).get(program_id)

        if not program: logger.warning(f"Program with id {program_id} not found."); return None
        
        details = program.to_dict(
            include_fgos=True, include_aup_list=True, include_selected_ps_list=True,
            include_recommended_ps_list=True, include_competencies_list=True
        )
        return details

    except AttributeError as ae: logger.error(f"AttributeError for program_id {program_id}: {ae}", exc_info=True); return None
    except SQLAlchemyError as e: logger.error(f"Database error for program_id {program_id}: {e}", exc_info=True); return None
    except Exception as e: logger.error(f"Unexpected error for program_id {program_id}: {e}", exc_info=True); return None

def create_educational_program(
    data: Dict[str, Any], session: Session
) -> EducationalProgram:
    """
    (ИЗМЕНЕНО)
    Создает новую образовательную программу (ОПОП).
    - Проверяет наличие обязательных полей.
    - Проверяет на дубликаты.
    - Связывает с ФГОС ВО.
    - Связывает с АУП.
    - АВТОМАТИЧЕСКИ СОЗДАЕТ ПУСТУЮ МАТРИЦУ КОМПЕТЕНЦИЙ для связанного АУП.
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
        if not fgos_vo: logger.warning(f"FGOS с ID {data['fgos_id']} не найден.")

    new_program = EducationalProgram(
        title=data['title'], code=data['code'], profile=data.get('profile'),
        qualification=data.get('qualification'), form_of_education=data.get('form_of_education'),
        enrollment_year=data.get('enrollment_year'), fgos=fgos_vo
    )
    session.add(new_program)
    session.flush()

    aup_info = None
    if data.get('num_aup'):
        aup_info = session.query(LocalAupInfo).filter_by(num_aup=data['num_aup']).first()
        if aup_info:
            has_primary_aup = session.query(EducationalProgramAup).filter_by(educational_program_id=new_program.id, is_primary=True).count() > 0
            link = EducationalProgramAup(educational_program_id=new_program.id, aup_id=aup_info.id_aup, is_primary=(not has_primary_aup))
            session.add(link)
            logger.info(f"Связь ОПОП (ID: {new_program.id}) с АУП (ID: {aup_info.id_aup}) создана.")
        else:
            logger.warning(f"АУП с номером '{data['num_aup']}' не найден в локальной БД. Связь с ОПОП не создана.")

    # --- НОВЫЙ БЛОК: Автоматическое создание пустой матрицы ---
    if aup_info and fgos_vo:
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

    session.refresh(new_program)
    return new_program


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


def get_matrix_for_aup(aup_num: str) -> Optional[Dict[str, Any]]:
    """
    Collects all data needed for the competency matrix for a given AUP number.
    Fetches disciplines from external KD DB and competencies/links from local DB.
    """
    logger.info(f"Processing request for AUP num: {aup_num}")
    session: Session = local_db.session
    matrix_response: Dict[str, Any] = {
        "aup_info": None, "disciplines": [], "competencies": [], "links": [],
        "suggestions": [], "external_aup_id": None, "external_aup_num": aup_num,
        "source": "not_found", "error_details": None
    }

    local_aup_info_entry: Optional[LocalAupInfo] = None
    educational_program: Optional[EducationalProgram] = None
    fgos: Optional[FgosVo] = None
    
    try:
        local_aup_info_entry = session.query(LocalAupInfo).options(
            selectinload(LocalAupInfo.educational_program_links)
                .selectinload(EducationalProgramAup.educational_program)
                .selectinload(EducationalProgram.fgos)
        ).filter_by(num_aup=aup_num).first()

        if local_aup_info_entry:
            matrix_response["aup_info"] = local_aup_info_entry.as_dict() if hasattr(local_aup_info_entry, 'as_dict') and callable(local_aup_info_entry.as_dict) else {'id_aup': local_aup_info_entry.id_aup, 'num_aup': local_aup_info_entry.num_aup}
            
            if local_aup_info_entry.educational_program_links:
                primary_assoc = next((assoc for assoc in local_aup_info_entry.educational_program_links if assoc.is_primary), None)
                assoc_to_use = primary_assoc or local_aup_info_entry.educational_program_links[0]
                if assoc_to_use and assoc_to_use.educational_program:
                    educational_program = assoc_to_use.educational_program
                    if educational_program.fgos: fgos = educational_program.fgos
        else: logger.warning(f"LocalAupInfo for num_aup '{aup_num}' not found.")
    except Exception as e_local_aup:
        logger.error(f"Error finding LocalAupInfo for num_aup '{aup_num}': {e_local_aup}", exc_info=True)
        current_error_details = matrix_response.get("error_details", "") or ""
        matrix_response["error_details"] = (current_error_details + f" Error finding local AUP record {aup_num}: {e_local_aup}.")

    external_disciplines: List[Dict[str, Any]] = []
    external_aup_id_for_disciplines: Optional[int] = None
    attempted_external_fetch = False

    try:
        external_aup_search_result = get_external_aups_list(search_query=aup_num, limit=1)
        attempted_external_fetch = True

        if external_aup_search_result["total"] > 0 and external_aup_search_result["items"]:
            exact_match_aup = next((item for item in external_aup_search_result["items"] if item.get('num_aup') == aup_num), None)
            if exact_match_aup:
                external_aup_id_for_disciplines = exact_match_aup.get('id_aup')
                matrix_response["external_aup_id"] = external_aup_id_for_disciplines
                matrix_response["external_aup_num"] = exact_match_aup.get('num_aup', aup_num)
                if not local_aup_info_entry: matrix_response["aup_info"] = exact_match_aup; matrix_response["source"] = "external_header_only"
                
                if external_aup_id_for_disciplines is not None:
                    external_disciplines = get_external_aup_disciplines(external_aup_id_for_disciplines)
                    matrix_response["disciplines"] = external_disciplines
                    if local_aup_info_entry and matrix_response["source"] != "local_fallback_disciplines": matrix_response["source"] = "local_with_external_disciplines"
                    elif not local_aup_info_entry: matrix_response["source"] = "external_only"
                else:
                    error_msg = f" External AUP {aup_num} found, but its ID is missing. Disciplines not loaded."
                    current_error_details = matrix_response.get("error_details", "") or ""
                    matrix_response["error_details"] = (current_error_details + error_msg)
            else:
                error_msg = f" AUP {aup_num} not found (exact match) in external DB. Disciplines not loaded."
                current_error_details = matrix_response.get("error_details", "") or ""
                matrix_response["error_details"] = (current_error_details + error_msg)
        else:
            error_msg = f" AUP {aup_num} not found in external DB. Disciplines not loaded."
            current_error_details = matrix_response.get("error_details", "") or ""
            matrix_response["error_details"] = (current_error_details + error_msg)
    except Exception as e_ext_disciplines:
        attempted_external_fetch = True
        logger.error(f"Error during external KD lookup/discipline fetch for num_aup '{aup_num}': {e_ext_disciplines}", exc_info=True)
        current_error_details = matrix_response.get("error_details", "") or ""
        matrix_response["error_details"] = (current_error_details + f" Error loading disciplines for AUP {aup_num} from external DB: {e_ext_disciplines}.")

    if not external_disciplines and local_aup_info_entry:
        try:
            local_aup_data_entries = session.query(LocalAupData).options(joinedload(LocalAupData.discipline)).filter(LocalAupData.id_aup == local_aup_info_entry.id_aup).order_by(LocalAupData.id_period, LocalAupData.shifr, LocalAupData.id).all()

            if local_aup_data_entries:
                local_disciplines_for_response = []
                for entry in local_aup_data_entries:
                    local_disciplines_for_response.append({
                        'aup_data_id': entry.id, 'id_aup': entry.id_aup, 'discipline_id': entry.id_discipline,
                        'title': entry.discipline.title if entry.discipline else entry._discipline,
                        'semester': entry.id_period, 'shifr': entry.shifr,
                        'id_type_record': entry.id_type_record, 'zet': (entry.zet / 100) if entry.zet is not None else 0,
                        'amount': entry.amount, 'id_type_control': entry.id_type_control
                    })
                matrix_response["disciplines"] = local_disciplines_for_response
                matrix_response["source"] = "local_fallback_disciplines"
                fallback_msg = " Using local discipline data."
                current_error_details = matrix_response.get("error_details", "") or ""
                if current_error_details and attempted_external_fetch: matrix_response["error_details"] += fallback_msg
                else: matrix_response["error_details"] = "Using local discipline data (external could not be loaded or was not requested)."
            else: logger.warning(f"No disciplines found in LOCAL AupData for local AUP ID {local_aup_info_entry.id_aup} either.")
        except Exception as e_local_disc:
            logger.error(f"Error fetching local disciplines for AUP {local_aup_info_entry.id_aup}: {e_local_disc}", exc_info=True)
            current_error_details = matrix_response.get("error_details", "") or ""
            matrix_response["error_details"] = (current_error_details + f" Error loading local disciplines: {e_local_disc}.")

    if local_aup_info_entry:
        if matrix_response["source"] not in ["local_fallback_disciplines", "external_header_only", "external_only"]:
             matrix_response["source"] = "local_only" if not external_disciplines else "local_with_external_disciplines"

        comp_types_q = session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК', 'ПК'])).all()
        comp_types = {ct.code: ct for ct in comp_types_q}
        relevant_competencies = []

        if educational_program and educational_program.fgos:
            fgos_id_to_load = educational_program.fgos.id
            uk_type = comp_types.get('УК'); opk_type = comp_types.get('ОПК')
            uk_opk_ids_to_load = [tid.id for tid in [uk_type, opk_type] if tid]
            if uk_opk_ids_to_load:
                uk_opk_competencies = session.query(Competency).options(
                    selectinload(Competency.indicators),
                    selectinload(Competency.competency_type),
                    selectinload(Competency.fgos) # For source_document_type
                ).filter(Competency.fgos_vo_id == fgos_id_to_load, Competency.competency_type_id.in_(uk_opk_ids_to_load)).all()
                relevant_competencies.extend(uk_opk_competencies)
            else: logger.warning(f"Competency types УК/ОПК not found in DB. Cannot load УК/ОПК for FGOS ID {fgos_id_to_load}.")
        elif educational_program and not educational_program.fgos: logger.warning(f"Educational Program ID {educational_program.id} linked to AUP {aup_num} has no FGOS linked. Skipping УК/ОПК.")
        else: logger.warning(f"No Educational Program linked to local AUP {aup_num}. Skipping УК/ОПК loading.")

        pk_type = comp_types.get('ПК')
        if pk_type:
            pk_competencies = session.query(Competency).options(
                selectinload(Competency.indicators),
                selectinload(Competency.competency_type),
                selectinload(Competency.educational_programs_assoc).selectinload(CompetencyEducationalProgram.educational_program), # For filtering by Educational Program
                selectinload(Competency.based_on_labor_function) # For source_document_type
                    .selectinload(LaborFunction.generalized_labor_function)
                    .selectinload(GeneralizedLaborFunction.prof_standard) # For source_document_type
            ).filter(Competency.competency_type_id == pk_type.id).all()
            
            filtered_pk_competencies = []
            if educational_program:
                for pk_comp in pk_competencies:
                    if any(assoc.educational_program_id == educational_program.id for assoc in pk_comp.educational_programs_assoc):
                        filtered_pk_competencies.append(pk_comp)
                relevant_competencies.extend(filtered_pk_competencies)
            else:
                # If Educational Program is not found or not linked, but PKs exist, display all PKs (as in MVP)
                relevant_competencies.extend(pk_competencies)
        else: logger.warning(f"Competency type ПК not found in DB. Skipping ПК loading.")

        competencies_data = []; all_indicator_ids_for_matrix = set()
        comp_type_id_sort_order = {ct.id: i for i, ct_code in enumerate(['УК', 'ОПК', 'ПК']) for ct in comp_types_q if ct.code == ct_code}
        relevant_competencies.sort(key=lambda c: (comp_type_id_sort_order.get(c.competency_type_id, 999), c.code))

        for comp in relevant_competencies:
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"
            comp_dict = comp.to_dict(rules=['-indicators', '-competency_type', '-fgos', '-based_on_labor_function', '-matrix_entries', '-educational_programs_assoc'])
            comp_dict['type_code'] = type_code;
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
                    comp_dict['source_document_type'] = "Ручной ввод" # PK created manually, without TF/PS link
                    comp_dict['source_document_code'] = "N/A"
                    comp_dict['source_document_name'] = "Введено вручную"


            if comp.based_on_labor_function: # Still include this for form pre-fill
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
        matrix_response["competencies"] = competencies_data

        if matrix_response["disciplines"] and all_indicator_ids_for_matrix:
            discipline_source_aup_data_ids = [d['aup_data_id'] for d in matrix_response["disciplines"] if d.get('aup_data_id') is not None]
            if discipline_source_aup_data_ids:
                existing_links_db = session.query(CompetencyMatrix).filter(
                    CompetencyMatrix.aup_data_id.in_(discipline_source_aup_data_ids),
                    CompetencyMatrix.indicator_id.in_(list(all_indicator_ids_for_matrix))
                ).all()
                matrix_response["links"] = [link.to_dict(only=('aup_data_id', 'indicator_id', 'is_manual')) for link in existing_links_db]
            else: logger.debug("No valid aup_data_ids from disciplines to load links for.")
        else: logger.debug("No disciplines loaded or no indicators for matrix, local links will be empty.")
    
    if not local_aup_info_entry and not matrix_response["disciplines"] and matrix_response["source"] != "external_header_only":
        matrix_response["source"] = "not_found"
        logger.error(f"AUP with num_aup '{aup_num}' not found in local DB. External search also failed or yielded no disciplines.")
        current_error_details = matrix_response.get("error_details", "") or ""
        if not current_error_details: matrix_response["error_details"] = f"AUP {aup_num} not found in local or external DB, or disciplines could not be loaded."
        if not matrix_response.get("aup_info") and not matrix_response.get("disciplines"): return None

    return matrix_response

def update_matrix_link(aup_data_id: int, indicator_id: int, create: bool = True) -> Dict[str, Any]:
    """Creates or deletes a Discipline(AUP)-Indicator link in the matrix."""
    session: Session = local_db.session
    try:
        indicator_exists = session.query(exists().where(Indicator.id == indicator_id)).scalar()
        if not indicator_exists:
            message = f"Indicator with id {indicator_id} not found in local DB."
            logger.warning(message); return { 'success': False, 'status': 'error', 'message': message, 'error_type': 'indicator_not_found' }
        
        existing_link = session.query(CompetencyMatrix).filter_by(aup_data_id=aup_data_id, indicator_id=indicator_id).first()

        if create:
            if not existing_link:
                link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
                session.add(link); logger.info(f"Link created: External AupData ID {aup_data_id} <-> Indicator {indicator_id}")
                session.commit() # Added commit
                return { 'success': True, 'status': 'created', 'message': "Link created." }
            else:
                if not existing_link.is_manual:
                     existing_link.is_manual = True
                     session.add(existing_link); logger.info(f"Link updated to manual: External AupData ID {aup_data_id} <-> Indicator {indicator_id}")
                     session.commit() # Added commit
                return { 'success': True, 'status': 'already_exists', 'message': "Link already exists." }
        else:  # delete
            if existing_link:
                session.delete(existing_link); logger.info(f"Link deleted: External AupData ID {aup_data_id} <-> Indicator {indicator_id}")
                session.commit() # Added commit
                return { 'success': True, 'status': 'deleted', 'message': "Link deleted." }
            else:
                logger.warning(f"Link not found for deletion: External AupData ID {aup_data_id} <-> Indicator {indicator_id}")
                return { 'success': True, 'status': 'not_found', 'message': "Link not found." }

    except SQLAlchemyError as e:
        session.rollback() # Added rollback
        logger.error(f"Database error updating matrix link: {e}", exc_info=True); raise
    except Exception as e:
        session.rollback() # Added rollback
        logger.error(f"Unexpected error updating matrix link: {e}", exc_info=True); raise

def get_all_competencies() -> List[Dict[str, Any]]:
    try:
        # Eagerly load related models to avoid N+1 queries
        competencies = local_db.session.query(Competency).options(
            joinedload(Competency.competency_type),
            joinedload(Competency.fgos), # For УК/ОПК source
            joinedload(Competency.based_on_labor_function) # For ПК source
                .joinedload(LaborFunction.generalized_labor_function)
                .joinedload(GeneralizedLaborFunction.prof_standard)
        ).all()
        result = []
        for comp in competencies:
            comp_dict = comp.to_dict(rules=['-indicators', '-fgos', '-based_on_labor_function', '-matrix_entries', '-educational_programs_assoc'])
            comp_dict['type_code'] = comp.competency_type.code if comp.competency_type else "UNKNOWN"
            
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
                    comp_dict['source_document_type'] = "Ручной ввод" # PK created manually, without TF/PS link
                    comp_dict['source_document_code'] = "N/A"
                    comp_dict['source_document_name'] = "Введено вручную"


            if comp.based_on_labor_function: # Still include this for form pre-fill
                 comp_dict['based_on_labor_function_id'] = comp.based_on_labor_function.id
                 comp_dict['based_on_labor_function_code'] = comp.based_on_labor_function.code
                 comp_dict['based_on_labor_function_name'] = comp.based_on_labor_function.name
            result.append(comp_dict)
        return result
    except Exception as e: logger.error(f"Error fetching all competencies with source info: {e}", exc_info=True); raise

def get_competency_details(comp_id: int) -> Optional[Dict[str, Any]]:
    try:
        competency = local_db.session.query(Competency).options(
            joinedload(Competency.competency_type),
            joinedload(Competency.indicators)
        ).get(comp_id)
        if not competency: logger.warning(f"Competency with id {comp_id} not found."); return None
        result = competency.to_dict(rules=['-fgos', '-based_on_labor_function'], include_indicators=True, include_type=True, include_educational_programs=True)
        if competency.based_on_labor_function:
            result['based_on_labor_function_id'] = competency.based_on_labor_function.id
            result['based_on_labor_function_code'] = competency.based_on_labor_function.code
            result['based_on_labor_function_name'] = competency.based_on_labor_function.name
        return result
    except Exception as e: logger.error(f"Error fetching competency {comp_id} details: {e}", exc_info=True); raise

def create_competency(data: Dict[str, Any], session: Session) -> Optional[Competency]:
    required_fields = ['type_code', 'code', 'name']
    if not all(field in data and data[field] is not None and str(data[field]).strip() for field in required_fields):
        raise ValueError("Отсутствуют обязательные поля: type_code, code, name.")
    if data['type_code'] != 'ПК': raise ValueError(f"Данный эндпоинт предназначен только для создания ПК. Получен тип '{data['type_code']}'.")

    educational_program_ids = data.get('educational_program_ids', [])
    if not isinstance(educational_program_ids, list):
         logger.warning(f"'educational_program_ids' is not a list. Ignoring or handling as error.")
         educational_program_ids = []
    
    based_on_labor_function_id = data.get('based_on_labor_function_id')
    
    try:
        comp_type = session.query(CompetencyType).filter_by(code=data['type_code']).first()
        if not comp_type: raise ValueError(f"Тип компетенции с кодом '{data['type_code']}' не найден.")
        
        existing_comp = session.query(Competency).filter_by(code=str(data['code']).strip(), competency_type_id=comp_type.id).first()
        if existing_comp: raise IntegrityError(f"Competency with code {data['code']} already exists for this type.", {}, None)
        
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
            based_on_labor_function_id=based_on_labor_function_id
        )
        session.add(competency); session.flush()

        for ep_id in educational_program_ids:
            educational_program = session.query(EducationalProgram).get(ep_id)
            if educational_program:
                 assoc = CompetencyEducationalProgram(competency_id=competency.id, educational_program_id=ep_id)
                 session.add(assoc)
            else: logger.warning(f"Educational Program with ID {ep_id} not found. Skipping link for competency {competency.id}.")

        session.flush(); return competency
    except IntegrityError as e: logger.error(f"Database IntegrityError creating competency: {e}", exc_info=True); raise e
    except SQLAlchemyError as e: logger.error(f"Database error creating competency: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error creating competency: {e}", exc_info=True); raise e

def update_competency(comp_id: int, data: Dict[str, Any], session: Session) -> Optional[Dict[str, Any]]:
    if not data: raise ValueError("Отсутствуют данные для обновления.")
    educational_program_ids = data.get('educational_program_ids')
    try:
        competency = session.query(Competency).get(comp_id)
        if not competency: return None
        
        allowed_fields = {'name', 'description'}
        updated = False
        
        for field in data:
            if field in allowed_fields:
                 processed_value = str(data[field]).strip() if data[field] is not None else None
                 if field == 'description' and processed_value == '': processed_value = None
                 
                 if getattr(competency, field) != processed_value:
                     setattr(competency, field, processed_value)
                     updated = True
            elif field == 'educational_program_ids': # Allow this field, but handle it separately
                pass
            else: logger.warning(f"Ignoring field '{field}' for update of comp {comp_id} as it is not allowed via this endpoint.")
        
        if educational_program_ids is not None: # Check if key exists, even if value is empty list
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
                    ).delete(synchronize_session='fetch'); updated = True
                
                to_add_ids = new_ep_ids - current_ep_ids
                if to_add_ids:
                    for ep_id in to_add_ids:
                        educational_program = session.query(EducationalProgram).get(ep_id)
                        if educational_program:
                            assoc = CompetencyEducationalProgram(competency_id=competency.id, educational_program_id=ep_id)
                            session.add(assoc); updated = True
                        else: logger.warning(f"Educational Program with ID {ep_id} not found when adding link for competency {comp_id}. Skipping.")
                if to_delete_ids or to_add_ids: session.flush() # Flush if associations changed
        
        if updated:
            session.add(competency) # Add competency again if its own fields or associations changed
            session.flush()
        
        session.refresh(competency) # Refresh to get latest data including associations
        return competency.to_dict(rules=['-indicators', '-fgos', '-based_on_labor_function'], include_type=True, include_educational_programs=True)

    except IntegrityError as e: logger.error(f"Database IntegrityError updating competency {comp_id}: {e}", exc_info=True); raise e
    except SQLAlchemyError as e: logger.error(f"Database error updating competency {comp_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error updating competency {comp_id}: {e}", exc_info=True); raise e

def delete_competency(comp_id: int, session: Session) -> bool:
    try:
         comp_to_delete = session.query(Competency).get(comp_id)
         if not comp_to_delete: logger.warning(f"Competency {comp_id} not found for deletion."); return False
         
         session.delete(comp_to_delete)
         return True
    except SQLAlchemyError as e: logger.error(f"Database error deleting competency {comp_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error deleting competency {comp_id}: {e}", exc_info=True); raise e

def get_all_indicators() -> List[Dict[str, Any]]:
    try:
        indicators = local_db.session.query(Indicator).options(joinedload(Indicator.competency)).all()
        result = []
        for ind in indicators:
             ind_dict = ind.to_dict(rules=['-labor_functions', '-matrix_entries'])
             if ind.competency: ind_dict['competency_code'] = ind.competency.code; ind_dict['competency_name'] = ind.competency.name
             result.append(ind_dict)
        return result
    except Exception as e: logger.error(f"Error fetching all indicators: {e}", exc_info=True); raise

def get_indicator_details(ind_id: int) -> Optional[Dict[str, Any]]:
    try:
        indicator = local_db.session.query(Indicator).options(joinedload(Indicator.competency)).get(ind_id)
        if not indicator: logger.warning(f"Indicator with id {ind_id} not found."); return None
        result = indicator.to_dict(rules=['-competency', '-labor_functions', '-matrix_entries'])
        if indicator.competency: result['competency_code'] = indicator.competency.code; result['competency_name'] = indicator.competency.name
        return result
    except Exception as e: logger.error(f"Error fetching indicator {ind_id} details: {e}", exc_info=True); raise

def create_indicator(data: Dict[str, Any], session: Session) -> Optional[Indicator]:
    required_fields = ['competency_id', 'code', 'formulation']
    if not all(field in data and data[field] is not None and str(data[field]).strip() for field in required_fields):
        raise ValueError("Отсутствуют обязательные поля: competency_id, code, formulation.")
    try:
        competency = session.query(Competency).get(data['competency_id'])
        if not competency: raise ValueError(f"Родительская компетенция с ID '{data['competency_id']}' не найдена.")
        
        selected_ps_elements_ids = data.get('selected_ps_elements_ids')
        if selected_ps_elements_ids is not None and not isinstance(selected_ps_elements_ids, dict):
            logger.warning(f"Invalid format for selected_ps_elements_ids: {type(selected_ps_elements_ids)}. Must be a dict. Ignoring.")
            selected_ps_elements_ids = None # Or default to empty dict
        elif selected_ps_elements_ids is None: # Explicitly default to empty dict if None
            selected_ps_elements_ids = {} # For consistency

        # Проверяем, есть ли индикатор с таким же кодом для данной компетенции
        existing_indicator = session.query(Indicator).filter_by(code=str(data['code']).strip(), competency_id=data['competency_id']).first()
        if existing_indicator:
            raise IntegrityError(f"Индикатор с кодом '{data['code']}' уже существует для компетенции '{competency.code}'.", {}, None)

        indicator = Indicator(
            competency_id=data['competency_id'], code=str(data['code']).strip(), formulation=str(data['formulation']).strip(),
            source=str(data['source']).strip() if data.get('source') is not None else None,
            selected_ps_elements_ids=selected_ps_elements_ids
        )
        session.add(indicator); session.flush(); return indicator
    except IntegrityError as e: logger.error(f"Database IntegrityError creating indicator: {e}", exc_info=True); raise e
    except SQLAlchemyError as e: logger.error(f"Database error creating indicator: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error creating indicator: {e}", exc_info=True); raise e

def update_indicator(ind_id: int, data: Dict[str, Any], session: Session) -> Optional[Indicator]:
    if not data: raise ValueError("Отсутствуют данные для обновления.")
    try:
        indicator = session.query(Indicator).get(ind_id)
        if not indicator: return None
        
        allowed_fields = {'code', 'formulation', 'source', 'selected_ps_elements_ids'}
        updated = False
        
        for field in data:
            if field in allowed_fields:
                 processed_value = str(data[field]).strip() if data[field] is not None and field != 'selected_ps_elements_ids' else data[field]
                 if field == 'source' and processed_value == '': processed_value = None
                 
                 if field == 'code' and processed_value != indicator.code:
                      existing_with_new_code = session.query(Indicator).filter_by(
                           code=processed_value, competency_id=indicator.competency_id
                      ).first()
                      if existing_with_new_code and existing_with_new_code.id != indicator.id:
                           raise IntegrityError(f"Indicator with code {processed_value} already exists for competency {indicator.competency_id}.", {}, None)
                 
                 if field == 'selected_ps_elements_ids':
                     if data[field] is not None and not isinstance(data[field], dict): # Allow None
                         logger.warning(f"Invalid format for selected_ps_elements_ids received for indicator {ind_id}: {type(data[field])}. Must be a dict or None. Skipping update for this field.")
                         continue
                     # Check if content of dict changed
                     if indicator.selected_ps_elements_ids != data[field]:
                         indicator.selected_ps_elements_ids = data[field]
                         updated = True
                 elif getattr(indicator, field) != processed_value:
                     setattr(indicator, field, processed_value)
                     updated = True
            else: logger.warning(f"Ignoring field '{field}' for update of ind {ind_id} as it is not allowed via this endpoint.")
        
        if updated:
            session.add(indicator); session.flush()
        
        session.refresh(indicator); return indicator

    except IntegrityError as e: logger.error(f"Database IntegrityError updating indicator {ind_id}: {e}", exc_info=True); raise e
    except SQLAlchemyError as e: logger.error(f"Database error updating indicator {ind_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error updating indicator {ind_id}: {e}", exc_info=True); raise e

def delete_indicator(ind_id: int, session: Session) -> bool:
    try:
         ind_to_delete = session.query(Indicator).get(ind_id)
         if not ind_to_delete: logger.warning(f"Indicator {ind_id} not found for deletion."); return False
         
         session.delete(ind_to_delete)
         return True
    except SQLAlchemyError as e: logger.error(f"Database error deleting indicator {ind_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error deleting indicator {ind_id}: {e}", exc_info=True); raise e

def parse_fgos_file(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    try:
        text_content = fgos_parser.extract_text(io.BytesIO(file_bytes)) # ИЗМЕНЕНИЕ: Используем pdfminer напрямую
        parsed_data = nlp_logic.parse_fgos_with_gemini(text_content) # ИЗМЕНЕНИЕ: Вызываем nlp_logic.py
        if not parsed_data or not parsed_data.get('metadata'):
             logger.warning(f"Parsing failed or returned insufficient metadata for {filename}")
             if not parsed_data: raise ValueError("Parser returned empty data.")
             if not parsed_data.get('metadata'): raise ValueError("Failed to extract metadata from FGOS file.")
        return parsed_data
    except ValueError as e: logger.error(f"Parser ValueError for {filename}: {e}"); raise e
    except Exception as e: logger.error(f"Unexpected error parsing {filename}: {e}", exc_info=True); raise Exception(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")

def save_fgos_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[FgosVo]:
    if not parsed_data or not parsed_data.get('metadata'):
        logger.warning("No parsed data or metadata provided for saving."); return None
    
    metadata = parsed_data.get('metadata', {})
    fgos_number = metadata.get('order_number')
    fgos_date_str = metadata.get('order_date')

    fgos_date_obj = None
    if isinstance(fgos_date_str, str):
        fgos_date_obj = parse_date_string(fgos_date_str)
    elif isinstance(fgos_date_str, datetime.datetime):
        fgos_date_obj = fgos_date_str.date()
    elif isinstance(fgos_date_str, datetime.date):
        fgos_date_obj = fgos_date_str

    fgos_direction_code = metadata.get('direction_code')
    fgos_education_level = metadata.get('education_level')
    fgos_generation_raw = metadata.get('generation')
    
    fgos_generation = str(fgos_generation_raw).strip() if fgos_generation_raw is not None else ''
    # Костыль
    if not fgos_generation or fgos_generation.lower() == 'null': # ИЗМЕНЕНИЕ: Добавлена проверка на 'null'
        fgos_generation = '3++'
        logger.warning(f"FGOS generation was missing, empty or 'null' for '{filename}'. Defaulting to '{fgos_generation}'.")
    else:
        fgos_generation = str(fgos_generation)

    fgos_direction_name = metadata.get('direction_name')

    if not fgos_date_obj:
        logger.error(f"FGOS date '{fgos_date_str}' from parsed data could not be converted to a datetime.date object. Cannot save.")
        raise ValueError(f"FGOS date '{fgos_date_str}' is not in expected date format (YYYY-MM-DD) or invalid after re-parsing.")

    if not all((fgos_number, fgos_direction_code, fgos_education_level)):
        logger.error("Missing core metadata from parsed data for saving (number, direction_code, or education_level).")
        raise ValueError("Missing core FGOS metadata from parsed data for saving.")

    recommended_ps_raw_data = parsed_data.get('recommended_ps', [])
    if not isinstance(recommended_ps_raw_data, list) or \
       not all(isinstance(item, dict) for item in recommended_ps_raw_data):
        logger.warning("Parsed recommended_ps data is not a list of dictionaries. Skipping raw data storage.")
        recommended_ps_raw_data = []
    
    clean_recommended_ps_for_json = []
    for ps_item in recommended_ps_raw_data:
        clean_item = ps_item.copy()
        if 'approval_date' in clean_item and isinstance(clean_item['approval_date'], datetime.date):
            clean_item['approval_date'] = clean_item['approval_date'].isoformat()
        clean_recommended_ps_for_json.append(clean_item)

    try:
        existing_fgos = session.query(FgosVo).filter(
            FgosVo.direction_code == fgos_direction_code,
            FgosVo.education_level == fgos_education_level,
            FgosVo.number == fgos_number,
            FgosVo.date == fgos_date_obj
        ).first()
        
        fgos_vo = None
        if existing_fgos:
            if force_update:
                logger.info(f"Existing FGOS found ({existing_fgos.id}). Force update. Deleting old comps/links...")
                session.query(Competency).filter_by(fgos_vo_id=existing_fgos.id).delete(synchronize_session='fetch')
                session.query(FgosRecommendedPs).filter_by(fgos_vo_id=existing_fgos.id).delete(synchronize_session='fetch')
                session.flush()

                fgos_vo = existing_fgos
                fgos_vo.direction_name = fgos_direction_name or 'Not specified'
                fgos_vo.generation = fgos_generation
                fgos_vo.file_path = filename
                fgos_vo.recommended_ps_parsed_data = clean_recommended_ps_for_json
                session.add(fgos_vo)
                session.flush()
            else:
                logger.warning(f"FGOS with same key data already exists ({existing_fgos.id}). Skipping save.")
                raise IntegrityError("ФГОС с этим направлением, номером и датой уже существует.", {}, None)
        else:
            fgos_vo = FgosVo(
                number=fgos_number, date=fgos_date_obj, direction_code=fgos_direction_code,
                direction_name=fgos_direction_name or 'Not specified', education_level=fgos_education_level,
                generation=fgos_generation, file_path=filename,
                recommended_ps_parsed_data=clean_recommended_ps_for_json
            )
            session.add(fgos_vo)
            session.flush() # Flush to get fgos_vo.id

        comp_types_map = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
        if not comp_types_map.get('УК') or not comp_types_map.get('ОПК'): # Check specifically for УК and ОПК
            logger.error("CompetencyType (УК, ОПК) not found. Cannot save competencies.")
            raise ValueError("CompetencyType (УК, ОПК) not found. Please seed initial competency types.")
        
        saved_competencies_count = 0
        all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])
        
        for parsed_comp in all_parsed_competencies:
            comp_code = parsed_comp.get('code')
            comp_name = parsed_comp.get('name')
            comp_category_name = parsed_comp.get('category_name')
            
            if not comp_code or not comp_name:
                logger.warning(f"Skipping competency due to missing code/name: {parsed_comp}"); continue
            
            comp_prefix = comp_code.split('-')[0].upper()
            comp_type = comp_types_map.get(comp_prefix)
            
            if not comp_type:
                logger.warning(f"Skipping competency {comp_code}: Competency type {comp_prefix} not found (must be УК or ОПК)."); continue
            
            existing_comp_for_fgos = session.query(Competency).filter_by(
                code=comp_code, competency_type_id=comp_type.id, fgos_vo_id=fgos_vo.id
            ).first()
            if existing_comp_for_fgos: # This check might be redundant if force_update already deleted them
                logger.warning(f"Competency {comp_code} already exists for FGOS {fgos_vo.id}. Skipping."); continue
            
            competency = Competency(
                competency_type_id=comp_type.id,
                fgos_vo_id=fgos_vo.id,
                code=comp_code,
                name=comp_name,
                category_name=comp_category_name
            )
            session.add(competency)
            session.flush() # Flush to get competency ID for potential indicators (if any were parsed)
            saved_competencies_count += 1
        
        logger.info(f"Saved {saved_competencies_count} competencies for FGOS {fgos_vo.id}.")
        
        if len(recommended_ps_raw_data) > 0:
             ps_codes_to_find = [ps_data['code'] for ps_data in recommended_ps_raw_data if ps_data.get('code')]
             existing_prof_standards = session.query(ProfStandard).filter(ProfStandard.code.in_(ps_codes_to_find)).all()
             ps_by_code = {ps.code: ps for ps in existing_prof_standards}
             
             linked_ps_count = 0
             for ps_data in recommended_ps_raw_data:
                ps_code = ps_data.get('code')
                ps_name_from_doc = ps_data.get('name')
                
                if not ps_code: continue
                
                prof_standard = ps_by_code.get(ps_code)
                # Link creation logic was here, ensure it's correct with force_update
                # If force_update, old FgosRecommendedPs were deleted. So, we always create new ones.
                # If not force_update and FGOS is new, we create new ones.
                # The check for existing_link is effectively handled by the earlier deletion if force_update.
                # If not force_update and FGOS already existed, this function would have raised IntegrityError.

                # We always try to add the link if the PS exists in the DB.
                # If the link already exists (e.g. not force_update, but somehow this part is reached for an existing FGOS),
                # we might want to update its description.
                # However, the current structure with force_update deleting old links simplifies this: just add.

                if prof_standard:
                    # Check if link already exists (e.g. if not force_update and this part is somehow reached)
                    # This check is more relevant if we weren't systematically deleting on force_update
                    existing_link = session.query(FgosRecommendedPs).filter_by(
                        fgos_vo_id=fgos_vo.id, 
                        prof_standard_id=prof_standard.id
                    ).first()

                    if not existing_link:
                        link = FgosRecommendedPs(
                            fgos_vo_id=fgos_vo.id,
                            prof_standard_id=prof_standard.id,
                            is_mandatory=False, # Default, or parse from doc if available
                            description=ps_name_from_doc
                        )
                        session.add(link)
                        linked_ps_count += 1
                    elif existing_link.description != ps_name_from_doc : # If link exists, update description if different
                        existing_link.description = ps_name_from_doc
                        session.add(existing_link)
                        # Not incrementing linked_ps_count as it's an update
                else:
                    logger.warning(f"Recommended PS with code {ps_code} (name: {ps_name_from_doc}) not found in DB. Skipping link in FgosRecommendedPs for FGOS {fgos_vo.id}.")
             if linked_ps_count > 0:
                logger.info(f"Queued {linked_ps_count} new recommended PS links for FGOS {fgos_vo.id}.")
        
        return fgos_vo
    except IntegrityError as e:
        logger.error(f"Integrity error for FGOS from '{filename}': {e}", exc_info=True)
        session.rollback()
        raise e
    except SQLAlchemyError as e:
        logger.error(f"Database error for FGOS from '{filename}': {e}", exc_info=True)
        session.rollback()
        raise e
    except Exception as e:
        logger.error(f"Unexpected error saving FGOS: {e}", exc_info=True)
        session.rollback()
        raise e

def get_fgos_list() -> List[FgosVo]:
    try: return local_db.session.query(FgosVo).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()
    except SQLAlchemyError as e: logger.error(f"Database error fetching FGOS list: {e}", exc_info=True); return []
    except Exception as e: logger.error(f"Unexpected error fetching FGOS list: {e}", exc_info=True); return []

def get_fgos_details(fgos_id: int) -> Optional[Dict[str, Any]]:
    try:
        session: Session = local_db.session
        fgos = session.query(FgosVo).options(
            selectinload(FgosVo.competencies).selectinload(Competency.indicators),
            selectinload(FgosVo.competencies).selectinload(Competency.competency_type),
            selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard)
        ).get(fgos_id)
        if not fgos: logger.warning(f"FGOS with id {fgos_id} not found."); return None
        
        details = fgos.to_dict(rules=['-competencies', '-recommended_ps_assoc', '-educational_programs'])
        
        # Process competencies (UK/OPK)
        uk_competencies_data = []; opk_competencies_data = []
        # Efficiently get type codes without another query if possible, or ensure Competency.competency_type is loaded
        # The selectinload already loads Competency.competency_type
        
        # Sort competencies by type (УК then ОПК) and then by code
        def sort_key_competency(c):
            type_code_order = {'УК': 1, 'ОПК': 2}.get(c.competency_type.code if c.competency_type else 'ZZZ', 99)
            return (type_code_order, c.code)

        sorted_competencies = sorted(fgos.competencies, key=sort_key_competency)

        for comp in sorted_competencies:
            if comp.competency_type and comp.competency_type.code in ['УК', 'ОПК']:
                 comp_dict = comp.to_dict(rules=['-fgos', '-based_on_labor_function', '-indicators', '-competency_type', '-matrix_entries', '-educational_programs_assoc'])
                 comp_dict['type_code'] = comp.competency_type.code
                 comp_dict['indicators'] = []
                 if comp.indicators:
                     # Sort indicators by code
                     sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                     comp_dict['indicators'] = [ind.to_dict(rules=['-competency', '-labor_functions', '-matrix_entries']) for ind in sorted_indicators]
                 
                 if comp.competency_type.code == 'УК': uk_competencies_data.append(comp_dict)
                 elif comp.competency_type.code == 'ОПК': opk_competencies_data.append(comp_dict)
        details['uk_competencies'] = uk_competencies_data; details['opk_competencies'] = opk_competencies_data
        
        recommended_ps_info_for_display = []
        # Use fgos.recommended_ps_parsed_data as the source of truth for what was in the document
        parsed_recommended_ps_from_doc = fgos.recommended_ps_parsed_data
        
        if parsed_recommended_ps_from_doc and isinstance(parsed_recommended_ps_from_doc, list):
            # Create a map of loaded PS from the associations for quick lookup
            loaded_ps_map = {assoc.prof_standard.code: assoc.prof_standard
                             for assoc in fgos.recommended_ps_assoc if assoc.prof_standard}
 
            for ps_data_from_doc in parsed_recommended_ps_from_doc:
                ps_code = ps_data_from_doc.get('code')
                if not ps_code: continue # Skip if no code in parsed data
 
                loaded_ps = loaded_ps_map.get(ps_code) # Check if this PS code is linked and loaded
                
                # Get approval_date from parsed data, ensure it's stringified if it's a date object
                approval_date_from_doc = ps_data_from_doc.get('approval_date')
                if isinstance(approval_date_from_doc, datetime.date):
                    approval_date_str = approval_date_from_doc.isoformat()
                elif isinstance(approval_date_from_doc, str):
                     # Validate or parse if it's a string but not ISO format
                    try:
                        datetime.date.fromisoformat(approval_date_from_doc)
                        approval_date_str = approval_date_from_doc
                    except ValueError:
                        parsed_date = parse_date_string(approval_date_from_doc) # Your existing helper
                        approval_date_str = parsed_date.isoformat() if parsed_date else None
                else:
                    approval_date_str = None


                item_to_add = {
                    'id': loaded_ps.id if loaded_ps else None, # ID of the ProfStandard in DB
                    'code': ps_code,
                    'name': loaded_ps.name if loaded_ps else ps_data_from_doc.get('name'), # Use DB name if loaded, else parsed name
                    'is_loaded': bool(loaded_ps), # True if this PS is in our DB and linked
                    'approval_date': approval_date_str # Date from the FGOS document
                }
                recommended_ps_info_for_display.append(item_to_add)
            
            # Sort the final list, e.g., by code
            recommended_ps_info_for_display.sort(key=lambda x: x['code'])
        
        details['recommended_ps'] = recommended_ps_info_for_display
        return details
    except SQLAlchemyError as e: logger.error(f"Database error fetching FGOS {fgos_id} details: {e}", exc_info=True); return None
    except Exception as e: logger.error(f"Unexpected error fetching FGOS {fgos_id} details: {e}", exc_info=True); return None

def delete_fgos(fgos_id: int, session: Session, delete_related_competencies: bool = False) -> bool:
    try:
         fgos_to_delete = session.query(FgosVo).get(fgos_id)
         if not fgos_to_delete: logger.warning(f"FGOS with id {fgos_id} not found for deletion."); return False
         
         # Cascading deletes for FgosRecommendedPs and Competencies (UK/OPK type for this FGOS)
         # are handled by SQLAlchemy if relationships are configured with cascade="all, delete-orphan".
         # No explicit deletion of related competencies or recommended PS links is needed here if so.
         # The `delete_related_competencies` flag becomes somewhat moot if cascade is correctly set up for competencies.
         # If it's meant to be a safeguard or for relationships without cascade, then explicit deletes would be needed.
         # Assuming cascade="all, delete-orphan" is on FgosVo.competencies and FgosVo.recommended_ps_assoc.

         if delete_related_competencies:
             logger.info(f"FGOS {fgos_id} will be deleted. Related competencies (if cascade is set) and recommended PS links will also be deleted.")
             # If cascade is not set for Competency but desired:
             # session.query(Competency).filter(Competency.fgos_vo_id == fgos_id).delete(synchronize_session='fetch')
         # else:
             # If competencies should NOT be deleted when FGOS is deleted (and cascade is on),
             # this would be more complex, potentially nullifying fgos_vo_id on competencies.
             # But typically, FGOS-specific competencies (UK/OPK) are deleted with the FGOS.

         session.delete(fgos_to_delete)
         return True
    except SQLAlchemyError as e: logger.error(f"Database error deleting FGOS {fgos_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error deleting FGOS {fgos_id}: {e}", exc_info=True); raise e

def handle_prof_standard_upload_parsing(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Handles the parsing of a PS file after upload. Calls the appropriate parser orchestrator."""
    return parsers.parse_prof_standard(file_bytes, filename)


def save_prof_standard_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[ProfStandard]:
    """Saves the parsed professional standard data (including structure) to the database."""
    ps_code = parsed_data.get('code'); ps_name = parsed_data.get('name'); generalized_labor_functions_data = parsed_data.get('generalized_labor_functions', [])
    if not ps_code or not ps_name: raise ValueError("Неполные данные ПС для сохранения: отсутствует код или название.")
    if not isinstance(generalized_labor_functions_data, list): raise ValueError("Неверный формат данных структуры ПС.")

    order_date_obj = parse_date_string(parsed_data.get('order_date')) if isinstance(parsed_data.get('order_date'), str) else parsed_data.get('order_date')
    if order_date_obj is None and parsed_data.get('order_date') is not None: logger.warning(f"Could not parse order_date '{parsed_data.get('order_date')}' to datetime.date object.")

    registration_date_obj = parse_date_string(parsed_data.get('registration_date')) if isinstance(parsed_data.get('registration_date'), str) else parsed_data.get('registration_date')
    if registration_date_obj is None and parsed_data.get('registration_date') is not None: logger.warning(f"Could not parse registration_date '{parsed_data.get('registration_date')}' to datetime.date object.")

    try:
        existing_ps = session.query(ProfStandard).filter_by(code=ps_code).first()
        current_ps = None

        if existing_ps:
            if force_update:
                logger.info(f"Existing PS found ({existing_ps.id}). Force update. Deleting old structure and updating metadata...")
                # Cascade delete for OTFs (and their children) should be handled by SQLAlchemy
                # if ProfStandard.generalized_labor_functions relationship has cascade="all, delete-orphan".
                # If not, explicit deletion is needed:
                # otfs_to_delete = session.query(GeneralizedLaborFunction).filter_by(prof_standard_id=existing_ps.id).all()
                # for otf in otfs_to_delete:
                #     # Manually delete children of OTF if cascade not set there either
                #     session.delete(otf)
                # For simplicity, assuming cascade="all, delete-orphan" on ProfStandard.generalized_labor_functions
                session.query(GeneralizedLaborFunction).filter_by(prof_standard_id=existing_ps.id).delete(synchronize_session='fetch') # Explicit delete if cascade not reliable or for clarity
                session.flush()

                existing_ps.name = ps_name
                existing_ps.order_number = parsed_data.get('order_number')
                existing_ps.order_date = order_date_obj
                existing_ps.registration_number = parsed_data.get('registration_number')
                existing_ps.registration_date = registration_date_obj
                existing_ps.activity_area_name = parsed_data.get('activity_area_name')
                existing_ps.activity_purpose = parsed_data.get('activity_purpose')
                # existing_ps.file_path = filename # Consider if file_path should be updated

                session.add(existing_ps); current_ps = existing_ps
            else: raise IntegrityError(f"Профессиональный стандарт с кодом {ps_code} уже существует.", {}, None)
        else:
            current_ps = ProfStandard(
                code=ps_code, name=ps_name, order_number=parsed_data.get('order_number'), order_date=order_date_obj,
                registration_number=parsed_data.get('registration_number'), registration_date=registration_date_obj,
                activity_area_name=parsed_data.get('activity_area_name'), activity_purpose=parsed_data.get('activity_purpose')
                # file_path=filename # Consider if file_path should be set
            )
            session.add(current_ps); session.flush() # Flush to get current_ps.id

        for otf_data in generalized_labor_functions_data:
            otf_code = otf_data.get('code'); otf_name = otf_data.get('name'); otf_level = otf_data.get('qualification_level'); tf_list_data = otf_data.get('labor_functions', [])

            if not otf_code or not otf_name or not isinstance(tf_list_data, list):
                logger.warning(f"Skipping OTF due to missing data or invalid TF list: code={otf_code}"); continue

            new_otf = GeneralizedLaborFunction(prof_standard_id=current_ps.id, code=otf_code, name=otf_name, qualification_level=str(otf_level) if otf_level is not None else None)
            session.add(new_otf); session.flush() # Flush to get new_otf.id

            for tf_data in tf_list_data:
                tf_code = tf_data.get('code'); tf_name = tf_data.get('name'); tf_level = tf_data.get('qualification_level') # This might be string or int
                la_list_data = tf_data.get('labor_actions', []); rs_list_data = tf_data.get('required_skills', []); rk_list_data = tf_data.get('required_knowledge', [])

                if not tf_code or not tf_name or not isinstance(la_list_data, list) or \
                   not isinstance(rs_list_data, list) or not isinstance(rk_list_data, list):
                   logger.warning(f"Skipping TF under OTF {otf_code} due to missing data or invalid sub-lists: code={tf_code}"); continue

                new_tf = LaborFunction(generalized_labor_function_id=new_otf.id, code=tf_code, name=tf_name, qualification_level=str(tf_level) if tf_level is not None else None)
                session.add(new_tf); session.flush() # Flush to get new_tf.id

                for i, la_data in enumerate(la_list_data):
                     la_description = la_data.get('description') if isinstance(la_data, dict) else str(la_data) # Handle if la_data is just a string
                     la_order = la_data.get('order', i) if isinstance(la_data, dict) else i
                     if la_description: session.add(LaborAction(labor_function_id=new_tf.id, description=str(la_description).strip(), order=la_order))

                for i, rs_data in enumerate(rs_list_data):
                     rs_description = rs_data.get('description') if isinstance(rs_data, dict) else str(rs_data)
                     rs_order = rs_data.get('order', i) if isinstance(rs_data, dict) else i
                     if rs_description: session.add(RequiredSkill(labor_function_id=new_tf.id, description=str(rs_description).strip(), order=rs_order))
                                
                for i, rk_data in enumerate(rk_list_data):
                     rk_description = rk_data.get('description') if isinstance(rk_data, dict) else str(rk_data)
                     rk_order = rk_data.get('order', i) if isinstance(rk_data, dict) else i
                     if rk_description: session.add(RequiredKnowledge(labor_function_id=new_tf.id, description=str(rk_description).strip(), order=rk_order))
        session.flush() # Final flush for all sub-elements
        return current_ps

    except IntegrityError as e: logger.error(f"Integrity error saving PS '{ps_code}': {e}", exc_info=True); session.rollback(); raise
    except SQLAlchemyError as e: logger.error(f"Database error saving PS '{ps_code}': {e}", exc_info=True); session.rollback(); raise
    except Exception as e: logger.error(f"Unexpected error saving PS '{ps_code}': {e}", exc_info=True); session.rollback(); raise

def get_prof_standards_list() -> List[Dict[str, Any]]:
    """
    Fetches list of all professional standards, including information about
    which FGOS recommends them. Merges actual loaded PS with placeholders from FGOS recommendations.
    Returns a list of dictionaries for direct JSON serialization.
    """
    try:
        session = local_db.session
        
        # Fetch all loaded Professional Standards with their FGOS associations
        saved_prof_standards_db = session.query(ProfStandard).options(
            selectinload(ProfStandard.fgos_assoc).selectinload(FgosRecommendedPs.fgos)
        ).all()
        
        # Fetch all FGOS to get their parsed recommended PS data
        all_fgos = session.query(FgosVo).all()
        
        combined_ps_data: Dict[str, Dict[str, Any]] = {}

        # Populate with loaded ProfStandards
        for ps in saved_prof_standards_db:
            ps_dict = ps.to_dict(rules=['-fgos_assoc', '-generalized_labor_functions', '-educational_program_assoc'])
            ps_dict['is_loaded'] = True
            ps_dict['recommended_by_fgos'] = [] # Initialize list for FGOS recommendations
            
            # Populate `recommended_by_fgos` from actual DB links
            if ps.fgos_assoc:
                for assoc in ps.fgos_assoc:
                    if assoc.fgos:
                        fgos_info = {
                            'id': assoc.fgos.id,
                            'code': assoc.fgos.direction_code,
                            'name': assoc.fgos.direction_name,
                            'generation': assoc.fgos.generation,
                            'number': assoc.fgos.number,
                            'date': assoc.fgos.date.isoformat() if assoc.fgos.date else None,
                        }
                        ps_dict['recommended_by_fgos'].append(fgos_info)
            combined_ps_data[ps.code] = ps_dict

        # Add/update with placeholders and recommendations from FGOS parsed data
        for fgos in all_fgos:
            parsed_recommended_ps = fgos.recommended_ps_parsed_data
            if parsed_recommended_ps and isinstance(parsed_recommended_ps, list):
                for ps_item_from_fgos_doc in parsed_recommended_ps:
                    ps_code = ps_item_from_fgos_doc.get('code')
                    if not ps_code: continue

                    fgos_recommendation_info = {
                        'id': fgos.id,
                        'code': fgos.direction_code,
                        'name': fgos.direction_name,
                        'generation': fgos.generation,
                        'number': fgos.number,
                        'date': fgos.date.isoformat() if fgos.date else None,
                    }
                    
                    approval_date_from_doc = ps_item_from_fgos_doc.get('approval_date')
                    if isinstance(approval_date_from_doc, datetime.date):
                        approval_date_str = approval_date_from_doc.isoformat()
                    elif isinstance(approval_date_from_doc, str):
                         # Validate or parse if it's a string but not ISO format
                        try:
                            datetime.date.fromisoformat(approval_date_from_doc)
                            approval_date_str = approval_date_from_doc
                        except ValueError:
                            parsed_date = parse_date_string(approval_date_from_doc) # Your existing helper
                            approval_date_str = parsed_date.isoformat() if parsed_date else None
                    else:
                        approval_date_str = None


                    if ps_code not in combined_ps_data:
                        # This PS is recommended by an FGOS but not loaded in our DB yet (placeholder)
                        combined_ps_data[ps_code] = {
                            'id': None, # No DB ID for this PS
                            'code': ps_code,
                            'name': ps_item_from_fgos_doc.get('name'), # Name from FGOS doc
                            'order_number': None, # Placeholder, actual PS not loaded
                            'order_date': approval_date_str, # Date from FGOS doc (often approval date of PS)
                            'registration_number': None,
                            'registration_date': None,
                            'is_loaded': False,
                            'recommended_by_fgos': [fgos_recommendation_info] # Starts with current FGOS
                        }
                    else:
                        # PS is loaded, add this FGOS to its recommendation list if not already present from DB link
                        # Check based on FGOS ID to avoid duplicates if parsed data and DB links overlap
                        current_recommendations = combined_ps_data[ps_code]['recommended_by_fgos']
                        if not any(rec['id'] == fgos.id for rec in current_recommendations):
                            current_recommendations.append(fgos_recommendation_info)
        
        # Sort `recommended_by_fgos` lists for consistency
        for ps_data_item in combined_ps_data.values():
            ps_data_item['recommended_by_fgos'].sort(key=lambda x: (x['code'] or "", x.get('date', "") or ""))

        # Convert dict to list and sort the final list of PS, e.g., by code
        result = sorted(list(combined_ps_data.values()), key=lambda x: x['code'])
        return result
        
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching ProfStandards list: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching ProfStandards list: {e}", exc_info=True)
        return []

def get_prof_standard_details(ps_id: int) -> Optional[Dict[str, Any]]:
    try:
        session: Session = local_db.session
        ps = session.query(ProfStandard).options(
            selectinload(ProfStandard.generalized_labor_functions).selectinload(GeneralizedLaborFunction.labor_functions).options(
                selectinload(LaborFunction.labor_actions),
                selectinload(LaborFunction.required_skills),
                selectinload(LaborFunction.required_knowledge)
            )
        ).get(ps_id) # Corrected this line
        if not ps: logger.warning(f"PS with ID {ps_id} not found."); return None
        
        details = ps.to_dict(rules=['-generalized_labor_functions', '-fgos_assoc', '-educational_program_assoc'])
        
        otf_list = []
        if ps.generalized_labor_functions:
            # Sort OTFs by code
            sorted_otfs = sorted(ps.generalized_labor_functions, key=lambda otf_item: otf_item.code or "")
            for otf_item in sorted_otfs:
                otf_dict = otf_item.to_dict(rules=['-prof_standard', '-labor_functions'])
                otf_dict['labor_functions'] = []
                if otf_item.labor_functions:
                    # Sort TFs by code
                    sorted_tfs = sorted(otf_item.labor_functions, key=lambda tf_item: tf_item.code or "")
                    for tf_item in sorted_tfs:
                        tf_dict = tf_item.to_dict(rules=['-generalized_labor_function', '-labor_actions', '-required_skills', '-required_knowledge', '-indicators', '-competencies'])
                        # Sort LA, RS, RK by their 'order' attribute
                        tf_dict['labor_actions'] = sorted([la.to_dict() for la in tf_item.labor_actions], key=lambda x: x.get('order', float('inf')))
                        tf_dict['required_skills'] = sorted([rs.to_dict() for rs in tf_item.required_skills], key=lambda x: x.get('order', float('inf')))
                        tf_dict['required_knowledge'] = sorted([rk.to_dict() for rk in tf_item.required_knowledge], key=lambda x: x.get('order', float('inf')))
                        otf_dict['labor_functions'].append(tf_dict)
                otf_list.append(otf_dict)
        details['generalized_labor_functions'] = otf_list
        
        return details
    except SQLAlchemyError as e: logger.error(f"Database error fetching PS {ps_id} details: {e}", exc_info=True); return None
    except Exception as e: logger.error(f"Unexpected error fetching PS {ps_id} details: {e}", exc_info=True); return None

def delete_prof_standard(ps_id: int, session: Session) -> bool:
    try:
         ps_to_delete = session.query(ProfStandard).get(ps_id)
         if not ps_to_delete: logger.warning(f"ProfStandard {ps_id} not found for deletion."); return False
         
         session.delete(ps_to_delete)
         return True
    except SQLAlchemyError as e: logger.error(f"Database error deleting PS {ps_id}: {e}", exc_info=True); raise e
    except Exception as e: logger.error(f"Unexpected error deleting PS {ps_id}: {e}", exc_info=True); raise e

def generate_prof_standard_excel_export_logic(selected_data: Dict[str, Any], opop_id: Optional[int]) -> bytes:
    """
    Готовит данные и вызывает функцию генерации Excel.
    """
    if not selected_data or not selected_data.get('profStandards'):
        raise ValueError("Нет данных для экспорта.")

    # Получаем данные об ОП для заголовка
    opop_data = {'direction_code': '', 'direction_name': '', 'profile_name': ''}
    if opop_id:
        program = EducationalProgram.query.get(opop_id)
        if program:
            opop_data['direction_code'] = program.code
            opop_data['direction_name'] = program.title # Или другое поле, если есть
            opop_data['profile_name'] = program.profile
    
    try:
        excel_bytes = exports.generate_tf_list_excel_export(selected_data, opop_data)
        return excel_bytes
    except Exception as e:
        logger.error(f"Error generating Excel export for TF list: {e}", exc_info=True)
        raise RuntimeError(f"Не удалось сгенерировать Excel-файл: {e}")

# --- НОВАЯ ФУНКЦИЯ ---
from pdfminer.high_level import extract_text # Импортируем здесь для PDF-парсинга

def process_uk_indicators_disposition_file(file_bytes: bytes, filename: str, education_level: str) -> Dict[str, Any]:
    """
    (ИЗМЕНЕНО)
    Обрабатывает PDF-файл распоряжения.
    Принимает education_level для фильтрации запроса к NLP и поиска ФГОС.
    """
    logger.info(f"Processing UK indicators disposition file: {filename} for education level: {education_level}")
    
    try:
        # ИЗМЕНЕНИЕ: Передаем education_level в NLP парсер
        text_content = extract_text(io.BytesIO(file_bytes))
        parsed_disposition_data = nlp_logic.parse_uk_indicators_disposition_with_gemini(text_content, education_level=education_level)

        if not parsed_disposition_data or not parsed_disposition_data.get('disposition_metadata'):
            raise ValueError("Не удалось извлечь метаданные из файла распоряжения.")

        result: Dict[str, Any] = {
            "disposition_metadata": parsed_disposition_data['disposition_metadata'],
            "filename": filename,
            "parsed_uk_competencies": parsed_disposition_data.get('uk_competencies_with_indicators', []),
            "applicable_fgos": [],
            "existing_uk_data_for_diff": {}
        }

        session = local_db.session
        # ИЗМЕНЕНИЕ: Ищем ФГОСы ТОЛЬКО по переданному education_level
        fgos_query = session.query(FgosVo).filter(
            FgosVo.education_level == education_level
        ).order_by(FgosVo.date.desc())
        
        all_fgos_records_for_level = fgos_query.all()
        
        if not all_fgos_records_for_level:
            logger.warning(f"No FGOS found in DB for education_level='{education_level}'.")
            result["fgos_not_found_warnings"] = [f"Не найдены ФГОСы для уровня образования '{education_level}'. Убедитесь, что соответствующие ФГОС ВО загружены."]
            return result # Возвращаем, но без applicable_fgos, чтобы фронтенд мог показать сообщение

        result["applicable_fgos"] = [fgos.to_dict() for fgos in all_fgos_records_for_level]

        # Сбор существующих УК/ИУК для сравнения (diff) для каждого ФГОС
        uk_type = session.query(CompetencyType).filter_by(code='УК').first()
        if not uk_type:
            logger.warning("CompetencyType 'УК' not found. Cannot perform diff.")
            return result

        # ИСПРАВЛЕНО: Использование корректной переменной all_fgos_records_for_level
        for fgos_record in all_fgos_records_for_level:
            existing_uk_competencies = session.query(Competency).options(
                selectinload(Competency.indicators)
            ).filter(
                Competency.fgos_vo_id == fgos_record.id,
                Competency.competency_type_id == uk_type.id
            ).all()

            uk_data_for_this_fgos = {}
            for uk_comp in existing_uk_competencies:
                uk_comp_dict = uk_comp.to_dict(rules=['-indicators']) # Base dict for UK
                uk_comp_dict['indicators'] = {ind.code: ind.to_dict() for ind in uk_comp.indicators} # Indicators by code
                uk_data_for_this_fgos[uk_comp.code] = uk_comp_dict # Store by UK code
            
            result["existing_uk_data_for_diff"][fgos_record.id] = uk_data_for_this_fgos

        logger.info(f"Found {len(all_fgos_records_for_level)} FGOS records for education_level='{education_level}'.")
        return result

    except ValueError as e:
        logger.error(f"Data validation or parsing error for disposition {filename}: {e}", exc_info=True)
        raise ValueError(f"Ошибка парсинга распоряжения: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке файла распоряжения: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при обработке файла распоряжения: {e}")

def save_uk_indicators_from_disposition(
    parsed_disposition_data: Dict[str, Any],
    filename: str,
    session: Session,
    fgos_ids: List[int], # ИЗМЕНЕНИЕ: Принимаем список ID
    force_update_uk: bool = False,
    resolutions: Optional[Dict[str, str]] = None # Для будущих разрешений конфликтов
) -> Dict[str, Any]:
    """
    (ИЗМЕНЕНО)
    Сохраняет/обновляет индикаторы УК из распоряжения, применяя их к каждому ФГОС из списка fgos_ids.
    """
    if resolutions is None:
        resolutions = {}

    logger.info(f"Saving UK indicators from disposition file: {filename} for FGOS IDs: {fgos_ids}. Force update UK: {force_update_uk}")
    
    summary = {
        "saved_uk": 0, "updated_uk": 0, "skipped_uk": 0,
        "saved_indicator": 0, "updated_indicator": 0, "skipped_indicator": 0
    }

    try:
        # Проверяем, что все ФГОСы существуют
        fgos_records = session.query(FgosVo).filter(FgosVo.id.in_(fgos_ids)).all()
        if len(fgos_records) != len(fgos_ids):
            found_ids = {r.id for r in fgos_records}
            missing_ids = set(fgos_ids) - found_ids
            raise ValueError(f"Один или несколько ФГОС ВО не найдены в БД: ID={list(missing_ids)}.")

        uk_type = session.query(CompetencyType).filter_by(code='УК').first()
        if not uk_type:
            raise ValueError("Тип компетенции 'УК' не найден в БД. Пожалуйста, инициализируйте справочники.")
        
        disposition_meta = parsed_disposition_data.get('disposition_metadata', {})
        source_string = f"Распоряжение №{disposition_meta.get('number', 'N/A')} от {disposition_meta.get('date', 'N/A')}"

        # --- Основной цикл по каждому выбранному ФГОСу ---
        for fgos_vo in fgos_records:
            logger.info(f"Processing FGOS ID: {fgos_vo.id} ({fgos_vo.direction_code})")
            
            # Если перезаписываем, сначала удаляем старые УК для этого ФГОСа
            if force_update_uk:
                logger.info(f"Force update is ON for FGOS {fgos_vo.id}. Deleting existing UKs.")
                session.query(Competency).filter(
                    Competency.fgos_vo_id == fgos_vo.id,
                    Competency.competency_type_id == uk_type.id
                ).delete(synchronize_session='fetch')
                session.flush()

            for parsed_uk_data in parsed_disposition_data.get('uk_competencies_with_indicators', []):
                uk_code = parsed_uk_data.get('code')
                uk_name = parsed_uk_data.get('name')
                uk_category_name = parsed_uk_data.get('category_name')

                if not uk_code or not uk_name:
                    logger.warning(f"Skipping parsed UK due to missing code/name for FGOS {fgos_vo.id}.")
                    summary['skipped_uk'] += 1
                    continue
                
                # Ищем УК только в контексте текущего ФГОСа
                existing_uk_comp = session.query(Competency).filter_by(
                    code=uk_code,
                    competency_type_id=uk_type.id,
                    fgos_vo_id=fgos_vo.id
                ).first()

                current_uk_comp: Optional[Competency] = None

                if existing_uk_comp:
                    # Если есть, обновляем название
                    if existing_uk_comp.name != uk_name:
                        existing_uk_comp.name = uk_name
                        existing_uk_comp.category_name = uk_category_name # Update category name too
                        session.add(existing_uk_comp)
                        summary['updated_uk'] += 1
                    else:
                        summary['skipped_uk'] += 1
                    current_uk_comp = existing_uk_comp
                else:
                    # Если нет, создаем новую УК для этого ФГОСа
                    current_uk_comp = Competency(
                        competency_type_id=uk_type.id,
                        fgos_vo_id=fgos_vo.id,
                        code=uk_code,
                        name=uk_name,
                        category_name=uk_category_name
                    )
                    session.add(current_uk_comp)
                    summary['saved_uk'] += 1
                
                session.flush()

                # --- Сохранение Индикаторов для этой УК и этого ФГОСа ---
                for parsed_indicator_data in parsed_uk_data.get('indicators', []):
                    indicator_code = parsed_indicator_data.get('code')
                    indicator_formulation = parsed_indicator_data.get('formulation')

                    if not indicator_code or not indicator_formulation:
                        summary['skipped_indicator'] += 1
                        continue
                    
                    existing_indicator = session.query(Indicator).filter_by(
                        code=indicator_code,
                        competency_id=current_uk_comp.id
                    ).first()

                    if existing_indicator:
                        if existing_indicator.formulation != indicator_formulation:
                            existing_indicator.formulation = indicator_formulation
                            existing_indicator.source = source_string
                            session.add(existing_indicator)
                            summary['updated_indicator'] += 1
                        else:
                            summary['skipped_indicator'] += 1
                    else:
                        new_indicator = Indicator(
                            competency_id=current_uk_comp.id,
                            code=indicator_code,
                            formulation=indicator_formulation,
                            source=source_string
                        )
                        session.add(new_indicator)
                        summary['saved_indicator'] += 1
        
        return {"success": True, "message": "Индикаторы УК успешно обработаны.", "summary": summary}
    except Exception as e:
        logger.error(f"Error saving UK indicators from disposition: {e}", exc_info=True)
        session.rollback()
        raise e

# НОВАЯ ФУНКЦИЯ
def handle_pk_name_correction(raw_phrase: str) -> Dict[str, str]:
    """
    Обрабатывает запрос на коррекцию имени ПК с использованием NLP.
    """
    if not raw_phrase or not isinstance(raw_phrase, str):
        raise ValueError("Некорректная сырая фраза для коррекции.")
    
    try:
        corrected_name = nlp_logic.correct_pk_name_with_gemini(raw_phrase)
        return corrected_name
    except RuntimeError as e:
        logger.error(f"NLP correction failed: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка NLP при коррекции названия ПК: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in handle_pk_name_correction: {e}", exc_info=True)
        raise RuntimeError(f"Неизвестная ошибка при коррекции названия ПК: {e}")

# НОВАЯ ФУНКЦИЯ
def handle_pk_ipk_generation(
    selected_tfs_data: List[Dict],
    selected_zun_elements: Dict[str, List[Dict]]
) -> Dict[str, Any]:
    """
    Обрабатывает запрос на генерацию ПК и ИПК с использованием NLP.
    """
    if not selected_tfs_data and not selected_zun_elements:
        raise ValueError("Необходимо выбрать Трудовые Функции или их элементы для генерации.")
    
    try:
        generated_data = nlp_logic.generate_pk_ipk_with_gemini(selected_tfs_data, selected_zun_elements)
        return generated_data
    except RuntimeError as e:
        logger.error(f"NLP generation failed: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка NLP при генерации ПК/ИПК: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in handle_pk_ipk_generation: {e}", exc_info=True)
        raise RuntimeError(f"Неизвестная ошибка при генерации ПК/ИПК: {e}")

def batch_create_pk_and_ipk(data_list: List[Dict[str, Any]], session: Session) -> Dict:
    created_count = 0
    errors = []
    for item_data in data_list:
        try:
            # Логика из create_competency
            pk_payload = {
                'code': item_data.get('pk_code'),
                'name': item_data.get('pk_name'),
                'type_code': 'ПК',
                'based_on_labor_function_id': item_data.get('tf_id')
            }
            new_pk = create_competency(pk_payload, session)
            session.flush() # Получаем ID для new_pk

            # Логика из create_indicator
            formulation = f"Знает: {item_data.get('ipk_znaet')}\\nУмеет: {item_data.get('ipk_umeet')}\\nВладеет: {item_data.get('ipk_vladeet')}"
            ipk_payload = {
                'competency_id': new_pk.id,
                'code': f"ИПК-{new_pk.code.replace('ПК-', '')}.1",
                'formulation': formulation,
                'source': f"ПС {item_data.get('ps_code')}"
            }
            create_indicator(ipk_payload, session)
            created_count += 1
        except Exception as e:
            errors.append({'pk_code': item_data.get('pk_code'), 'error': str(e)})

    if errors:
        # Если были ошибки, можно откатить всю транзакцию или вернуть частичный результат
        raise Exception(f"Завершено с ошибками. Успешно: {created_count}, Ошибки: {len(errors)}. Подробности: {errors}")

    return {"success_count": created_count, "error_count": len(errors), "errors": errors}