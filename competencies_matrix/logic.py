# competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
from sqlalchemy.orm import joinedload, selectinload, Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import exists, and_
import traceback
from .fgos_parser import parse_fgos_pdf

from maps.models import db, AupData, SprDiscipline, AupInfo
from .models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramAup, EducationalProgramPs,
    CompetencyType, IndicatorPsLink
)

import logging
# Настройка логирования
logger = logging.getLogger(__name__)
# Уровень логирования устанавливается при старте приложения или в конфиге

# --- Функции для получения данных для отображения ---

def get_educational_programs_list() -> List[EducationalProgram]:
    """
    Получает список всех образовательных программ из БД.

    Returns:
        List[EducationalProgram]: Список объектов SQLAlchemy EducationalProgram.
    """
    try:
        # Используем joinedload для предзагрузки первого AUP
        # Это может ускорить отображение списка, если первый_aup_id используется на фронте
        programs = EducationalProgram.query.options(
             joinedload(EducationalProgram.aup_assoc).joinedload(EducationalProgramAup.aup)
        ).order_by(EducationalProgram.title).all()
        return programs
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_educational_programs_list: {e}")
        return [] # Возвращаем пустой список в случае ошибки

def get_program_details(program_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает детальную информацию по ОП, включая связанные сущности.

    Args:
        program_id: ID образовательной программы.

    Returns:
        Optional[Dict[str, Any]]: Словарь с данными программы или None, если не найдена.
                                   Структура должна включать детали ФГОС, список АУП,
                                   список выбранных и рекомендованных ПС.
    """
    try:
        program = EducationalProgram.query.options(
            # Эффективно загружаем связанные данные одним запросом
            selectinload(EducationalProgram.fgos),
            selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
            selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard)
        ).get(program_id)

        if not program:
            logger.warning(f"Program with id {program_id} not found for details.")
            return None

        # Сериализуем программу основные поля без связей
        details = {
            'id': program.id,
            'title': program.title,
            'code': program.code,
            'profile': program.profile,
            'qualification': program.qualification,
            'form_of_education': program.form_of_education,
            'enrollment_year': program.enrollment_year,
            'fgos_vo_id': program.fgos_vo_id,
            'created_at': program.created_at.isoformat() if program.created_at else None, # Форматируем дату
            'updated_at': program.updated_at.isoformat() if program.updated_at else None  # Форматируем дату
        }

        # Добавляем детали в нужном формате
        if program.fgos:
            details['fgos_details'] = {
                'id': program.fgos.id,
                'number': program.fgos.number,
                'date': program.fgos.date.isoformat() if program.fgos.date else None, # Форматируем дату
                'direction_code': program.fgos.direction_code,
                'direction_name': program.fgos.direction_name,
                'education_level': program.fgos.education_level,
                'generation': program.fgos.generation,
                'file_path': program.fgos.file_path
            }
        else:
            details['fgos_details'] = None
            
        details['aup_list'] = []
        if program.aup_assoc:
            details['aup_list'] = [
                {
                    'id_aup': assoc.aup.id_aup,
                    'num_aup': assoc.aup.num_aup,
                    'file': assoc.aup.file
                } 
                for assoc in program.aup_assoc if assoc.aup
            ]
        
        details['selected_ps_list'] = []
        if program.selected_ps_assoc:
            details['selected_ps_list'] = [
                {
                    'id': assoc.prof_standard.id,
                    'code': assoc.prof_standard.code,
                    'name': assoc.prof_standard.name
                }
                for assoc in program.selected_ps_assoc if assoc.prof_standard
            ]

        # Получаем рекомендованные ПС для связанного ФГОС
        recommended_ps_list = []
        if program.fgos and program.fgos.recommended_ps_assoc:
            if program.fgos.recommended_ps_assoc:
                # Бережно обрабатываем каждую связь, извлекая только нужные поля
                for assoc in program.fgos.recommended_ps_assoc:
                    if assoc.prof_standard:
                        recommended_ps_list.append({
                            'id': assoc.prof_standard.id,
                            'code': assoc.prof_standard.code,
                            'name': assoc.prof_standard.name
                        })
                    
        details['recommended_ps_list'] = recommended_ps_list

        return details
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_program_details for program_id {program_id}: {e}")
        return None
    except AttributeError as e: # Может быть при неполноте данных (например, AUP_assoc, но AUP==None)
        logger.error(f"Attribute error likely due to missing relationship/data in get_program_details for program_id {program_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_program_details for program_id {program_id}: {e}", exc_info=True)
        return None

def get_matrix_for_aup(aup_id: int) -> Optional[Dict[str, Any]]:
    """
    Собирает все данные для отображения матрицы компетенций для АУП.
    (Версия с исправлениями сортировки, фильтрации УК/ОПК и ПК)

    Args:
        aup_id: ID Академического учебного плана (из таблицы tbl_aup).

    Returns:
        Словарь с данными для фронтенда или None.
    """
    try:
        session: Session = db.session

        # 1. Получаем инфо об АУП и связанные ОП
        aup_info = session.query(AupInfo).options(
            selectinload(AupInfo.education_programs_assoc).selectinload(EducationalProgramAup.educational_program)
        ).get(aup_id)

        if not aup_info:
            logger.warning(f"AUP with id {aup_id} not found for matrix.")
            return None

        # 2. Находим связанную ОП и ФГОС
        program = None
        fgos = None
        if aup_info.education_programs_assoc:
             # Предполагаем, что AUP связан только с одной ОП в контексте матрицы
             program = aup_info.education_programs_assoc[0].educational_program
             if program and program.fgos_vo_id:
                  fgos = session.query(FgosVo).get(program.fgos_vo_id)

        if not program:
             logger.warning(f"AUP {aup_id} is not linked to any Educational Program.")
             return None

        logger.info(f"Found Program (id: {program.id}, title: {program.title}) for AUP {aup_id}.")
        if fgos:
             logger.info(f"Found linked FGOS (id: {fgos.id}, code: {fgos.direction_code}).")
        else:
             logger.warning(f"Educational Program {program.id} is not linked to any FGOS.")


        # 3. Получаем дисциплины АУП из AupData
        aup_data_entries = session.query(AupData).options(
            joinedload(AupData.discipline)
        ).filter_by(id_aup=aup_id).order_by(AupData.id_period, AupData.num_row).all()

        disciplines_list = []
        aup_data_ids_in_matrix = set()
        for entry in aup_data_entries:
            if entry.id_discipline is None:
                continue
            discipline_title = entry.discipline.title if entry.discipline else f"Discipline ID:{entry.id_discipline} (Not in Spr)"
            discipline_data = {
                "aup_data_id": entry.id,
                "discipline_id": entry.id_discipline,
                "title": discipline_title,
                "semester": entry.id_period
            }
            disciplines_list.append(discipline_data)
            aup_data_ids_in_matrix.add(entry.id)

        # Сортировка списка дисциплин уже сделана ORM
        # disciplines_list.sort(key=lambda d: (d.get('semester', 0), d.get('title', '')))
        logger.info(f"Found {len(disciplines_list)} AupData entries for AUP {aup_id}.")

        # 4. Получаем релевантные компетенции и их индикаторы
        # УК и ОПК берутся из ФГОС, связанного с ОП
        # ПК берутся из тех, что созданы пользователем (или связаны с ОП косвенно через ПС)
        # На данном этапе (MVP) берем ВСЕ ПК
        
        relevant_competencies_query = session.query(Competency).options(
            selectinload(Competency.indicators),
            joinedload(Competency.competency_type)
        )

        relevant_competencies = []

        # Получаем УК и ОПК, связанные с данным ФГОС (если ФГОС есть)
        if fgos:
            uk_opk_competencies = relevant_competencies_query.filter(
                Competency.fgos_vo_id == fgos.id
                # Проверка типа через join CompetencyType добавлена в .all() фильтрацию
            ).all() # Query.all() вернет все объекты, фильтруем по типу в Python
            
            # Фильтруем по типу 'УК' или 'ОПК' после загрузки
            uk_opk_competencies = [
                 c for c in uk_opk_competencies 
                 if c.competency_type and c.competency_type.code in ['УК', 'ОПК']
            ]
            relevant_competencies.extend(uk_opk_competencies)
            logger.info(f"Found {len(uk_opk_competencies)} УК/ОПК competencies linked to FGOS {fgos.id}.")
        else:
             logger.warning("No FGOS linked to program, cannot retrieve УК/ОПК from FGOS.")


        # Получаем ВСЕ ПК, т.к. логика связи ПК с ОП еще не полностью реализована (Issue #2.5)
        # TODO: Реализовать фильтрацию ПК по ОП (например, через выбранные ПС для ОП)
        pk_competencies = relevant_competencies_query.join(CompetencyType).filter(CompetencyType.code == 'ПК').all()
        relevant_competencies.extend(pk_competencies)
        logger.info(f"Found {len(pk_competencies)} ПК competencies (all existing ПК).")


        # Форматируем результат
        competencies_data = []
        indicator_ids_in_matrix = set()
        
        # Сортируем релевантные компетенции перед форматированием
        relevant_competencies.sort(key=lambda c: (c.competency_type.code if c.competency_type else '', c.code))

        for comp in relevant_competencies:
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"

            comp_dict = comp.to_dict(rules=['-indicators', '-competency_type', '-fgos', '-based_on_labor_function', '-matrix_links'])
            comp_dict['type_code'] = type_code
            comp_dict['indicators'] = []
            if comp.indicators:
                # Сортируем индикаторы внутри компетенции
                sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                for ind in sorted_indicators:
                    indicator_ids_in_matrix.add(ind.id)
                    comp_dict['indicators'].append(
                        ind.to_dict(only=('id', 'code', 'formulation', 'source'))
                    )
            competencies_data.append(comp_dict)

        logger.info(f"Formatted {len(competencies_data)} relevant competencies with indicators.")

        # 5. Получаем существующие связи
        existing_links_data = []
        if aup_data_ids_in_matrix and indicator_ids_in_matrix:
            # Используем .in_() для эффективного запроса
            existing_links_db = session.query(CompetencyMatrix).filter(
                and_(
                   CompetencyMatrix.aup_data_id.in_(list(aup_data_ids_in_matrix)), # Преобразуем set в list
                   CompetencyMatrix.indicator_id.in_(list(indicator_ids_in_matrix)) # Преобразуем set в list
                )
            ).all()
            existing_links_data = [
                link.to_dict(only=('aup_data_id', 'indicator_id'))
                for link in existing_links_db
            ]
            logger.info(f"Found {len(existing_links_data)} existing matrix links for relevant AupData and Indicators.")


        # 6. Предложения от NLP (заглушка для MVP)
        suggestions_data = []
        # TODO: Добавить вызов suggest_links_nlp(disciplines_list, competencies_data)
        # suggestions_data = suggest_links_nlp(disciplines_list, competencies_data) # Заглушка

        # Сериализуем AupInfo в конце
        aup_info_dict = aup_info.as_dict() # Используем as_dict из maps.models.py
        # Удаляем relation properties, если они есть в as_dict
        aup_info_dict.pop('education_programs_assoc', None)
        # Добавляем num_aup если он не попал в as_dict
        if 'num_aup' not in aup_info_dict and hasattr(aup_info, 'num_aup'):
             aup_info_dict['num_aup'] = aup_info.num_aup


        return {
            "aup_info": aup_info_dict,
            "disciplines": disciplines_list,
            "competencies": competencies_data,
            "links": existing_links_data,
            "suggestions": suggestions_data
        }

    except SQLAlchemyError as e:
        logger.error(f"Database error in get_matrix_for_aup for aup_id {aup_id}: {e}", exc_info=True)
        session.rollback() # Откат при ошибке БД
        return None
    except AttributeError as e: # Может быть при неполноте данных (например, AUP_assoc, но AUP==None)
        logger.error(f"Attribute error likely due to missing relationship/data in get_matrix_for_aup for aup_id {aup_id}: {e}", exc_info=True)
        session.rollback() # Откат при ошибке
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_matrix_for_aup for aup_id {aup_id}: {e}", exc_info=True)
        session.rollback() # Откат при любой неожиданной ошибке
        return None

# --- Функции для изменения данных ---

def update_matrix_link(aup_data_id: int, indicator_id: int, create: bool = True) -> Dict[str, Any]:
    """
    Создает или удаляет связь Дисциплина(АУП)-ИДК в матрице.
    (Версия с подробным возвратом статуса)

    Args:
        aup_data_id: ID записи из таблицы aup_data.
        indicator_id: ID индикатора из таблицы indicators.
        create (bool): True для создания связи, False для удаления.

    Returns:
        Dict[str, Any]: Словарь с результатом операции:
            {
                'success': True/False,
                'status': 'created'/'already_exists'/'deleted'/'not_found'/'error',
                'message': '...' (сообщение для логирования/отладки),
                'error_type': '...' (опционально, тип ошибки),
                'details': '...' (опционально, детали ошибки)
            }
    """
    session: Session = db.session
    try:
        # 1. Проверяем существование AupData и Indicator более эффективно
        # Используем AND для комбинации условий в одном exists() запросе, если возможно
        # Или делаем два отдельных запроса для более точной диагностики ошибки 404
        
        aup_data_exists = session.query(exists().where(AupData.id == aup_data_id)).scalar()
        if not aup_data_exists:
            message = f"update_matrix_link: AupData entry with id {aup_data_id} not found."
            logger.warning(message)
            return {
                'success': False,
                'status': 'error',
                'message': message,
                'error_type': 'aup_data_not_found'
            }

        indicator_exists = session.query(exists().where(Indicator.id == indicator_id)).scalar()
        if not indicator_exists:
            message = f"update_matrix_link: Indicator with id {indicator_id} not found."
            logger.warning(message)
            return {
                'success': False,
                'status': 'error',
                'message': message,
                'error_type': 'indicator_not_found'
            }

        # 2. Находим существующую связь
        existing_link = session.query(CompetencyMatrix).filter_by(
            aup_data_id=aup_data_id,
            indicator_id=indicator_id
        ).first()

        if create:
            if not existing_link:
                link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
                session.add(link)
                session.commit()
                message = f"Link created: AupData {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return {
                    'success': True,
                    'status': 'created',
                    'message': message
                }
            else:
                message = f"Link already exists: AupData {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return {
                    'success': True,
                    'status': 'already_exists',
                    'message': message
                }
        else: # delete
            if existing_link:
                session.delete(existing_link)
                session.commit()
                message = f"Link deleted: AupData {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return {
                    'success': True,
                    'status': 'deleted',
                    'message': message
                }
            else:
                message = f"Link not found for deletion: AupData {aup_data_id} <-> Indicator {indicator_id}"
                logger.warning(message)
                return {
                    'success': True, # Вернем success=True, т.к. цель (отсутствие связи) достигнута
                    'status': 'not_found',
                    'message': message
                }

    except SQLAlchemyError as e:
        session.rollback()
        message = f"Database error in update_matrix_link: {e}"
        logger.error(message, exc_info=True)
        return {
            'success': False,
            'status': 'error',
            'message': message,
            'error_type': 'database_error'
        }
    except Exception as e:
        session.rollback()
        message = f"Unexpected error in update_matrix_link: {e}"
        logger.error(message, exc_info=True)
        return {
            'success': False,
            'status': 'error',
            'message': message,
            'error_type': 'unexpected_error',
            'details': str(e)
        }


def create_competency(data: Dict[str, Any]) -> Optional[Competency]:
    """
    Создает новую компетенцию (обычно ПК). Базовая реализация для MVP.

    Args:
        data: Словарь с данными {'type_code': 'ПК', 'code': 'ПК-1', 'name': '...', ...}.

    Returns:
        Optional[Competency]: Созданный объект компетенции или None.
    """
    # TODO: Добавить валидацию входных данных (через schemas.py)
    required_fields = ['type_code', 'code', 'name']
    if not all(field in data for field in required_fields):
        logger.warning("Missing required fields for competency creation.")
        return None

    try:
        session = db.session
        comp_type = session.query(CompetencyType).filter_by(code=data['type_code']).first()
        if not comp_type:
            logger.warning(f"Competency type with code {data['type_code']} not found.")
            return None

        # Проверка на уникальность кода компетенции в рамках типа и/или ФГОС/ТФ
        # Для ПК, вероятно, код уникален в рамках ОП (косвенно через ПС/ТФ) или глобально?
        # Для УК/ОПК - уникален в рамках ФГОС.
        # MVP: Просто проверка уникальности кода в рамках типа.
        existing_comp = session.query(Competency).filter_by(
             code=data['code'],
             competency_type_id=comp_type.id # Уникальность по коду и типу
        ).first()
        if existing_comp:
             logger.warning(f"Competency with code {data['code']} and type {data['type_code']} already exists.")
             return None # Или вернуть существующий объект? Для POST обычно возвращают новый или ошибку.

        competency = Competency(
            competency_type_id=comp_type.id,
            code=data['code'],
            name=data['name'],
            description=data.get('description'),
            # TODO: Добавить поля based_on_labor_function_id, fgos_vo_id и др.
            # based_on_labor_function_id=data.get('based_on_tf_id'), # Требует валидации ID ТФ
            # fgos_vo_id=data.get('fgos_vo_id') # Требует валидации ID ФГОС
        )
        session.add(competency)
        session.commit()
        logger.info(f"Competency created: {competency.code} (ID: {competency.id})")
        return competency
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error creating competency: {e}", exc_info=True)
        return None
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error creating competency: {e}", exc_info=True)
        return None

def create_indicator(data: Dict[str, Any]) -> Optional[Indicator]:
    """
    Создает новый индикатор (ИДК). Базовая реализация для MVP.

    Args:
        data: Словарь с данными {'competency_id': ..., 'code': 'ИПК-1.1', 'formulation': '...', ...}

    Returns:
        Optional[Indicator]: Созданный объект индикатора или None.
    """
    # TODO: Добавить валидацию входных данных
    required_fields = ['competency_id', 'code', 'formulation']
    if not all(field in data for field in required_fields):
        logger.warning("Missing required fields for indicator creation.")
        return None

    try:
        session = db.session
        # Проверяем существование родительской компетенции
        competency = session.query(Competency).get(data['competency_id'])
        if not competency:
            logger.warning(f"Parent competency with id {data['competency_id']} not found.")
            return None

        # Проверка на уникальность кода индикатора в рамках компетенции
        existing_indicator = session.query(Indicator).filter_by(
             code=data['code'],
             competency_id=data['competency_id']
        ).first()
        if existing_indicator:
             logger.warning(f"Indicator with code {data['code']} for competency {data['competency_id']} already exists.")
             return None # Или вернуть существующий объект?

        indicator = Indicator(
            competency_id=data['competency_id'],
            code=data['code'],
            formulation=data['formulation'],
            source=data.get('source') # Используем поле 'source'
            # TODO: Реализовать сохранение связей с ПС (IndicatorPsLink)
        )
        session.add(indicator)
        session.commit()
        logger.info(f"Indicator created: {indicator.code} (ID: {indicator.id}) for competency {indicator.competency_id}")
        return indicator
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error creating indicator: {e}", exc_info=True)
        return None
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error creating indicator: {e}", exc_info=True)
        return None

# --- Функции для работы с ФГОС ---

def parse_fgos_file(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    """
    Оркестрирует парсинг загруженного файла ФГОС ВО.

    Args:
        file_bytes: Содержимое PDF файла в байтах.
        filename: Имя файла.

    Returns:
        Optional[Dict[str, Any]]: Структурированные данные ФГОС или None в случае ошибки парсинга.
    """
    try:
        # TODO: Добавить проверку типа файла (только PDF?) - на роуте
        parsed_data = parse_fgos_pdf(file_bytes, filename)
        
        # Простая проверка, что извлечены хотя бы базовые метаданные и компетенции
        if not parsed_data or not parsed_data.get('metadata') or (not parsed_data.get('uk_competencies') and not parsed_data.get('opk_competencies')):
             logger.warning(f"parse_fgos_file: Parsing failed or returned insufficient data for {filename}")
             # Если парсер вернул данные, но они неполные, выбрасываем ValueError
             raise ValueError("Не удалось извлечь основные метаданные и/или компетенции из файла ФГОС.")

        # TODO: Добавить логику сравнения с существующим ФГОС в БД (если нужно для preview)
        # На этом этапе возвращаем просто парсенные данные. Сравнение будет на фронтенде или в save_fgos_data.
        
        return parsed_data
        
    except ValueError as e: # Ловим специфичные ошибки парсера
        logger.error(f"parse_fgos_file: Parser ValueError for {filename}: {e}")
        # traceback.print_exc() # Уже выведено в парсере при ValueError
        raise e # Перевыбрасываем ошибку для обработки вызывающей функцией
    except Exception as e:
        logger.error(f"parse_fgos_file: Unexpected error parsing {filename}: {e}", exc_info=True)
        # traceback.print_exc()
        raise Exception(f"Неожиданная ошибка при парсинге файла ФГОС: {e}")


def save_fgos_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[FgosVo]:
    """
    Сохраняет структурированные данные ФГОС из парсера в БД.
    Обрабатывает обновление существующих записей (FgosVo, Competency, Indicator).

    Args:
        parsed_data: Структурированные данные, полученные от parse_fgos_file.
        filename: Имя исходного файла (для сохранения пути).
        session: Сессия SQLAlchemy.
        force_update: Если True, удаляет старый ФГОС и связанные сущности перед сохранением нового.
                      Если False, пытается найти существующий ФГОС и либо пропустить,
                      либо вернуть ошибку (в зависимости от логики обновления).

    Returns:
        Optional[FgosVo]: Сохраненный (или обновленный) объект FgosVo или None в случае ошибки.
                          Возвращает существующий объект, если force_update=False и он найден.
    """
    if not parsed_data or not parsed_data.get('metadata'):
        logger.warning("save_fgos_data: No parsed data or metadata provided.")
        return None

    metadata = parsed_data['metadata']
    fgos_number = metadata.get('order_number')
    fgos_date_str = metadata.get('order_date') # Строка из парсера
    fgos_direction_code = metadata.get('direction_code')
    fgos_education_level = metadata.get('education_level')
    fgos_generation = metadata.get('generation')
    fgos_direction_name = metadata.get('direction_name')

    # TODO: Добавить другие поля метаданных, если извлекаются парсером (metadata['order_info']?)

    if not fgos_number or not fgos_date_str or not fgos_direction_code or not fgos_education_level:
        logger.error("save_fgos_data: Missing core metadata from parsed data for saving.")
        # Возвращаем None, чтобы вызывающая функция знала об ошибке
        return None

    # Преобразуем дату из строки в объект Date (поддерживаем разные форматы парсера)
    fgos_date_obj = None
    try:
        # Пробуем формат DD.MM.YYYY
        fgos_date_obj = datetime.datetime.strptime(fgos_date_str, '%d.%m.%Y').date()
    except (ValueError, TypeError):
        try:
            # Пробуем формат "D MMMM YYYY г."
            # Пример: "19 сентября 2017 г."
            # Для этого может потребоваться локализация или более сложный парсинг
            # Пока просто логируем и оставляем None
            logger.warning(f"save_fgos_data: Could not parse date '{fgos_date_str}' in standard format. Attempting other formats.")
            # TODO: Implement parsing for "D MMMM YYYY г." format if needed
            pass # Оставляем fgos_date_obj = None если парсинг не удался
        except Exception as e:
             logger.warning(f"save_fgos_data: Unexpected error parsing date '{fgos_date_str}': {e}")
             fgos_date_obj = None # Убеждаемся, что он None при ошибке

    if not fgos_date_obj:
         logger.error(f"save_fgos_data: Failed to parse date '{fgos_date_str}' into a Date object.")
         return None # Не можем сохранить без валидной даты

    # --- 1. Ищем существующий ФГОС ---
    # Считаем ФГОС уникальным по комбинации код направления + уровень + номер + дата
    existing_fgos = session.query(FgosVo).filter_by(
        direction_code=fgos_direction_code,
        education_level=fgos_education_level,
        number=fgos_number,
        date=fgos_date_obj # Сравниваем с объектом Date
    ).first()

    if existing_fgos:
        if force_update:
            logger.info(f"save_fgos_data: Existing FGOS found ({existing_fgos.id}, code: {existing_fgos.direction_code}). Force update requested. Deleting old...")
            # Удаляем старый ФГОС и все связанные сущности (благодаря CASCADE DELETE)
            try:
                session.delete(existing_fgos)
                # НЕ КОММИТИМ УДАЛЕНИЕ ЗДЕСЬ. Комит будет в конце вместе с новым сохранением.
                # Если удаление не сработало из-за FK, общая транзакция откатится.
                # session.commit() # Удален коммит
                logger.info(f"save_fgos_data: Old FGOS ({existing_fgos.id}) marked for deletion.")
            except SQLAlchemyError as e:
                # Не откатываем здесь, т.к. это будет сделано в вызывающей функции при ошибке
                # session.rollback()
                logger.error(f"save_fgos_data: Database error marking old FGOS {existing_fgos.id} for deletion: {e}", exc_info=True)
                # Возвращаем None, чтобы сигнализировать об ошибке сохранения
                return None
        else:
            # Если не force_update и ФГОС существует, мы его не перезаписываем
            logger.warning(f"save_fgos_data: FGOS with same code, level, number, date already exists ({existing_fgos.id}). Force update NOT requested. Skipping save.")
            # Возвращаем существующий объект, чтобы фронтенд знал о дубликате
            return existing_fgos


    # --- 2. Создаем новый FgosVo ---
    try:
        # Создаем новый объект FgosVo
        fgos_vo = FgosVo(
            number=fgos_number,
            date=fgos_date_obj,
            direction_code=fgos_direction_code,
            direction_name=fgos_direction_name or 'Не указано', # Используем извлеченное имя
            education_level=fgos_education_level,
            generation=fgos_generation,
            file_path=filename # Сохраняем имя файла
            # TODO: Добавить другие поля метаданных, если извлекаются парсером
        )
        session.add(fgos_vo)
        # Не коммитим здесь, все коммиты в конце
        # session.commit() # Удален коммит
        logger.info(f"save_fgos_data: New FgosVo object created for {fgos_vo.direction_code}.")

    except SQLAlchemyError as e:
        # Не откатываем здесь
        # session.rollback()
        logger.error(f"save_fgos_data: Database error creating FgosVo object: {e}", exc_info=True)
        return None

    # --- 3. Сохраняем Компетенции и Индикаторы ---
    try:
        # Получаем типы компетенций (УК, ОПК) из БД (уже должны быть сидированы)
        comp_types = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
        if not comp_types:
             logger.error("save_fgos_data: CompetencyType (УК, ОПК) not found in DB. Cannot save competencies.")
             return None # Критическая ошибка, не можем сохранить Компетенции

        saved_competencies_count = 0
        saved_indicators_count = 0
        # Объединяем УК и ОПК для итерации
        all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])

        for parsed_comp in all_parsed_competencies:
            comp_code = parsed_comp.get('code')
            comp_name = parsed_comp.get('name')
            parsed_indicators = parsed_comp.get('indicators', [])

            if not comp_code or not comp_name:
                logger.warning(f"save_fgos_data: Skipping competency due to missing code/name: {parsed_comp}")
                continue

            comp_prefix = comp_code.split('-')[0]
            comp_type = comp_types.get(comp_prefix)

            if not comp_type:
                logger.warning(f"save_fgos_data: Skipping competency {comp_code}: Competency type {comp_prefix} not found in DB.")
                continue
                
            # Проверяем, существует ли уже компетенция с таким кодом, привязанная к этому ФГОС
            # Это важно при force_update, чтобы не дублировать (хотя удаление старого ФГОС должно это предотвратить)
            # Но также полезно, если логика обновления будет сложнее, чем просто удаление
            existing_comp = session.query(Competency).filter_by(
                 code=comp_code,
                 fgos_vo_id=fgos_vo.id # Проверяем привязку именно к новому/обновляемому ФГОС
            ).first()
            
            if existing_comp:
                 logger.warning(f"save_fgos_data: Competency {comp_code} already exists for FGOS {fgos_vo.id}. Updating instead of creating.")
                 # TODO: Реализовать логику обновления существующей компетенции и ее индикаторов
                 # Для MVP просто пропускаем создание, предполагая, что она осталась от старого или была создана иначе
                 # Или можно очистить ее старые индикаторы и добавить новые
                 # Для простоты текущей логики (удаление старого ФГОС) - этот блок не должен часто срабатывать.
                 # Если сработал - это либо баг в удалении, либо неполное удаление.
                 # Пока просто логируем и пропускаем.
                 continue # Пропускаем создание, если уже есть

            # Создаем компетенцию
            competency = Competency(
                competency_type_id=comp_type.id,
                fgos_vo_id=fgos_vo.id, # Связываем с новым ФГОС
                code=comp_code,
                name=comp_name,
                # description=... # Если есть описание в парсенных данных
            )
            session.add(competency)
            # Используем flush, чтобы получить ID компетенции ДО коммита
            session.flush() 
            saved_competencies_count += 1

            # Создаем индикаторы для этой компетенции
            for parsed_ind in parsed_indicators:
                ind_code = parsed_ind.get('code')
                ind_formulation = parsed_ind.get('formulation')

                # Проверяем, относится ли индикатор к этой компетенции по коду
                if not ind_code or not ind_formulation or not ind_code.startswith(f"{comp_code}."):
                    logger.warning(f"save_fgos_data: Skipping indicator due to missing code/formulation or code mismatch ({comp_code}.* vs {ind_code}): {parsed_ind}")
                    continue

                # Проверяем, существует ли уже индикатор с таким кодом для этой компетенции
                existing_ind = session.query(Indicator).filter_by(
                     code=ind_code,
                     competency_id=competency.id
                ).first()
                
                if existing_ind:
                     logger.warning(f"save_fgos_data: Indicator {ind_code} already exists for competency {competency.id}. Skipping creation.")
                     # TODO: Реализовать логику обновления индикатора, если нужно
                     continue # Пропускаем создание, если уже есть

                indicator = Indicator(
                    competency_id=competency.id, # Связываем по ID
                    code=ind_code,
                    formulation=ind_formulation,
                    source=f"ФГОС {fgos_vo.direction_code} ({fgos_vo.generation})" # Указываем источник
                )
                session.add(indicator)
                saved_indicators_count += 1

        # Не коммитим здесь
        # session.commit() # Удален коммит
        logger.info(f"save_fgos_data: Queued {saved_competencies_count} competencies and {saved_indicators_count} indicators for saving.")

    except SQLAlchemyError as e:
        # Не откатываем здесь
        # session.rollback()
        logger.error(f"save_fgos_data: Database error saving competencies/indicators: {e}", exc_info=True)
        return None # Вернем None, чтобы указать на ошибку

    # --- 4. Сохраняем рекомендованные ПС ---
    try:
        recommended_ps_codes = parsed_data.get('recommended_ps_codes', [])
        logger.info(f"save_fgos_data: Found {len(recommended_ps_codes)} potential recommended PS codes in parsed data.")
        
        # Ищем существующие Профстандарты по кодам в БД
        # Используем .in_() для эффективного запроса
        if recommended_ps_codes:
             existing_prof_standards = session.query(ProfStandard).filter(ProfStandard.code.in_(recommended_ps_codes)).all()
             ps_by_code = {ps.code: ps for ps in existing_prof_standards}
        else:
             ps_by_code = {}


        linked_ps_count = 0
        for ps_code in recommended_ps_codes:
            prof_standard = ps_by_code.get(ps_code)
            if prof_standard:
                # Проверяем, существует ли уже эта связь ФГОС-ПС
                existing_link = session.query(FgosRecommendedPs).filter_by(
                    fgos_vo_id=fgos_vo.id,
                    prof_standard_id=prof_standard.id
                ).first()
                
                if not existing_link:
                     # Создаем связь FgosRecommendedPs
                     link = FgosRecommendedPs(
                         fgos_vo_id=fgos_vo.id,
                         prof_standard_id=prof_standard.id,
                         is_mandatory=False # По умолчанию считаем рекомендованным
                         # description = ... # Если парсер найдет доп. описание связи
                     )
                     session.add(link)
                     linked_ps_count += 1
                else:
                     logger.warning(f"save_fgos_data: Link between FGOS {fgos_vo.id} and PS {prof_standard.code} already exists. Skipping creation.")

            else:
                logger.warning(f"save_fgos_data: Recommended PS with code {ps_code} not found in DB. Skipping link creation.")

        # Не коммитим здесь
        # session.commit() # Удален коммит
        logger.info(f"save_fgos_data: Queued {linked_ps_count} recommended PS links for saving.")

    except SQLAlchemyError as e:
        # Не откатываем здесь
        # session.rollback()
        logger.error(f"save_fgos_data: Database error saving recommended PS links: {e}", exc_info=True)
        return None # Вернем None, чтобы указать на ошибку


    # --- Финальный коммит ---
    try:
        session.commit()
        logger.info(f"save_fgos_data: Final commit successful for FGOS ID {fgos_vo.id}.")
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"save_fgos_data: Final commit failed for FGOS ID {getattr(fgos_vo, 'id', 'N/A')}: {e}", exc_info=True)
        return None # Вернем None, чтобы указать на ошибку


    # Если дошли сюда, все сохранено успешно
    return fgos_vo


def get_fgos_list() -> List[FgosVo]:
    """
    Получает список всех сохраненных ФГОС ВО.

    Returns:
        List[FgosVo]: Список объектов FgosVo.
    """
    try:
        # Просто возвращаем все ФГОС, можно добавить сортировку/фильтры позже
        # Добавим eager loading для associated educational programs count
        fgos_list = db.session.query(FgosVo).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()
        # TODO: добавить count_educational_programs = column_property(select(func.count(EducationalProgram.id)).where(EducationalProgram.fgos_vo_id == FgosVo.id).scalar_subquery()) in model?
        return fgos_list
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_fgos_list: {e}", exc_info=True)
        return []


def get_fgos_details(fgos_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает детальную информацию по ФГОС ВО, включая связанные компетенции, индикаторы,
    и рекомендованные профстандарты.

    Args:
        fgos_id: ID ФГОС ВО.

    Returns:
        Optional[Dict[str, Any]]: Словарь с данными ФГОС или None, если не найден.
    """
    try:
        # Убедимся, что сессия активна
        session = db.session
        if not session.is_active:
            session = db.session # Получим новую сессию, если текущая закрыта

        fgos = session.query(FgosVo).options(
            # Загружаем связанные сущности
            selectinload(FgosVo.competencies).selectinload(Competency.indicators).joinedload(Indicator.competency), # Загружаем родителя индикатора для типа
            selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard)
        ).get(fgos_id)

        if not fgos:
            logger.warning(f"FGOS with id {fgos_id} not found for details.")
            return None

        # Сериализуем основной объект ФГОС
        details = fgos.to_dict()
        details['date'] = details['date'].isoformat() if details.get('date') else None # Форматируем дату

        # Сериализуем компетенции и индикаторы
        uk_competencies_data = []
        opk_competencies_data = []

        # Сортируем компетенции
        sorted_competencies = sorted(fgos.competencies, key=lambda c: c.code)

        for comp in sorted_competencies:
            # Убеждаемся, что компетенция относится к этому ФГОС и является УК/ОПК
            # Проверка comp.fgos_vo_id == fgos_id избыточна благодаря relationship,
            # но проверка типа важна
            if comp.competency_type and comp.competency_type.code in ['УК', 'ОПК']:
                 comp_dict = comp.to_dict(rules=['-fgos', '-based_on_labor_function']) # Избегаем циклических ссылок и лишних данных
                 
                 # Сериализуем индикаторы для этой компетенции
                 comp_dict['indicators'] = []
                 if comp.indicators:
                      # Сортируем индикаторы
                      sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                      comp_dict['indicators'] = [ind.to_dict() for ind in sorted_indicators]

                 if comp.competency_type.code == 'УК':
                      uk_competencies_data.append(comp_dict)
                 elif comp.competency_type.code == 'ОПК':
                      opk_competencies_data.append(comp_dict)
                 # ПК не должны быть напрямую связаны через fgos_vo_id

        details['uk_competencies'] = uk_competencies_data
        details['opk_competencies'] = opk_competencies_data


        # Сериализуем рекомендованные профстандарты
        recommended_ps_list = []
        if fgos.recommended_ps_assoc:
            for assoc in fgos.recommended_ps_assoc:
                if assoc.prof_standard:
                    recommended_ps_list.append({
                        'id': assoc.prof_standard.id,
                        'code': assoc.prof_standard.code,
                        'name': assoc.prof_standard.name,
                        'is_mandatory': assoc.is_mandatory,
                        'description': assoc.description,
                    })
        details['recommended_ps_list'] = recommended_ps_list

        logger.info(f"Fetched details for FGOS {fgos_id}.")
        return details

    except SQLAlchemyError as e:
        logger.error(f"Database error in get_fgos_details for fgos_id {fgos_id}: {e}", exc_info=True)
        # Нет необходимости в rollback для GET запросов, если они были только read
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_fgos_details for fgos_id {fgos_id}: {e}", exc_info=True)
        return None


def delete_fgos(fgos_id: int, session: Session) -> bool:
    """
    Удаляет ФГОС ВО и все связанные сущности (Компетенции, Индикаторы, связи с ПС).
    Предполагается, что отношения в моделях настроены на CASCADE DELETE.

    Args:
        fgos_id: ID ФГОС ВО для удаления.
        session: Сессия SQLAlchemy.

    Returns:
        bool: True, если удаление выполнено успешно, False в противном случае.
    """
    try:
        fgos_to_delete = session.query(FgosVo).get(fgos_id)
        if not fgos_to_delete:
            logger.warning(f"delete_fgos: FGOS with id {fgos_id} not found.")
            return False

        # SQLAlchemy с CASCADE DELETE должен удалить:
        # - Competency, связанные с этим FgosVo (FK Competency.fgos_vo_id)
        # - Indicator, связанные с этими Competency (FK Indicator.competency_id)
        # - FgosRecommendedPs, связанные с этим FgosVo (FK FgosRecommendedPs.fgos_vo_id)
        # - EducationalProgram, связанные с этим FgosVo (FK EducationalProgram.fgos_vo_id)
        # - EducationalProgramAup, связанные с EducationalProgram (FK EducationalProgramAup.educational_program_id) - если CASCADE настроен там
        # - EducationalProgramPs, связанные с EducationalProgram (FK EducationalProgramPs.educational_program_id) - если CASCADE настроен там

        session.delete(fgos_to_delete)
        session.commit()
        logger.info(f"delete_fgos: FGOS with id {fgos_id} deleted successfully (cascading enabled).")
        return True

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"delete_fgos: Database error deleting FGOS {fgos_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"delete_fgos: Unexpected error deleting FGOS {fgos_id}: {e}", exc_info=True)
        return False


# Вспомогательные функции (для будущей имплементации)

def create_indicator(data: Dict[str, Any]) -> Optional[Indicator]:
    """
    Создает новый индикатор достижения компетенции (ИДК).
    (Функция дублируется в logic.py. Оставим один вариант.)
    """
    # TODO: Убедиться, что остался только ОДИН вариант create_indicator в logic.py
    pass

def suggest_links_nlp(disciplines: List[Dict], indicators: List[Dict]) -> List[Dict]:
    """
    Получает предложения по связям "Дисциплина-ИДК" от NLP модуля.
    Это заглушка, которая будет заменена реальным вызовом к NLP.
    
    Args:
        disciplines: Список дисциплин с их данными
        indicators: Список ИДК с их данными
        
    Returns:
        List: Список предложенных связей вида [{'aup_data_id': ..., 'indicator_id': ..., 'score': ...}, ...]
    """
    # Заглушка - в реальности здесь будет вызов к NLP сервису
    # Просто возвращаем пару случайных связей
    import random
    
    if not disciplines or not indicators:
        return []
    
    result = []
    # Генерируем 5 случайных предложений
    for _ in range(min(5, len(disciplines) * len(indicators))):
        # Защита от деления на ноль, если какой-то список пуст
        if not disciplines or not indicators:
            break
        d = random.choice(disciplines)
        i = random.choice(indicators)
        result.append({
            'aup_data_id': d['aup_data_id'],
            'indicator_id': i['id'],
            'score': round(random.random(), 2) # Случайная оценка релевантности
        })
    
    return result