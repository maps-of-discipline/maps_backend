# competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
from sqlalchemy.orm import joinedload, selectinload, Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import exists
import traceback
from .fgos_parser import parse_fgos_pdf

from maps.models import db, AupData, SprDiscipline, AupInfo
from .models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramPs, EducationalProgramAup,
    CompetencyType, IndicatorPsLink
)

# --- Функции для получения данных для отображения ---

def get_educational_programs_list() -> List[EducationalProgram]:
    """
    Получает список всех образовательных программ из БД.

    Returns:
        List[EducationalProgram]: Список объектов SQLAlchemy EducationalProgram.
    """
    try:
        # Просто возвращаем все программы, можно добавить фильтры/пагинацию позже
        programs = EducationalProgram.query.order_by(EducationalProgram.title).all()
        return programs
    except SQLAlchemyError as e:
        # Логирование ошибки
        print(f"Database error in get_educational_programs_list: {e}")
        # В реальном приложении здесь может быть более сложное логирование
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
            'created_at': program.created_at,
            'updated_at': program.updated_at
        }

        # Добавляем детали в нужном формате
        if program.fgos:
            details['fgos_details'] = {
                'id': program.fgos.id,
                'number': program.fgos.number,
                'date': program.fgos.date,
                'direction_code': program.fgos.direction_code,
                'direction_name': program.fgos.direction_name,
                'education_level': program.fgos.education_level,
                'generation': program.fgos.generation,
                'file_path': program.fgos.file_path
            }
        else:
            details['fgos_details'] = None
            
        details['aup_list'] = [
            {
                'id_aup': assoc.aup.id_aup,
                'num_aup': assoc.aup.num_aup,
                'file': assoc.aup.file
            } 
            for assoc in program.aup_assoc if assoc.aup
        ]
        
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
        print(f"Database error in get_program_details for program_id {program_id}: {e}")
        return None

def get_matrix_for_aup(aup_id: int) -> Optional[Dict[str, Any]]:
    """
    Собирает все данные для отображения матрицы компетенций для АУП.
    (Версия с исправлениями сортировки и фильтрации УК/ОПК)

    Args:
        aup_id: ID Академического учебного плана (из таблицы tbl_aup).

    Returns:
        Словарь с данными для фронтенда или None.
    """
    try:
        session: Session = db.session

        # 1. Получаем инфо об АУП, ОП и ФГОС
        aup_info = session.query(AupInfo).options(
            selectinload(AupInfo.education_programs_assoc)
                .selectinload(EducationalProgramAup.educational_program)
                    .selectinload(EducationalProgram.fgos)
        ).get(aup_id)

        if not aup_info:
            print(f"AUP with id {aup_id} not found.")
            return None

        # 2. Находим ОП и ФГОС
        program = None
        fgos = None
        if aup_info.education_programs_assoc:
            program = aup_info.education_programs_assoc[0].educational_program
            if program:
                fgos = program.fgos
        else:
            print(f"Warning: AUP {aup_id} is not linked to any Educational Program.")
            return None
        if not program:
             print(f"Could not retrieve Educational Program for AUP {aup_id}.")
             return None

        # 3. Получаем дисциплины АУП из AupData
        aup_data_entries = session.query(AupData).options(
            joinedload(AupData.discipline)  # Change from unique_discipline to discipline
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

        # Сортировка списка дисциплин
        disciplines_list.sort(key=lambda d: (d.get('semester', 0), d.get('title', '')))

        # 4. Получаем компетенции и их индикаторы
        competencies_query = session.query(Competency).options(
            selectinload(Competency.indicators),
            joinedload(Competency.competency_type)
        )

        relevant_competencies = []
        if fgos:
            uk_opk_competencies = competencies_query.filter(
                Competency.fgos_vo_id == fgos.id,
                Competency.competency_type.has(CompetencyType.code.in_(['УК', 'ОПК']))
            ).all()
            relevant_competencies.extend(uk_opk_competencies)
        else:
             print(f"Warning: No FGOS linked to Educational Program {program.id}. УК/ОПК might be missing.")

        pk_competencies = competencies_query.join(CompetencyType).filter(
            CompetencyType.code == 'ПК'
        ).all()
        relevant_competencies.extend(pk_competencies)

        # Форматируем результат
        competencies_data = []
        indicator_ids_in_matrix = set()
        unique_competency_ids = set()

        for comp in relevant_competencies:
            if comp.id in unique_competency_ids:
                continue
            unique_competency_ids.add(comp.id)

            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"

            comp_dict = comp.to_dict(rules=['-indicators', '-competency_type', '-fgos', '-based_on_labor_function', '-matrix_links'])
            comp_dict['type_code'] = type_code
            comp_dict['indicators'] = []
            if comp.indicators:
                sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                for ind in sorted_indicators:
                    indicator_ids_in_matrix.add(ind.id)
                    comp_dict['indicators'].append(
                        ind.to_dict(only=('id', 'code', 'formulation', 'source'))
                    )
            competencies_data.append(comp_dict)

        # Сортировка компетенций
        competencies_data.sort(key=lambda c: (c.get('type_code', ''), c.get('code', '')))

        # 5. Получаем существующие связи
        existing_links_data = []
        if aup_data_ids_in_matrix and indicator_ids_in_matrix:
            existing_links_db = session.query(CompetencyMatrix).filter(
                CompetencyMatrix.aup_data_id.in_(aup_data_ids_in_matrix),
                CompetencyMatrix.indicator_id.in_(indicator_ids_in_matrix)
            ).all()
            existing_links_data = [
                link.to_dict(only=('aup_data_id', 'indicator_id'))
                for link in existing_links_db
            ]

        # 6. Предложения от NLP (заглушка для MVP)
        suggestions_data = []

        return {
            "aup_info": aup_info.as_dict(),
            "disciplines": disciplines_list,
            "competencies": competencies_data,
            "links": existing_links_data,
            "suggestions": suggestions_data
        }

    except SQLAlchemyError as e:
        print(f"Database error in get_matrix_for_aup for aup_id {aup_id}: {e}")
        session.rollback()
        return None
    except AttributeError as e:
        print(f"Attribute error likely due to missing relationship/data in get_matrix_for_aup for aup_id {aup_id}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error in get_matrix_for_aup for aup_id {aup_id}: {e}")
        traceback.print_exc()
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
                'error': '...' (опционально, детали ошибки, если была)
            }
    """
    session: Session = db.session
    try:
        # 1. Проверяем существование AupData и Indicator более эффективно
        aup_data_exists = session.query(exists().where(AupData.id == aup_data_id)).scalar()
        if not aup_data_exists:
            message = f"update_matrix_link: AupData entry with id {aup_data_id} not found."
            print(message)
            return {
                'success': False,
                'status': 'error',
                'message': message,
                'error': 'aup_data_not_found'
            }

        indicator_exists = session.query(exists().where(Indicator.id == indicator_id)).scalar()
        if not indicator_exists:
            message = f"update_matrix_link: Indicator with id {indicator_id} not found."
            print(message)
            return {
                'success': False,
                'status': 'error',
                'message': message,
                'error': 'indicator_not_found'
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
                print(message)
                return {
                    'success': True,
                    'status': 'created',
                    'message': message
                }
            else:
                message = f"Link already exists: AupData {aup_data_id} <-> Indicator {indicator_id}"
                print(message)
                return {
                    'success': True,
                    'status': 'already_exists',
                    'message': message
                }
        else:
            if existing_link:
                session.delete(existing_link)
                session.commit()
                message = f"Link deleted: AupData {aup_data_id} <-> Indicator {indicator_id}"
                print(message)
                return {
                    'success': True,
                    'status': 'deleted',
                    'message': message
                }
            else:
                message = f"Link not found for deletion: AupData {aup_data_id} <-> Indicator {indicator_id}"
                print(message)
                return {
                    'success': True,
                    'status': 'not_found',
                    'message': message
                }

    except SQLAlchemyError as e:
        session.rollback()
        message = f"Database error in update_matrix_link: {e}"
        print(message)
        return {
            'success': False,
            'status': 'error',
            'message': message,
            'error': 'database_error'
        }
    except Exception as e:
        session.rollback()
        message = f"Unexpected error in update_matrix_link: {e}"
        print(message)
        traceback.print_exc()
        return {
            'success': False,
            'status': 'error',
            'message': message,
            'error': 'unexpected_error'
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
        print("Missing required fields for competency creation.")
        return None

    try:
        comp_type = CompetencyType.query.filter_by(code=data['type_code']).first()
        if not comp_type:
            print(f"Competency type with code {data['type_code']} not found.")
            return None

        # Проверка на уникальность кода компетенции (в рамках типа? ФГОС?)
        # TODO: Уточнить правила уникальности

        competency = Competency(
            competency_type_id=comp_type.id,
            code=data['code'],
            name=data['name'],
            # TODO: Добавить поля based_on_labor_function_id, fgos_vo_id и др.
            # based_on_labor_function_id=data.get('based_on_tf_id'),
            # fgos_vo_id=data.get('fgos_vo_id')
        )
        db.session.add(competency)
        db.session.commit()
        print(f"Competency created: {competency.code}")
        return competency
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"Database error creating competency: {e}")
        return None
    except Exception as e:
        db.session.rollback()
        print(f"Unexpected error creating competency: {e}")
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
        print("Missing required fields for indicator creation.")
        return None

    try:
        # Проверяем существование родительской компетенции
        competency_exists = db.session.query(Competency.id).filter_by(id=data['competency_id']).first() is not None
        if not competency_exists:
            print(f"Parent competency with id {data['competency_id']} not found.")
            return None

        # TODO: Проверка на уникальность кода индикатора в рамках компетенции

        indicator = Indicator(
            competency_id=data['competency_id'],
            code=data['code'],
            formulation=data['formulation'],
            source_description=data.get('source_description') # Добавил source
            # TODO: Реализовать сохранение связей с ПС (IndicatorPsLink)
        )
        db.session.add(indicator)
        db.session.commit()
        print(f"Indicator created: {indicator.code} for competency {indicator.competency_id}")
        return indicator
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"Database error creating indicator: {e}")
        return None
    except Exception as e:
        db.session.rollback()
        print(f"Unexpected error creating indicator: {e}")
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
        # TODO: Добавить проверку типа файла (только PDF?)
        parsed_data = parse_fgos_pdf(file_bytes, filename)
        
        # Простая проверка, что извлечены хотя бы базовые метаданные
        if not parsed_data or not parsed_data.get('metadata'):
             print(f"parse_fgos_file: Parsing failed or returned no metadata for {filename}")
             return None

        # TODO: Добавить логику сравнения с существующим ФГОС в БД (если нужно для preview)
        # На этом этапе возвращаем просто парсенные данные
        return parsed_data
        
    except ValueError as e: # Ловим специфичные ошибки парсера
        print(f"parse_fgos_file: Parser ValueError for {filename}: {e}")
        return None
    except Exception as e:
        print(f"parse_fgos_file: Unexpected error parsing {filename}: {e}")
        traceback.print_exc()
        return None


def save_fgos_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[FgosVo]:
    """
    Сохраняет структурированные данные ФГОС из парсера в БД.
    Обрабатывает обновление существующих записей (FgosVo, Competency, Indicator).

    Args:
        parsed_data: Структурированные данные, полученные от parse_fgos_file.
        filename: Имя исходного файла (для сохранения пути).
        session: Сессия SQLAlchemy.
        force_update: Если True, удаляет старый ФГОС и связанные сущности перед сохранением нового.
                      Если False, пытается найти существующий ФГОС и либо обновить его, либо пропустить,
                      либо вернуть ошибку (в зависимости от логики обновления).

    Returns:
        Optional[FgosVo]: Сохраненный (или обновленный) объект FgosVo или None в случае ошибки.
    """
    if not parsed_data or not parsed_data.get('metadata'):
        print("save_fgos_data: No parsed data or metadata provided.")
        return None

    metadata = parsed_data['metadata']
    fgos_number = metadata.get('order_number')
    fgos_date = metadata.get('order_date') # Строка в формате DD.MM.YYYY
    fgos_direction_code = metadata.get('direction_code')
    fgos_education_level = metadata.get('education_level')
    fgos_generation = metadata.get('generation')

    if not fgos_number or not fgos_date or not fgos_direction_code or not fgos_education_level:
        print("save_fgos_data: Missing core metadata for saving.")
        return None

    # Преобразуем дату из строки в объект Date
    try:
        fgos_date_obj = datetime.datetime.strptime(fgos_date, '%d.%m.%Y').date()
    except (ValueError, TypeError):
        print(f"save_fgos_data: Could not parse date '{fgos_date}'.")
        return None

    # --- 1. Ищем существующий ФГОС ---
    # Считаем ФГОС уникальным по комбинации код направления + уровень + номер + дата
    # Или только код направления + уровень + поколение? Поколение может быть "не определено".
    # Давайте использовать код направления, уровень, номер и дату приказа как основной ключ.
    existing_fgos = session.query(FgosVo).filter_by(
        direction_code=fgos_direction_code,
        education_level=fgos_education_level,
        number=fgos_number,
        date=fgos_date_obj # Сравниваем с объектом Date
    ).first()

    if existing_fgos:
        if force_update:
            print(f"save_fgos_data: Existing FGOS found ({existing_fgos.id}). Force update requested. Deleting old...")
            # Удаляем старый ФГОС и все связанные сущности (благодаря CASCADE DELETE)
            try:
                session.delete(existing_fgos)
                session.commit() # Коммит удаления
                print(f"save_fgos_data: Old FGOS ({existing_fgos.id}) and its dependencies deleted.")
            except SQLAlchemyError as e:
                session.rollback()
                print(f"save_fgos_data: Database error deleting old FGOS {existing_fgos.id}: {e}")
                return None
        else:
            # Если не force_update и ФГОС существует, мы его не перезаписываем
            print(f"save_fgos_data: FGOS with same code, level, number, date already exists ({existing_fgos.id}). Force update NOT requested. Skipping save.")
            # Можно вернуть существующий объект или None, в зависимости от требуемого поведения API POST /fgos/save
            # Если API должен вернуть ошибку 409 Conflict, то нужно выбросить исключение здесь.
            # Для простоты MVP вернем существующий объект и фронтенд решит, что с этим делать.
            return existing_fgos # Возвращаем существующий ФГОС


    # --- 2. Создаем или обновляем FgosVo ---
    try:
        # Создаем новый объект FgosVo
        fgos_vo = FgosVo(
            number=fgos_number,
            date=fgos_date_obj,
            direction_code=fgos_direction_code,
            direction_name=metadata.get('direction_name', 'Не указано'),
            education_level=fgos_education_level,
            generation=fgos_generation,
            file_path=filename # Сохраняем имя файла
            # TODO: Добавить другие поля метаданных, если извлекаются парсером
        )
        session.add(fgos_vo)
        session.commit() # Коммитим FgosVo, чтобы получить ID
        print(f"save_fgos_data: FGOS {fgos_vo.direction_code} ({fgos_vo.generation}) created with id {fgos_vo.id}.")

    except SQLAlchemyError as e:
        session.rollback()
        print(f"save_fgos_data: Database error creating FgosVo: {e}")
        return None

    # --- 3. Сохраняем Компетенции и Индикаторы ---
    # Получаем типы компетенций (УК, ОПК) из БД
    comp_types = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}

    try:
        saved_competencies = []
        # Объединяем УК и ОПК для итерации
        all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])

        for parsed_comp in all_parsed_competencies:
            comp_code = parsed_comp.get('code')
            comp_name = parsed_comp.get('name')
            parsed_indicators = parsed_comp.get('indicators', [])

            if not comp_code or not comp_name:
                print(f"save_fgos_data: Skipping competency due to missing code/name: {parsed_comp}")
                continue

            comp_prefix = comp_code.split('-')[0]
            comp_type = comp_types.get(comp_prefix)

            if not comp_type:
                print(f"save_fgos_data: Skipping competency {comp_code}: Competency type {comp_prefix} not found in DB.")
                continue

            # Создаем компетенцию
            competency = Competency(
                competency_type_id=comp_type.id,
                fgos_vo_id=fgos_vo.id, # Связываем с новым ФГОС
                code=comp_code,
                name=comp_name,
                # description=... # Если есть описание в парсенных данных
            )
            session.add(competency)
            # db.session.flush() # Получим ID компетенции перед сохранением индикаторов

            # Создаем индикаторы для этой компетенции
            for parsed_ind in parsed_indicators:
                ind_code = parsed_ind.get('code')
                ind_formulation = parsed_ind.get('formulation')

                if not ind_code or not ind_formulation:
                    print(f"save_fgos_data: Skipping indicator due to missing code/formulation: {parsed_ind}")
                    continue

                indicator = Indicator(
                    # competency_id будет установлен SQLAlchemy после flush/commit
                    competency=competency, # Связываем с родителем
                    code=ind_code,
                    formulation=ind_formulation,
                    source=f"ФГОС {fgos_vo.direction_code} ({fgos_vo.generation})" # Указываем источник
                )
                session.add(indicator)
            
            saved_competencies.append(competency)

        session.commit() # Коммитим компетенции и индикаторы
        print(f"save_fgos_data: Saved {len(saved_competencies)} competencies and their indicators for FGOS {fgos_vo.id}.")

    except SQLAlchemyError as e:
        session.rollback()
        print(f"save_fgos_data: Database error saving competencies/indicators: {e}")
        return None # Вернем None, чтобы указать на ошибку

    # --- 4. Сохраняем рекомендованные ПС ---
    try:
        recommended_ps_codes = parsed_data.get('recommended_ps_codes', [])
        print(f"save_fgos_data: Found {len(recommended_ps_codes)} recommended PS codes.")
        
        # Ищем существующие Профстандарты по кодам
        existing_prof_standards = session.query(ProfStandard).filter(ProfStandard.code.in_(recommended_ps_codes)).all()
        ps_by_code = {ps.code: ps for ps in existing_prof_standards}

        for ps_code in recommended_ps_codes:
            prof_standard = ps_by_code.get(ps_code)
            if prof_standard:
                # Создаем связь FgosRecommendedPs
                link = FgosRecommendedPs(
                    fgos_vo_id=fgos_vo.id,
                    prof_standard_id=prof_standard.id,
                    is_mandatory=False # По умолчанию считаем рекомендованным, не обязательным
                    # description = ... # Если парсер найдет доп. описание связи
                )
                session.add(link)
            else:
                print(f"save_fgos_data: Recommended PS with code {ps_code} not found in DB. Skipping link creation.")

        session.commit() # Коммитим связи ПС
        print(f"save_fgos_data: Linked {len(recommended_ps_codes)} recommended PS (if found in DB).")

    except SQLAlchemyError as e:
        session.rollback()
        print(f"save_fgos_data: Database error saving recommended PS links: {e}")
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
        fgos_list = db.session.query(FgosVo).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()
        return fgos_list
    except SQLAlchemyError as e:
        print(f"Database error in get_fgos_list: {e}")
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
        fgos = db.session.query(FgosVo).options(
            # Загружаем связанные сущности
            selectinload(FgosVo.competencies).selectinload(Competency.indicators),
            selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard)
        ).get(fgos_id)

        if not fgos:
            return None

        # Сериализуем основной объект ФГОС
        details = fgos.to_dict()

        # Сериализуем компетенции и индикаторы (фильтруем только те, что связаны с этим ФГОС)
        # Хотя relationship FgosVo.competencies уже должен был отфильтровать по FK,
        # явная проверка делает логику понятнее.
        uk_competencies_data = []
        opk_competencies_data = []

        # Сортируем компетенции и индикаторы для консистентности
        sorted_competencies = sorted(fgos.competencies, key=lambda c: c.code)

        for comp in sorted_competencies:
            # Убеждаемся, что компетенция относится к этому ФГОС и является УК/ОПК
            if comp.fgos_vo_id == fgos_id:
                 comp_dict = comp.to_dict(rules=['-fgos', '-based_on_labor_function']) # Избегаем циклических ссылок и лишних данных
                 comp_dict['indicators'] = []
                 if comp.indicators:
                      sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                      comp_dict['indicators'] = [ind.to_dict() for ind in sorted_indicators]

                 if comp.competency_type and comp.competency_type.code == 'УК':
                      uk_competencies_data.append(comp_dict)
                 elif comp.competency_type and comp.competency_type.code == 'ОПК':
                      opk_competencies_data.append(comp_dict)
                 # ПК не должны быть напрямую связаны через fgos_vo_id, но могут быть в списке competencies
                 # Если ПК случайно сюда попали, они не будут добавлены в uk_comp или opk_comp списки

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

        return details

    except SQLAlchemyError as e:
        print(f"Database error in get_fgos_details for fgos_id {fgos_id}: {e}")
        # Нет необходимости в rollback для GET запросов
        return None
    except Exception as e:
        print(f"Unexpected error in get_fgos_details for fgos_id {fgos_id}: {e}")
        traceback.print_exc()
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
            print(f"delete_fgos: FGOS with id {fgos_id} not found.")
            return False

        # SQLAlchemy с CASCADE DELETE должен удалить:
        # - Competency, связанные с этим FgosVo
        # - Indicator, связанные с этими Competency (через CASCADE на Competency)
        # - FgosRecommendedPs, связанные с этим FgosVo

        session.delete(fgos_to_delete)
        session.commit()
        print(f"delete_fgos: FGOS with id {fgos_id} deleted successfully (cascading enabled).")
        return True

    except SQLAlchemyError as e:
        session.rollback()
        print(f"delete_fgos: Database error deleting FGOS {fgos_id}: {e}")
        return False
    except Exception as e:
        session.rollback()
        print(f"delete_fgos: Unexpected error deleting FGOS {fgos_id}: {e}")
        traceback.print_exc()
        return False

def parse_prof_standard_file(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    """
    Обрабатывает загруженный файл ПС, парсит и сохраняет в БД.
    Базовая реализация для MVP: сохраняет только сам стандарт и Markdown.

    Args:
        file_bytes: Содержимое файла в байтах.
        filename: Имя файла.

    Returns:
        Optional[Dict[str, Any]]: Словарь с результатом или None.
                                  Структура успеха: {'success': True, 'prof_standard_id': ..., 'code': ..., 'name': ...}
                                  Структура ошибки: {'success': False, 'error': '...'}
    """
    from .parsers import parse_uploaded_prof_standard # Импортируем здесь, чтобы избежать цикличности при старте

    try:
        # 1. Вызов парсера для получения структурированных данных
        #    В MVP парсер может возвращать только код, имя и markdown
        parsed_data = parse_uploaded_prof_standard(file_bytes, filename)
        if not parsed_data or not parsed_data.get('code') or not parsed_data.get('name'):
            return {'success': False, 'error': 'Не удалось извлечь код или имя из файла'}

        prof_standard_code = parsed_data['code']
        prof_standard_name = parsed_data['name']
        markdown_content = parsed_data.get('parsed_content', '')
        # TODO: Получить структурированные ОТФ, ТФ и т.д. из parsed_data, когда парсер будет их возвращать

        # 2. Поиск или создание записи ProfStandard
        prof_standard = ProfStandard.query.filter_by(code=prof_standard_code).first()
        if not prof_standard:
            prof_standard = ProfStandard(
                code=prof_standard_code,
                name=prof_standard_name,
                parsed_content=markdown_content
                # TODO: Добавить даты, приказы, если парсер их извлекает
            )
            db.session.add(prof_standard)
            action = "создан"
        else:
            # Обновляем существующий
            prof_standard.name = prof_standard_name
            prof_standard.parsed_content = markdown_content
            prof_standard.updated_at = datetime.datetime.utcnow()
            action = "обновлен"
            # TODO: Реализовать обновление ОТФ, ТФ и т.д.

        # TODO: Реализовать сохранение ОТФ, ТФ и их элементов, когда парсер будет их возвращать

        db.session.commit()
        print(f"Профстандарт {prof_standard.code} {action}.")

        return {
            'success': True,
            'prof_standard_id': prof_standard.id,
            'code': prof_standard.code,
            'name': prof_standard.name
        }

    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"Database error saving parsed prof standard: {e}")
        return {'success': False, 'error': f'Ошибка базы данных: {e}'}
    except Exception as e:
        db.session.rollback()
        print(f"Error parsing or saving prof standard file {filename}: {e}")
        return {'success': False, 'error': f'Ошибка обработки файла: {e}'}

# Вспомогательные функции (для будущей имплементации)

def create_indicator(data: Dict[str, Any]) -> Optional[Indicator]:
    """
    Создает новый индикатор достижения компетенции (ИДК).
    
    Args:
        data: Словарь с данными индикатора
        
    Returns:
        Indicator: Созданный индикатор или None в случае ошибки
    """
    try:
        # Проверяем, что компетенция существует
        competency = Competency.query.get(data['competency_id'])
        if not competency:
            return None
        
        # Создаем индикатор
        new_indicator = Indicator(
            competency_id=data['competency_id'],
            code=data['code'],
            formulation=data['formulation'],
            source=data.get('source', None)
        )
        
        db.session.add(new_indicator)
        db.session.commit()
        
        # Если указаны связи с ТФ - добавляем их
        if 'labor_function_ids' in data and data['labor_function_ids']:
            for tf_id in data['labor_function_ids']:
                link = IndicatorPsLink(
                    indicator_id=new_indicator.id,
                    labor_function_id=tf_id,
                    is_manual=True
                )
                db.session.add(link)
            db.session.commit()
        
        return new_indicator
    except Exception as e:
        print(f"Ошибка при создании индикатора: {str(e)}")
        db.session.rollback()
        return None

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
    for _ in range(min(3, len(disciplines) * len(indicators))):
        d = random.choice(disciplines)
        i = random.choice(indicators)
        result.append({
            'aup_data_id': d['aup_data_id'],
            'indicator_id': i['id'],
            'score': round(random.random(), 2)
        })
    
    return result
