# competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

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
        programs = EducationalProgram.query.order_by(EducationalProgram.name).all()
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

        # Сериализуем программу и связанные объекты
        details = program.to_dict(rules=[
            '-selected_ps_assoc', # Убираем ассоциативные таблицы из основного объекта
            '-aup_assoc',
            '-fgos.educational_programs' # Предотвращаем цикл
        ])

        # Добавляем детали в нужном формате
        details['fgos_details'] = program.fgos.to_dict(rules=['-educational_programs','-recommended_ps_assoc']) if program.fgos else None
        details['aup_list'] = [assoc.aup.to_dict() for assoc in program.aup_assoc if assoc.aup]
        details['selected_ps_list'] = [
            assoc.prof_standard.to_dict(only=('id', 'code', 'name'))
            for assoc in program.selected_ps_assoc if assoc.prof_standard
        ]

        # Получаем рекомендованные ПС для связанного ФГОС
        recommended_ps_list = []
        if program.fgos and program.fgos.recommended_ps_assoc:
            # Здесь может быть эффективнее сделать отдельный запрос, если ФГОС уже загружен
            # Мы уже загрузили связи, так что можем использовать их
             recommended_ps_list = [
                 assoc.prof_standard.to_dict(only=('id', 'code', 'name'))
                 for assoc in program.fgos.recommended_ps_assoc if assoc.prof_standard
             ]
        details['recommended_ps_list'] = recommended_ps_list

        return details
    except SQLAlchemyError as e:
        print(f"Database error in get_program_details for program_id {program_id}: {e}")
        return None

def get_matrix_for_aup(aup_id: int) -> Optional[Dict[str, Any]]:
    """
    Собирает все данные для отображения матрицы компетенций для АУП.
    КЛЮЧЕВАЯ ФУНКЦИЯ ДЛЯ MVP - Доработанная версия.

    Args:
        aup_id: ID Академического учебного плана (из таблицы tbl_aup).

    Returns:
        Словарь с данными для фронтенда или None.
    """
    try:
        # 1. Получаем инфо об АУП и сразу пытаемся подгрузить связанную ОП и ФГОС
        aup_info = AupInfo.query.options(
            selectinload(AupInfo.education_programs_assoc) # Загружаем связь АУП -> ОП_АУП
                .selectinload(EducationalProgramAup.educational_program) # Загружаем ОП из связи
                    .selectinload(EducationalProgram.fgos) # Загружаем ФГОС из ОП
        ).get(aup_id)

        if not aup_info:
            print(f"AUP with id {aup_id} not found.")
            return None

        # 2. Находим ОП и ФГОС
        program = None
        fgos = None
        if aup_info.education_programs_assoc:
            # Берем первую связанную программу (предполагаем, что АУП связан только с одной ОП)
            program = aup_info.education_programs_assoc[0].educational_program
            if program:
                fgos = program.fgos
        else:
            print(f"Warning: AUP {aup_id} is not linked to any Educational Program.")
            # Если нет ОП, матрицу строить бессмысленно? Или искать компетенции по ФГОС, если он указан в АУП?
            # Для MVP вернем None, если нет связи с ОП
            return None

        if not program:
             print(f"Could not retrieve Educational Program for AUP {aup_id}.")
             return None

        # 3. Получаем дисциплины АУП из AupData (из maps.models)
        aup_data_entries = AupData.query.options(
            joinedload(AupData.unique_discipline) # Используем joinedload, т.к. связь один-к-одному
        ).filter_by(id_aup=aup_id).order_by(AupData.id_period, AupData.num_row).all()

        disciplines_list = []
        aup_data_ids_in_matrix = set() # Собираем ID записей aup_data для запроса связей
        for entry in aup_data_entries:
            # Пропускаем записи без ID дисциплины, если такие есть
            if entry.id_discipline is None:
                print(f"Warning: Skipping AupData entry id {entry.id} for AUP {aup_id} due to missing discipline_id.")
                continue

            discipline_title = entry.unique_discipline.title if entry.unique_discipline else f"Discipline ID:{entry.id_discipline} (Not in Spr)"
            discipline_data = {
                "aup_data_id": entry.id,
                "discipline_id": entry.id_discipline,
                "title": discipline_title,
                "semester": entry.id_period
            }
            disciplines_list.append(discipline_data)
            aup_data_ids_in_matrix.add(entry.id)

        # 4. Получаем ВСЕ компетенции (УК, ОПК, ПК) и ИХ ИНДИКАТОРЫ, релевантные для ОП
        competencies_query = Competency.query.options(
            selectinload(Competency.indicators), # Загружаем индикаторы сразу
            joinedload(Competency.competency_type) # Загружаем тип компетенции
        )

        relevant_competencies = []
        # УК/ОПК из связанного ФГОС
        if fgos:
            # TODO: Раскомментировать, когда поле fgos_vo_id будет в модели Competency
            # relevant_competencies.extend(
            #     competencies_query.filter(
            #         Competency.fgos_vo_id == fgos.id,
            #         Competency.competency_type.has(CompetencyType.code.in_(['УК', 'ОПК']))
            #     ).all()
            # )
            # ВРЕМЕННО: Берем все УК/ОПК
             relevant_competencies.extend(
                competencies_query.join(CompetencyType).filter(
                    CompetencyType.code.in_(['УК', 'ОПК'])
                ).all()
            )
        else:
             print(f"Warning: No FGOS linked to Educational Program {program.id}. УК/ОПК might be missing.")
             # Если ФГОС не привязан, но УК/ОПК все равно нужно показать, убрать этот else

        # ПК, связанные с ОП
        # TODO: Определить точную логику связи ПК и ОП (через ПС? через EducationalProgram?)
        # Пока берем ВСЕ ПК для MVP
        relevant_competencies.extend(
            competencies_query.join(CompetencyType).filter(
                CompetencyType.code == 'ПК'
            ).all()
        )

        # Форматируем результат компетенций и индикаторов
        competencies_data = []
        indicator_ids_in_matrix = set() # Собираем ID всех релевантных индикаторов
        unique_competency_ids = set() # Чтобы избежать дубликатов компетенций

        for comp in relevant_competencies:
            if comp.id in unique_competency_ids:
                continue
            unique_competency_ids.add(comp.id)

            # Проверяем наличие competency_type перед доступом к code
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"

            comp_dict = comp.to_dict(rules=['-indicators', '-competency_type', '-fgos', '-based_on_labor_function']) # Убираем лишние связи
            comp_dict['type_code'] = type_code
            comp_dict['indicators'] = []
            if comp.indicators: # Проверяем, что список индикаторов не пуст
                for ind in sorted(comp.indicators, key=lambda i: i.code):
                    indicator_ids_in_matrix.add(ind.id)
                    comp_dict['indicators'].append(
                        ind.to_dict(only=('id', 'code', 'formulation', 'source_description'))
                    )
            competencies_data.append(comp_dict)

        # Сортируем итоговый список компетенций
        competencies_data.sort(key=lambda c: (c.get('type_code', ''), c.get('code', '')))

        # 5. Получаем существующие связи из CompetencyMatrix
        existing_links_data = []
        if aup_data_ids_in_matrix and indicator_ids_in_matrix:
            existing_links_db = CompetencyMatrix.query.filter(
                CompetencyMatrix.aup_data_id.in_(aup_data_ids_in_matrix),
                CompetencyMatrix.indicator_id.in_(indicator_ids_in_matrix)
            ).all()
            existing_links_data = [
                link.to_dict(only=('aup_data_id', 'indicator_id')) # Только нужные поля
                for link in existing_links_db
            ]

        # 6. Предложения от NLP (заглушка для MVP)
        suggestions_data = []

        # 7. Сборка итогового словаря
        return {
            "aup_info": aup_info.to_dict(rules=['-aup_data', '-department', '-faculty', '-form', '-degree', '-rop', '-name_op']), # Основные поля АУП
            "disciplines": disciplines_list,
            "competencies": competencies_data,
            "links": existing_links_data,
            "suggestions": suggestions_data
        }

    except SQLAlchemyError as e:
        print(f"Database error in get_matrix_for_aup for aup_id {aup_id}: {e}")
        # В реальном приложении - логирование ошибки
        return None
    except AttributeError as e:
        print(f"Attribute error likely due to missing relationship/data in get_matrix_for_aup for aup_id {aup_id}: {e}")
        # Часто возникает из-за отсутствия .unique_discipline или .competency_type
        return None
    except Exception as e:
        print(f"Unexpected error in get_matrix_for_aup for aup_id {aup_id}: {e}")
        # В реальном приложении - логирование полного traceback
        return None

# --- Функции для изменения данных ---

def update_matrix_link(aup_data_id: int, indicator_id: int, create: bool = True) -> bool:
    """
    Создает или удаляет связь Дисциплина(АУП)-ИДК в матрице.

    Args:
        aup_data_id: ID записи из таблицы aup_data.
        indicator_id: ID индикатора из таблицы indicators.
        create (bool): True для создания связи, False для удаления.

    Returns:
        bool: True в случае успеха, False если AupData или Indicator не найдены.
    """
    try:
        # 1. Проверяем, существуют ли AupData и Indicator
        #    Используем exists() для оптимизации - нам не нужны сами объекты
        aup_data_exists = db.session.query(AupData.id).filter_by(id=aup_data_id).first() is not None
        indicator_exists = db.session.query(Indicator.id).filter_by(id=indicator_id).first() is not None

        if not aup_data_exists:
            print(f"AupData entry with id {aup_data_id} not found.")
            return False
        if not indicator_exists:
            print(f"Indicator with id {indicator_id} not found.")
            return False

        # 2. Находим существующую связь (если она есть)
        existing_link = CompetencyMatrix.query.filter_by(
            aup_data_id=aup_data_id,
            indicator_id=indicator_id
        ).first()

        if create:
            # 3. Создаем, если связи нет
            if not existing_link:
                link = CompetencyMatrix(
                    aup_data_id=aup_data_id,
                    indicator_id=indicator_id
                    # TODO: Возможно, добавить is_manual=True и created_by=current_user.id
                )
                db.session.add(link)
                db.session.commit()
                print(f"Link created: AupData {aup_data_id} <-> Indicator {indicator_id}")
            else:
                print(f"Link already exists: AupData {aup_data_id} <-> Indicator {indicator_id}")
            return True
        else:
            # 4. Удаляем, если связь есть
            if existing_link:
                db.session.delete(existing_link)
                db.session.commit()
                print(f"Link deleted: AupData {aup_data_id} <-> Indicator {indicator_id}")
            else:
                 print(f"Link not found for deletion: AupData {aup_data_id} <-> Indicator {indicator_id}")
            return True

    except SQLAlchemyError as e:
        db.session.rollback() # Откатываем изменения в случае ошибки БД
        print(f"Database error in update_matrix_link: {e}")
        return False
    except Exception as e:
        db.session.rollback()
        print(f"Unexpected error in update_matrix_link: {e}")
        return False


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
