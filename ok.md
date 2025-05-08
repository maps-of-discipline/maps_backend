Окей, давайте разберем эти ошибки и внесем необходимые изменения в код, чтобы исправить их и улучшить процесс.

**1. Анализ Ошибок:**

*   **Ошибка `NameError: name 'db' is not defined`:** Это классическая ошибка, когда вы пытаетесь использовать объект `db` (инстанс SQLAlchemy) в файле, где он не был импортирован. Из traceback видно, что это происходит в `competencies_matrix/routes.py` и в `except` блоке этого же файла.
*   **Ошибка парсинга даты в CLI (`save_fgos_data: Failed to parse date '2020-08-07' into a Date object`):** Лог `save_fgos_data: Could not parse date '2020-08-07' in standard format. Attempting other formats.` показывает, что функция `save_fgos_data` пытается повторно парсить дату, которую `fgos_parser.py` уже успешно распарсил в объект `datetime.date` и положил в `parsed_data['metadata']['order_date']`. Проблема в том, что `save_fgos_data` сейчас не использует этот объект напрямую, а пытается снова парсить строку, которая уже не в том формате, который она ожидает для повторного парсинга ('DD.MM.YYYY').

**2. План Действий:**

1.  **Исправить `NameError` в `routes.py`:** Добавить импорт `db` в начало `routes.py`.
2.  **Исправить парсинг даты в `save_fgos_data`:** Изменить логику в `save_fgos_data`, чтобы она правильно использовала *уже распарсенный* объект `datetime.date` из `parsed_data`, а если получает строку (как из JSON от фронтенда), то парсила ее в стандартном ISO-формате ('YYYY-MM-DD').
3.  **Улучшить `seed_db`:** Добавить в сидер тестовые данные для ФГОС, УК, ОПК, ИУК, ИОПК, ПС (с базовой структурой ОТФ/ТФ) и связей между ними, чтобы эти справочники были наполнены для тестирования.
4.  **Обновить `tasks.md`:** Отметить выполненные задачи и уточнить описание оставшихся.

**3. Внедрение Изменений в Код:**

---

```python
# filepath: /home/me/ВКР/maps_backend/competencies_matrix/routes.py
# Маршруты (API endpoints) для модуля матрицы компетенций.
# Здесь определены все API-точки входа для работы с матрицами компетенций,
# образовательными программами, ФГОС, профстандартами и т.д.

from flask import request, jsonify, abort
# --- ИМПОРТ db ИЗ maps.models ---
from maps.models import db # !!! ИСПРАВЛЕНИЕ: Импортируем объект db
# --------------------------------
from .logic import (
    get_educational_programs_list, get_program_details, 
    get_matrix_for_aup, update_matrix_link,
    create_competency, create_indicator,
    parse_fgos_file, save_fgos_data, get_fgos_list, get_fgos_details, delete_fgos
)
from auth.logic import login_required, approved_required, admin_only
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

# Группа эндпоинтов для работы с образовательными программами (ОП)
@competencies_matrix_bp.route('/programs', methods=['GET'])
@login_required
@approved_required
def get_programs():
    """Получение списка всех образовательных программ"""
    # Используем функцию из logic.py
    programs = get_educational_programs_list()
    
    # Сериализуем результат в список словарей
    # Используем метод to_dict из BaseModel
    result = [p.to_dict() for p in programs] # Используем .to_dict(), а не .to_dict(rules=...) для базовых полей
    
    return jsonify(result)

@competencies_matrix_bp.route('/programs/<int:program_id>', methods=['GET'])
@login_required
@approved_required
def get_program(program_id):
    """Получение детальной информации по образовательной программе (ОП)"""
    details = get_program_details(program_id)
    if not details:
        return jsonify({"error": "Образовательная программа не найдена"}), 404
        
    return jsonify(details)

# Группа эндпоинтов для работы с матрицей компетенций
@competencies_matrix_bp.route('/matrix/<int:aup_id>', methods=['GET'])
@login_required
@approved_required
def get_matrix(aup_id):
    """
    Получение данных для матрицы компетенций конкретного АУП.
    Этот эндпоинт возвращает все необходимые данные для отображения 
    и редактирования матрицы в UI: дисциплины, компетенции, индикаторы и их связи.
    """
    matrix_data = get_matrix_for_aup(aup_id)
    if not matrix_data:
        return jsonify({"error": "АУП не найден или не связан с образовательной программой"}), 404
        
    return jsonify(matrix_data)

@competencies_matrix_bp.route('/matrix/link', methods=['POST', 'DELETE'])
@login_required
@approved_required
def manage_matrix_link():
    """
    Создает или удаляет связь Дисциплина(АУП)-ИДК в матрице.
    Возвращает подробный статус операции вместе с соответствующим HTTP-кодом.
    """
    data = request.get_json()
    if not data or 'aup_data_id' not in data or 'indicator_id' not in data:
        abort(400, description="Отсутствуют обязательные поля: aup_data_id, indicator_id")

    aup_data_id = data['aup_data_id']
    indicator_id = data['indicator_id']
    is_creating = (request.method == 'POST')

    # Вызов функции логики, которая управляет транзакцией
    result = update_matrix_link(
        aup_data_id,
        indicator_id,
        create=is_creating
    )

    # Формируем ответ в зависимости от статуса результата
    if result['success']:
        if is_creating:
            if result['status'] == 'created':
                return jsonify({"status": "created", "message": "Связь успешно создана"}), 201
            elif result['status'] == 'already_exists':
                return jsonify({"status": "already_exists", "message": "Связь уже существует"}), 200
        else:  # DELETE
            if result['status'] == 'deleted':
                return jsonify({"status": "deleted", "message": "Связь успешно удалена"}), 200
            elif result['status'] == 'not_found':
                return jsonify({"status": "not_found", "message": "Связь для удаления не найдена"}), 404
    else:  # Обработка ошибок
        # Обработка ошибок из логики, которая уже сделала rollback
        error_msg = "Не удалось выполнить операцию"
        status_code = 400
        
        if result.get('error_type') == 'aup_data_not_found':
            error_msg = f"Запись AupData (id: {aup_data_id}) не найдена"
            status_code = 404
        elif result.get('error_type') == 'indicator_not_found':
            error_msg = f"Индикатор (id: {indicator_id}) не найден"
            status_code = 404
        elif result.get('error_type') == 'database_error':
            error_msg = "Ошибка базы данных при выполнении операции"
            status_code = 500
        # Логирование ошибки уже есть в update_matrix_link
        
        return jsonify({"status": "error", "message": error_msg}), status_code

# Группа эндпоинтов для работы с компетенциями и индикаторами
@competencies_matrix_bp.route('/competencies', methods=['POST'])
@login_required
@approved_required
# @admin_only # Создание ПК может быть доступно методистам
def create_new_competency():
    """
    Создание новой компетенции (обычно ПК на основе профстандарта).
    Принимает JSON с полями компетенции:
    - type_code: Код типа (УК, ОПК, ПК)
    - code: Код компетенции (ПК-1, ...)
    - name: Формулировка компетенции
    - based_on_labor_function_id: (опционально) ID трудовой функции из ПС
    - fgos_vo_id: (опционально) ID ФГОС ВО
    """
    data = request.get_json()
    
    # Проверка необходимых полей
    if not data or 'type_code' not in data or 'code' not in data or 'name' not in data:
        return jsonify({"error": "Отсутствуют обязательные поля"}), 400
    
    # Вызов функции логики, которая управляет транзакцией
    result = create_competency(data) # create_competency возвращает словарь {success, status, message, competency?}
    
    if result['success']:
        # Возвращаем созданный объект и статус 201 Created
        return jsonify(result.get('competency')), 201
    else:
        # Обработка ошибок из логики
        error_msg = result.get('message', "Не удалось создать компетенцию")
        status_code = 400 # По умолчанию 400 Bad Request
        if result.get('error_type') == 'type_not_found' or result.get('error_type') == 'parent_not_found':
            status_code = 404 # Ресурс не найден
        elif result.get('error_type') == 'already_exists':
            status_code = 409 # Конфликт (уже существует)
        elif result.get('error_type') == 'database_error':
            status_code = 500 # Ошибка БД
        
        return jsonify({"error": error_msg}), status_code


@competencies_matrix_bp.route('/indicators', methods=['POST'])
@login_required
@approved_required
# @admin_only # Создание индикаторов доступно методистам
def create_new_indicator():
    """
    Создание нового индикатора достижения компетенции (ИДК).
    Принимает JSON с полями:
    - competency_id: ID родительской компетенции
    - code: Код индикатора (ИУК-1.1, ИОПК-2.3, ИПК-3.2 и т.д.)
    - formulation: Формулировка индикатора
    - source: (опционально) Описание источника (имя поля изменено на 'source')
    - labor_function_ids: (опционально) Список ID трудовых функций
    """
    data = request.get_json()
    
    # Проверка необходимых полей
    if not data or 'competency_id' not in data or 'code' not in data or 'formulation' not in data:
        return jsonify({"error": "Отсутствуют обязательные поля"}), 400
    
    # Вызов функции логики, которая управляет транзакцией
    result = create_indicator(data) # create_indicator возвращает словарь {success, status, message, indicator?}
    
    if result['success']:
        # Возвращаем созданный объект и статус 201 Created
        return jsonify(result.get('indicator')), 201
    else:
        # Обработка ошибок из логики
        error_msg = result.get('message', "Не удалось создать индикатор")
        status_code = 400 # По умолчанию 400 Bad Request
        if result.get('error_type') == 'parent_competency_not_found':
            status_code = 404 # Родительская компетенция не найдена
        elif result.get('error_type') == 'already_exists':
            status_code = 409 # Конфликт (уже существует)
        elif result.get('error_type') == 'database_error':
            status_code = 500 # Ошибка БД
        
        return jsonify({"error": error_msg}), status_code


# --- Новая группа эндпоинтов для работы с ФГОС ВО ---
@competencies_matrix_bp.route('/fgos', methods=['GET'])
@login_required
@approved_required
# @admin_only # Возможно, просмотр доступен не только админам, но и методистам
def get_all_fgos():
    """Получение списка всех загруженных ФГОС ВО"""
    fgos_list = get_fgos_list()
    # Сериализуем результат в список словарей
    # Используем to_dict из BaseModel
    result = [f.to_dict() for f in fgos_list]
    return jsonify(result)

@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['GET'])
@login_required
@approved_required
# @admin_only # Просмотр деталей тоже может быть шире
def get_fgos_details_route(fgos_id):
    """Получение детальной информации по ФГОС ВО"""
    details = get_fgos_details(fgos_id)
    if not details:
        return jsonify({"error": "ФГОС ВО не найден"}), 404
    return jsonify(details)

@competencies_matrix_bp.route('/fgos/upload', methods=['POST'])
@login_required
@approved_required
@admin_only # Загрузка и парсинг нового ФГОС - действие администратора
def upload_fgos():
    """
    Загрузка PDF файла ФГОС ВО, парсинг и возврат данных для предпросмотра.
    Не сохраняет данные в БД автоматически.
    Принимает multipart/form-data с полем 'file'.
    """
    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден в запросе"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Файл не выбран"}), 400

    # TODO: Добавить проверку расширения файла на .pdf
    
    try:
        file_bytes = file.read()
        
        # Вызываем парсер ФГОС
        parsed_data = parse_fgos_file(file_bytes, file.filename)

        if not parsed_data or not parsed_data.get('metadata'):
            # Если парсер не вернул данные или вернул без метаданных, считаем ошибкой парсинга
            return jsonify({"error": parsed_data.get('message', "Не удалось распарсить файл ФГОС или извлечь основные данные")}), 400

        # TODO: Добавить в ответ информацию о существующем ФГОС, если найден (для сравнения на фронтенде)
        # Можно вызвать get_fgos_details, если найден ФГОС с такими же ключевыми параметрами
        # Для этого нужно распарсить ключевые метаданные и сделать поиск в БД
        # Логика поиска дублирует начало save_fgos_data. Можно вынести в отдельную функцию логики.
        
        return jsonify(parsed_data), 200 # Возвращаем парсенные данные

    except Exception as e:
        logger.error(f"Error processing FGOS upload for {file.filename}: {e}", exc_info=True)
        # Если произошла ошибка на уровне парсинга (не ValueError из парсера), скорее всего, проблема в коде
        # or related libraries (e.g., pdfminer)
        return jsonify({"error": f"Ошибка сервера при обработке файла: {e}"}), 500


@competencies_matrix_bp.route('/fgos/save', methods=['POST'])
@login_required
@approved_required
@admin_only # Сохранение ФГОС - действие администратора
def save_fgos():
    """
    Сохранение структурированных данных ФГОС в БД после подтверждения пользователя.
    Принимает JSON с парсенными данными и опциями.
    """
    data = request.get_json()
    # Ожидаем JSON: {'parsed_data': {...}, 'filename': '...', 'options': {'force_update': true/false}}
    
    parsed_data = data.get('parsed_data')
    filename = data.get('filename')
    options = data.get('options', {})
    
    if not parsed_data or not filename:
        return jsonify({"error": "Некорректные данные для сохранения"}), 400

    # Вызываем функцию сохранения данных. Она сама управляет транзакцией.
    result = save_fgos_data(
        parsed_data=parsed_data, 
        filename=filename, 
        # Передаем сессию, как это было в логике.
        # !!! ИСПРАВЛЕНИЕ: Передаем сессию из контекста Flask.
        session=db.session, 
        # -------------------------------------------------
        force_update=options.get('force_update', False)
    )

    # save_fgos_data теперь возвращает словарь {success, message, fgos_id?}
    if result['success']:
        # Возвращаем ID сохраненного/обновленного ФГОС
        return jsonify({"success": True, "fgos_id": result.get('fgos_id'), "message": result.get('message')}), 201
    else:
        # Ошибка сохранения (ошибка БД, валидации данных перед сохранением и т.д.)
        # Логирование ошибки уже есть в save_fgos_data
        return jsonify({"success": False, "error": result.get('message', 'Ошибка при сохранении данных ФГОС')}), 500

@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only # Удаление ФГОС - действие администратора
def delete_fgos_route(fgos_id):
    """Удаление ФГОС ВО по ID"""
    try:
        # Вызываем функцию логики, которая управляет транзакцией
        deleted = delete_fgos(fgos_id, db.session)
        if deleted:
            return jsonify({"success": True, "message": "ФГОС успешно удален"}), 200
        else:
            # Если функция вернула False, значит объект не найден (уже залогировано в логике)
            return jsonify({"success": False, "error": "ФГОС не найден или не удалось удалить"}), 404

    except Exception as e:
        logger.error(f"Error deleting FGOS {fgos_id}: {e}", exc_info=True)
        # Если ошибка не поймана в логике (что маловероятно), откатываем здесь
        db.session.rollback()
        return jsonify({"success": False, "error": f"Неожиданная ошибка сервера при удалении: {e}"}), 500


# Группа эндпоинтов для работы с профессиональными стандартами (ПС)
@competencies_matrix_bp.route('/profstandards/upload', methods=['POST'])
@login_required
@approved_required
# @admin_only # Загрузка ПС может быть доступна методистам
def upload_profstandard():
    """
    Загрузка файла профессионального стандарта (HTML/Markdown).
    Парсит и сохраняет в БД профстандарт и его структуру (базово).
    Принимает multipart/form-data с файлом.
    """
    # from .logic import parse_prof_standard_file as parse_prof_standard_logic_function # Переименована в save_prof_standard_from_file
    from .logic import save_prof_standard_from_file

    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден в запросе"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Файл не выбран"}), 400
    
    # Читаем содержимое файла в байтах
    file_bytes = file.read()

    # Вызываем функцию логики, которая парсит и сохраняет
    result = save_prof_standard_from_file(file_bytes, file.filename)
    
    # save_prof_standard_from_file возвращает словарь {success, message, prof_standard_id?}
    if result.get('success'):
        return jsonify(result), 201 # 201 Created
    else:
        return jsonify(result), 400 # 400 Bad Request (или 500, если ошибка сервера/БД)


# Дальнейшие эндпоинты можно добавить по мере необходимости:
# - CRUD для образовательных программ
# - Управление связями ОП-АУП и ОП-ПС
# - API для NLP-модуля
# - Генерация отчетов
# - и т.д.
```

```python
# filepath: /home/me/ВКР/maps_backend/competencies_matrix/logic.py
# competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
from sqlalchemy.orm import joinedload, selectinload, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError # Импортируем IntegrityError
from sqlalchemy import exists, and_
import traceback
# Импортируем парсер ФГОС
from .fgos_parser import parse_fgos_pdf, parse_uk_opk_simple # parse_uk_opk_simple тоже может пригодиться в будущем сидере
# Импортируем парсер ПС
from .parsers import parse_prof_standard_upload # Переименовал для ясности
# Импортируем модели ПС, если они не импортируются автоматически через BaseModel или другие связи
from .models import (
    GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
)

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
        logger.error(f"Database error in get_educational_programs_list: {e}", exc_info=True) # Добавлено exc_info
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
        session: Session = db.session # Используем сессию
        program = session.query(EducationalProgram).options( # Используем session.query
            # Эффективно загружаем связанные данные одним запросом
            selectinload(EducationalProgram.fgos),
            selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
            selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard)
        ).get(program_id)

        if not program:
            logger.warning(f"Program with id {program_id} not found for details.")
            return None

        # Сериализуем программу основные поля без связей
        details = program.to_dict() # Используем to_dict из BaseModel

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
                            'name': assoc.prof_standard.name,
                            'is_mandatory': assoc.is_mandatory, # Добавляем метаданные связи
                            'description': assoc.description,
                        })
                    
        details['recommended_ps_list'] = recommended_ps_list

        return details
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_program_details for program_id {program_id}: {e}", exc_info=True)
        return None
    except AttributeError as e: # Может быть при неполноте данных (например, AUP_assoc, но AUP==None)
        logger.error(f"Attribute error likely due to missing relationship/data in get_program_details for program_id {program_id}: {e}", exc_info=True)
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
            selectinload(AupInfo.education_programs_assoc).selectinload(EducationalProgramAup.educational_program).selectinload(EducationalProgram.fgos) # Загружаем FGOS через ОП
        ).get(aup_id)

        if not aup_info:
            logger.warning(f"AUP with id {aup_id} not found for matrix.")
            return None

        # 2. Находим связанную ОП и ФГОС
        program = None
        fgos = None
        if aup_info.education_programs_assoc:
             # Предполагаем, что AUP связан только с одной ОП в контексте матрицы
             # TODO: Уточнить логику, если AUP связан с несколькими ОП
             program_assoc = aup_info.education_programs_assoc[0]
             program = program_assoc.educational_program
             if program and program.fgos:
                  fgos = program.fgos # FGOS уже загружен благодаря selectinload

        if not program:
             logger.warning(f"AUP {aup_id} is not linked to any Educational Program.")
             # TODO: Если АУП не связан с ОП, что показываем? Пустую матрицу? Ошибку?
             # Пока возвращаем None, чтобы фронтенд показал ошибку.
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
            # Пропускаем записи без привязки к дисциплине (например, служебные строки)
            if entry.id_discipline is None or entry.discipline is None:
                continue
            
            # TODO: Возможно, добавить фильтрацию по типам записей AupData (только Дисциплины)
            # if entry.id_type_record != 1: # 1 - Дисциплина, нужно уточнить ID в справочнике D_TypeRecord
            #     continue

            discipline_title = entry.discipline.title
            discipline_data = {
                "aup_data_id": entry.id,
                "discipline_id": entry.id_discipline,
                "title": discipline_title,
                "semester": entry.id_period # Семестр хранится в id_period AupData
            }
            disciplines_list.append(discipline_data)
            aup_data_ids_in_matrix.add(entry.id)

        # Сортировка списка дисциплин уже сделана ORM по id_period и num_row, что обычно соответствует порядку в АУП
        # disciplines_list.sort(key=lambda d: (d.get('semester', 0), d.get('title', ''))) # На всякий случай можно оставить, но ORM должен справиться
        logger.info(f"Found {len(disciplines_list)} relevant AupData entries for AUP {aup_id}.")

        # 4. Получаем релевантные компетенции и их индикаторы
        # УК и ОПК берутся из ФГОС, связанного с ОП
        # ПК берутся из тех, что созданы пользователем и связаны с ОП
        
        relevant_competencies_query = session.query(Competency).options(
            selectinload(Competency.indicators),
            joinedload(Competency.competency_type)
        )

        relevant_competencies = []

        # Получаем УК и ОПК, связанные с данным ФГОС (если ФГОС есть)
        if fgos:
            uk_opk_competencies = relevant_competencies_query.filter(
                Competency.fgos_vo_id == fgos.id # Фильтруем по FK на ФГОС
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


        # Получаем ПК, связанные с данной ОП
        # Логика связи ПК с ОП: Компетенция (ПК) может быть создана на основе ТФ (LaborFunction).
        # LaborFunction принадлежит Профстандарту (ProfStandard).
        # Профстандарт может быть выбран для Образовательной Программы (EducationalProgramPs).
        # Поэтому, чтобы получить ПК для данной ОП, нужно найти все ТФ из ПС, выбранных для этой ОП,
        # и все ПК, основанные на этих ТФ.
        # Также, ПК могут быть созданы не на основе ТФ, а просто вручную и связаны с ОП напрямую (если такая связь есть в модели).
        # На данном этапе (MVP) временно берем ВСЕ ПК, т.к. логика связи ПК с ОП через ПС/ТФ еще не полностью реализована/верифицирована.
        
        # TODO: Реализовать правильную фильтрацию ПК по ОП
        # Вариант 1 (Если ПК напрямую связаны с ОП):
        # pk_competencies = relevant_competencies_query.join(EducationalProgramCompetency).filter(EducationalProgramCompetency.program_id == program.id).all()
        # Вариант 2 (Если ПК связаны через ТФ, ПС, ОП-ПС):
        # pk_competencies = relevant_competencies_query.join(LaborFunction).join(ProfStandard).join(EducationalProgramPs).filter(EducationalProgramPs.educational_program_id == program.id).all()
        # На данном этапе, берем все ПК:
        pk_competencies = relevant_competencies_query.join(CompetencyType).filter(CompetencyType.code == 'ПК').all()
        relevant_competencies.extend(pk_competencies)
        logger.info(f"Found {len(pk_competencies)} ПК competencies (all existing ПК).")


        # Форматируем результат
        competencies_data = []
        indicator_ids_in_matrix = set()
        
        # Сортируем релевантные компетенции перед форматированием
        # Сортировка: сначала УК, потом ОПК, потом ПК; внутри каждого типа - по коду
        type_order = ['УК', 'ОПК', 'ПК']
        relevant_competencies.sort(key=lambda c: (
            type_order.index(c.competency_type.code) if c.competency_type and c.competency_type.code in type_order else len(type_order), # Неизвестные типы в конец
            c.code
        ))

        for comp in relevant_competencies:
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"

            # Используем .to_dict() из BaseModel для сериализации полей
            comp_dict = comp.to_dict()
            comp_dict.pop('fgos', None) # Удаляем объект Fgos
            comp_dict.pop('competency_type', None) # Удаляем объект CompetencyType
            comp_dict.pop('based_on_labor_function', None) # Удаляем объект LaborFunction
            comp_dict.pop('matrix_links', None) # Удаляем связи матрицы, они в отдельном массиве

            comp_dict['type_code'] = type_code # Добавляем код типа явно
            comp_dict['indicators'] = []
            if comp.indicators:
                # Сортируем индикаторы внутри компетенции
                sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                for ind in sorted_indicators:
                    indicator_ids_in_matrix.add(ind.id)
                    # Сериализуем индикатор
                    ind_dict = ind.to_dict()
                    ind_dict.pop('competency', None) # Удаляем родительскую компетенцию
                    ind_dict.pop('labor_functions', None) # Удаляем связанные ТФ
                    ind_dict.pop('matrix_entries', None) # Удаляем связи матрицы
                    comp_dict['indicators'].append(ind_dict)
            competencies_data.append(comp_dict)

        logger.info(f"Formatted {len(competencies_data)} relevant competencies with indicators.")

        # 5. Получаем существующие связи
        existing_links_data = []
        # Проверяем, что списки ID не пустые, чтобы избежать ошибки .in_([])
        if aup_data_ids_in_matrix and indicator_ids_in_matrix:
            # Используем .in_() для эффективного запроса
            existing_links_db = session.query(CompetencyMatrix).filter(
                and_(
                   CompetencyMatrix.aup_data_id.in_(list(aup_data_ids_in_matrix)), # Преобразуем set в list
                   CompetencyMatrix.indicator_id.in_(list(indicator_ids_in_matrix)) # Преобразуем set в list
                )
            ).all()
            # Сериализуем связи
            existing_links_data = [
                link.to_dict() for link in existing_links_db # Используем to_dict из BaseModel
            ]
            logger.info(f"Found {len(existing_links_data)} existing matrix links for relevant AupData and Indicators.")


        # 6. Предложения от NLP (заглушка для MVP)
        # suggestions_data = suggest_links_nlp(disciplines_list, competencies_data) # Заглушка

        # Сериализуем AupInfo в конце
        aup_info_dict = aup_info.as_dict() # Используем as_dict из maps.models.py
        # Удаляем relation properties, если они есть в as_dict
        aup_info_dict.pop('education_programs_assoc', None)
        # Добавляем num_aup если он не попал в as_dict (хотя должен)
        # if 'num_aup' not in aup_info_dict and hasattr(aup_info, 'num_aup'):
        #      aup_info_dict['num_aup'] = aup_info.num_aup


        return {
            "aup_info": aup_info_dict,
            "disciplines": disciplines_list,
            "competencies": competencies_data,
            "links": existing_links_data,
            "suggestions": [] # Заглушка для NLP
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
                'details': '...' (опционально, детали ошибки),
                'link_id': '...' (ID созданной связи, если 'created')
            }
    """
    session: Session = db.session
    try:
        # 1. Проверяем существование AupData и Indicator более эффективно
        # Используем AND для комбинации условий в одном exists() запросе, если возможно
        # Или делаем два отдельных запроса для более точной диагностики ошибки 404
        
        # Оптимизированная проверка существования AupData и Indicator в одном запросе (если возможно)
        # Или делаем два запроса, чтобы точно знать, какой ID не найден
        aup_data_rec = session.query(AupData).get(aup_data_id)
        if not aup_data_rec:
             message = f"update_matrix_link: AupData entry with id {aup_data_id} not found."
             logger.warning(message)
             return {
                 'success': False,
                 'status': 'error',
                 'message': message,
                 'error_type': 'aup_data_not_found'
             }

        indicator_rec = session.query(Indicator).get(indicator_id)
        if not indicator_rec:
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
                session.commit() # Коммит после успешного добавления
                message = f"Link created: AupData {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return {
                    'success': True,
                    'status': 'created',
                    'message': message,
                    'link_id': link.id # Возвращаем ID созданной связи
                }
            else:
                message = f"Link already exists: AupData {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                # Не нужно коммитить, т.к. ничего не меняли
                return {
                    'success': True,
                    'status': 'already_exists',
                    'message': message,
                    'link_id': existing_link.id # Возвращаем ID существующей связи
                }
        else: # delete
            if existing_link:
                session.delete(existing_link)
                session.commit() # Коммит после успешного удаления
                message = f"Link deleted: AupData {aup_data_id} <-> Indicator {indicator_id}"
                logger.info(message)
                return {
                    'success': True, # Вернем success=True, т.к. цель (отсутствие связи) достигнута
                    'status': 'deleted',
                    'message': message
                }
            else:
                message = f"Link not found for deletion: AupData {aup_data_id} <-> Indicator {indicator_id}"
                logger.warning(message)
                # Не нужно коммитить
                return {
                    'success': True, # Вернем success=True, т.к. цель (отсутствие связи) достигнута
                    'status': 'not_found',
                    'message': message
                }

    except SQLAlchemyError as e:
        session.rollback() # Откат при ошибке БД
        message = f"Database error in update_matrix_link: {e}"
        logger.error(message, exc_info=True)
        return {
            'success': False,
            'status': 'error',
            'message': message,
            'error_type': 'database_error'
        }
    except Exception as e:
        session.rollback() # Откат при любой другой ошибке
        message = f"Unexpected error in update_matrix_link: {e}"
        logger.error(message, exc_info=True)
        return {
            'success': False,
            'status': 'error',
            'message': message,
            'error_type': 'unexpected_error',
            'details': str(e)
        }


def create_competency(data: Dict[str, Any]) -> Dict[str, Any]: # Изменен возвращаемый тип
    """
    Создает новую компетенцию (обычно ПК). Базовая реализация для MVP.

    Args:
        data: Словарь с данными {'type_code': 'ПК', 'code': 'ПК-1', 'name': '...', ...}.

    Returns:
        Dict[str, Any]: Словарь с результатом операции:
            {
                'success': True/False,
                'status': 'created'/'already_exists'/'error',
                'message': '...',
                'error_type': '...',
                'competency': {...} (созданный объект в словаре, если success=True)
            }
    """
    # TODO: Добавить валидацию входных данных (через schemas.py)
    required_fields = ['type_code', 'code', 'name']
    if not all(field in data and data[field] is not None for field in required_fields): # Проверяем на None тоже
        message = "Отсутствуют обязательные поля: type_code, code, name"
        logger.warning(message)
        return {'success': False, 'status': 'error', 'message': message, 'error_type': 'missing_fields'}

    session: Session = db.session
    try:
        # Проверяем тип компетенции
        comp_type_code = data['type_code'].upper() # Приводим к верхнему регистру
        comp_type = session.query(CompetencyType).filter_by(code=comp_type_code).first()
        if not comp_type:
            message = f"Тип компетенции с кодом '{comp_type_code}' не найден в базе данных."
            logger.warning(message)
            return {'success': False, 'status': 'error', 'message': message, 'error_type': 'type_not_found'}

        # Проверка на уникальность кода компетенции в рамках типа и/или родителя (ФГОС/ТФ)
        # Для УК/ОПК - уникален в рамках ФГОС (если fgos_vo_id предоставлен)
        # Для ПК - уникален в рамках ТФ (если based_on_labor_function_id предоставлен)
        # Если родитель не предоставлен, уникален только по коду и типу.
        # MVP: Проверка уникальности кода в рамках типа и опционально родителя.
        
        existing_comp_query = session.query(Competency).filter_by(
             code=data['code'],
             competency_type_id=comp_type.id
        )
        
        # Добавляем фильтр по родителю, если он предоставлен
        if data.get('fgos_vo_id') is not None:
            existing_comp_query = existing_comp_query.filter_by(fgos_vo_id=data['fgos_vo_id'])
        elif data.get('based_on_labor_function_id') is not None:
            existing_comp_query = existing_comp_query.filter_by(based_on_labor_function_id=data['based_on_labor_function_id'])

        existing_comp = existing_comp_query.first()

        if existing_comp:
             message = f"Компетенция с кодом '{data['code']}' и типом '{comp_type_code}' уже существует."
             # TODO: Уточнить сообщение, если есть родитель (ФГОС/ТФ)
             logger.warning(message)
             return {'success': False, 'status': 'already_exists', 'message': message, 'error_type': 'already_exists'}

        # Проверяем существование родительских сущностей, если ID предоставлены
        if data.get('fgos_vo_id') is not None:
            fgos = session.query(FgosVo).get(data['fgos_vo_id'])
            if not fgos:
                 message = f"Указанный ФГОС с id {data['fgos_vo_id']} не найден."
                 logger.warning(message)
                 return {'success': False, 'status': 'error', 'message': message, 'error_type': 'parent_not_found', 'parent_type': 'fgos_vo'}
        
        if data.get('based_on_labor_function_id') is not None:
            tf = session.query(LaborFunction).get(data['based_on_labor_function_id'])
            if not tf:
                 message = f"Указанная Трудовая Функция с id {data['based_on_labor_function_id']} не найдена."
                 logger.warning(message)
                 return {'success': False, 'status': 'error', 'message': message, 'error_type': 'parent_not_found', 'parent_type': 'labor_function'}


        # Создаем компетенцию
        competency = Competency(
            competency_type_id=comp_type.id,
            code=data['code'],
            name=data['name'],
            description=data.get('description'),
            fgos_vo_id=data.get('fgos_vo_id'), # Связываем с ФГОС, если ID предоставлен
            based_on_labor_function_id=data.get('based_on_labor_function_id') # Связываем с ТФ, если ID предоставлен
        )
        session.add(competency)
        session.commit() # Коммит после успешного добавления
        logger.info(f"Competency created: {competency.code} (ID: {competency.id})")
        
        # Возвращаем созданный объект в виде словаря
        return {'success': True, 'status': 'created', 'message': 'Компетенция успешно создана', 'competency': competency.to_dict()}

    except IntegrityError as e:
        session.rollback()
        message = f"Ошибка уникальности при создании компетенции: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'status': 'error', 'message': message, 'error_type': 'integrity_error'}
    except SQLAlchemyError as e:
        session.rollback()
        message = f"Ошибка базы данных при создании компетенции: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'status': 'error', 'message': message, 'error_type': 'database_error'}
    except Exception as e:
        session.rollback()
        message = f"Неожиданная ошибка при создании компетенции: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'status': 'error', 'message': message, 'error_type': 'unexpected_error', 'details': str(e)}


def create_indicator(data: Dict[str, Any]) -> Dict[str, Any]: # Изменен возвращаемый тип
    """
    Создает новый индикатор (ИДК). Базовая реализация для MVP.

    Args:
        data: Словарь с данными {'competency_id': ..., 'code': 'ИПК-1.1', 'formulation': '...', ...}

    Returns:
        Dict[str, Any]: Словарь с результатом операции:
            {
                'success': True/False,
                'status': 'created'/'already_exists'/'error',
                'message': '...',
                'error_type': '...',
                'indicator': {...} (созданный объект в словаре, если success=True)
            }
    """
    # TODO: Добавить валидацию входных данных
    required_fields = ['competency_id', 'code', 'formulation']
    if not all(field in data and data[field] is not None for field in required_fields): # Проверяем на None тоже
        message = "Отсутствуют обязательные поля: competency_id, code, formulation"
        logger.warning(message)
        return {'success': False, 'status': 'error', 'message': message, 'error_type': 'missing_fields'}

    session: Session = db.session
    try:
        # Проверяем существование родительской компетенции
        competency = session.query(Competency).get(data['competency_id'])
        if not competency:
            message = f"Родительская компетенция с id {data['competency_id']} не найдена."
            logger.warning(message)
            return {'success': False, 'status': 'error', 'message': message, 'error_type': 'parent_competency_not_found'}

        # Проверка на уникальность кода индикатора в рамках компетенции
        existing_indicator = session.query(Indicator).filter_by(
             code=data['code'],
             competency_id=data['competency_id']
        ).first()
        if existing_indicator:
             message = f"Индикатор с кодом '{data['code']}' для компетенции {data['competency_id']} уже существует."
             logger.warning(message)
             return {'success': False, 'status': 'already_exists', 'message': message, 'error_type': 'already_exists'}

        indicator = Indicator(
            competency_id=data['competency_id'], # Связываем по ID
            code=data['code'],
            formulation=data['formulation'],
            source=data.get('source') # Используем поле 'source'
        )
        session.add(indicator)
        session.commit() # Коммит после успешного добавления
        logger.info(f"Indicator created: {indicator.code} (ID: {indicator.id}) for competency {indicator.competency_id}")

        # TODO: Реализовать сохранение связей с ПС (IndicatorPsLink)
        # data.get('labor_function_ids') - список ID ТФ
        # Нужно найти эти ТФ и создать записи в IndicatorPsLink
        # if data.get('labor_function_ids') and isinstance(data['labor_function_ids'], list):
        #     labor_functions = session.query(LaborFunction).filter(LaborFunction.id.in_(data['labor_function_ids'])).all()
        #     for tf in labor_functions:
        #         # Проверяем, нет ли уже такой связи
        #         existing_link = session.query(IndicatorPsLink).filter_by(
        #             indicator_id=indicator.id,
        #             labor_function_id=tf.id
        #         ).first()
        #         if not existing_link:
        #             link = IndicatorPsLink(
        #                 indicator_id=indicator.id,
        #                 labor_function_id=tf.id,
        #                 is_manual=True # Связь установлена вручную при создании индикатора
        #                 # relevance_score = ... # Возможно, задается пользователем?
        #             )
        #             session.add(link)
        #     session.commit() # Коммит связей ПС

        # Возвращаем созданный объект в виде словаря
        return {'success': True, 'status': 'created', 'message': 'Индикатор успешно создан', 'indicator': indicator.to_dict()}

    except IntegrityError as e:
        session.rollback()
        message = f"Ошибка уникальности при создании индикатора: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'status': 'error', 'message': message, 'error_type': 'integrity_error'}
    except SQLAlchemyError as e:
        session.rollback()
        message = f"Ошибка базы данных при создании индикатора: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'status': 'error', 'message': message, 'error_type': 'database_error'}
    except Exception as e:
        session.rollback()
        message = f"Неожиданная ошибка при создании индикатора: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'status': 'error', 'message': message, 'error_type': 'unexpected_error', 'details': str(e)}


# --- Функции для работы с ФГОС ---

def parse_fgos_file(file_bytes: bytes, filename: str) -> Dict[str, Any]: # Возвращаемый тип изменен на Dict (т.к. ошибки ловятся внутри парсера)
    """
    Оркестрирует парсинг загруженного файла ФГОС ВО.

    Args:
        file_bytes: Содержимое PDF файла в байтах.
        filename: Имя файла.

    Returns:
        Dict[str, Any]: Структурированные данные ФГОС или raise ValueError/Exception в случае ошибки парсинга.
                        В случае успеха всегда возвращает словарь с ключом 'metadata'.
    """
    # parse_fgos_pdf сам обрабатывает ошибки парсинга и логирует их, выбрасывая ValueError или Exception
    # Мы просто вызываем его.
    parsed_data = parse_fgos_pdf(file_bytes, filename)
    
    # Если parse_fgos_pdf не выбросил исключение, значит базовый парсинг прошел успешно.
    # Возвращаем результат.
    # Проверка на неполные данные (нет метаданных или компетенций) уже есть внутри parse_fgos_pdf.
    
    return parsed_data


def save_fgos_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Dict[str, Any]: # Изменен возвращаемый тип
    """
    Сохраняет структурированные данные ФГОС из парсера в БД.
    Обрабатывает обновление существующих записей (FgosVo, Competency, Indicator).
    Управляет своей транзакцией.

    Args:
        parsed_data: Структурированные данные, полученные от parse_fgos_file.
        filename: Имя исходного файла (для сохранения пути).
        session: Сессия SQLAlchemy.
        force_update: Если True, удаляет старый ФГОС и связанные сущности перед сохранением нового.

    Returns:
        Dict[str, Any]: Словарь с результатом операции:
            {
                'success': True/False,
                'message': '...',
                'fgos_id': '...' (ID сохраненного/обновленного FgosVo, если success=True),
                'error_type': '...' (опционально)
            }
    """
    if not parsed_data or not parsed_data.get('metadata'):
        message = "Некорректные или пустые данные для сохранения ФГОС."
        logger.warning(message)
        # Не нужен rollback, если данные даже не начали обрабатываться
        return {'success': False, 'message': message, 'error_type': 'invalid_data'}

    metadata = parsed_data['metadata']
    fgos_number = metadata.get('order_number')
    # !!! ИСПРАВЛЕНИЕ: Используем распарсенный объект date напрямую, если он есть
    fgos_date_obj = metadata.get('order_date') # <-- Теперь это объект Date из парсера
    # ------------------------------------------------------------------------
    fgos_direction_code = metadata.get('direction_code')
    fgos_education_level = metadata.get('education_level')
    fgos_generation = metadata.get('generation')
    fgos_direction_name = metadata.get('direction_name')
    # TODO: Добавить другие поля метаданных, если извлекаются парсером (metadata['order_info']?)

    # Проверка на обязательные метаданные (уже должна быть в парсере, но на всякий случай)
    if not fgos_number or fgos_date_obj is None or not fgos_direction_code or not fgos_education_level:
        message = "Отсутствуют обязательные метаданные ФГОС (номер, дата, код направления, уровень)."
        logger.error(message)
        return {'success': False, 'message': message, 'error_type': 'missing_metadata'}

    # --- 1. Ищем существующий ФГОС ---
    # Считаем ФГОС уникальным по комбинации код направления + уровень + номер + дата
    existing_fgos = session.query(FgosVo).filter_by(
        direction_code=fgos_direction_code,
        education_level=fgos_education_level,
        number=fgos_number,
        date=fgos_date_obj # Сравниваем с объектом Date
    ).first()

    fgos_id_to_return = None # Для возврата ID нового или существующего ФГОС

    if existing_fgos:
        if force_update:
            logger.info(f"save_fgos_data: Existing FGOS found ({existing_fgos.id}, code: {existing_fgos.direction_code}). Force update requested. Deleting old...")
            # Удаляем старый ФГОС и все связанные сущности (благодаря CASCADE DELETE)
            try:
                session.delete(existing_fgos)
                # Не коммитим здесь. Коммит будет в конце вместе с новым сохранением.
                logger.info(f"save_fgos_data: Old FGOS ({existing_fgos.id}) marked for deletion.")
                # Сохраняем ID, если нам нужно вернуть ID нового ФГОС после сохранения
                fgos_id_to_return = existing_fgos.id # Сохраняем старый ID, чтобы, возможно, новый объект занял его место (или просто возвращаем новый ID)
            except SQLAlchemyError as e:
                session.rollback() # Откат при ошибке БД во время удаления
                message = f"Ошибка базы данных при удалении старого ФГОС {existing_fgos.id}: {e}"
                logger.error(message, exc_info=True)
                return {'success': False, 'message': message, 'error_type': 'database_error_deleting_old'}
        else:
            # Если не force_update и ФГОС существует, мы его не перезаписываем
            message = f"FGOS с тем же кодом, уровнем, номером и датой уже существует ({existing_fgos.id}). Обновление не затребовано (--force не установлен)."
            logger.warning(message)
            # Возвращаем существующий объект, чтобы фронтенд знал о дубликате
            # Возвращаем success=True, т.к. операция "сохранения" в некотором смысле завершилась успешно (мы убедились, что запись есть)
            # Но фронтенд должен интерпретировать status/message как "уже существует"
            return {'success': True, 'message': message, 'status': 'already_exists', 'fgos_id': existing_fgos.id}


    # --- 2. Создаем новый FgosVo (или обновляем существующий, если логика будет сложнее) ---
    try:
        # Создаем новый объект FgosVo
        fgos_vo = FgosVo(
            number=fgos_number,
            date=fgos_date_obj, # <-- Используем объект Date
            direction_code=fgos_direction_code,
            direction_name=fgos_direction_name or 'Не указано', # Используем извлеченное имя
            education_level=fgos_education_level,
            generation=fgos_generation,
            file_path=filename # Сохраняем имя файла
            # TODO: Добавить другие поля метаданных, если извлекаются парсером
        )
        session.add(fgos_vo)
        # Используем flush, чтобы получить ID нового ФГОС ДО коммита
        session.flush() 
        fgos_id_to_return = fgos_vo.id # Сохраняем ID нового объекта
        logger.info(f"save_fgos_data: New FgosVo object created/queued for {fgos_vo.direction_code} with ID {fgos_vo.id}.")

    except SQLAlchemyError as e:
        session.rollback() # Откат при ошибке БД при создании нового ФГОС
        message = f"Ошибка базы данных при создании объекта FgosVo: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'message': message, 'error_type': 'database_error_creating_new'}

    # --- 3. Сохраняем Компетенции и Индикаторы ---
    # Важно: На этом этапе мы сохраняем ТОЛЬКО УК/ОПК из ФГОС PDF.
    # Индикаторы для них (ИУК/ИОПК) должны приходить из Распоряжения 505-Р
    # и быть сидированы или загружены отдельно.
    # Если парсер ФГОС PDF находит индикаторы (старый код), они ИГНОРИРУЮТСЯ ЗДЕСЬ при сохранении.
    
    try:
        # Получаем типы компетенций (УК, ОПК) из БД (уже должны быть сидированы)
        comp_types = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}
        if not comp_types:
             session.rollback() # Откат, т.к. не можем сохранить компетенции без типов
             message = "Типы компетенций (УК, ОПК) не найдены в базе данных. Запустите seed_db!"
             logger.error(message)
             return {'success': False, 'message': message, 'error_type': 'missing_competency_types'}

        saved_competencies_count = 0
        # Объединяем УК и ОПК для итерации
        all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])

        for parsed_comp in all_parsed_competencies:
            comp_code = parsed_comp.get('code')
            comp_name = parsed_comp.get('name')
            # parsed_indicators = parsed_comp.get('indicators', []) # ИГНОРИРУЕМ индикаторы из PDF

            if not comp_code or not comp_name:
                logger.warning(f"save_fgos_data: Skipping competency due to missing code/name in parsed data: {parsed_comp}")
                continue

            comp_prefix = comp_code.split('-')[0].upper() # Убедимся, что префикс верхний регистр
            comp_type = comp_types.get(comp_prefix)

            if not comp_type:
                logger.warning(f"save_fgos_data: Skipping competency {comp_code}: Competency type {comp_prefix} not found in mapped types (expected UK/OPK).")
                continue
                
            # Проверяем, существует ли уже компетенция с таким кодом, привязанная к этому ФГОС
            # Это важно при force_update, чтобы не дублировать (хотя удаление старого ФГОС должно это предотвратить)
            # Если сработало - это либо баг в удалении, либо неполное удаление.
            # В этом случае, мы хотим убедиться, что не добавляем дубликат по unique constraint.
            # Добавляем явную проверку перед add().
            existing_comp = session.query(Competency).filter_by(
                 code=comp_code,
                 fgos_vo_id=fgos_vo.id # Проверяем привязку именно к новому/обновляемому ФГОС
            ).first()
            
            if existing_comp:
                 logger.warning(f"save_fgos_data: Competency {comp_code} already exists for FGOS {fgos_vo.id} before explicit add. This is unexpected. Skipping add.")
                 # TODO: Рассмотреть логику обновления существующей, если это нужно
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
            # Используем flush, чтобы получить ID компетенции ДО коммита (если нужно)
            # session.flush() 
            saved_competencies_count += 1

            # Индикаторы для этих УК/ОПК НЕ ПАРСЯТСЯ из PDF и НЕ СОХРАНЯЮТСЯ здесь.
            # Они должны быть добавлены в БД из Распоряжения 505-Р через seed_db или отдельный механизм.
            # Если они уже есть в БД и связаны с этим ФГОС/Компетенцией (по коду и родительскому ID),
            # то они будут доступны через relationship при получении деталей ФГОС/Компетенции.

        logger.info(f"save_fgos_data: Queued {saved_competencies_count} УК/ОПК competencies for saving.")

    except SQLAlchemyError as e:
        session.rollback() # Откат при ошибке БД при сохранении компетенций/индикаторов
        message = f"Ошибка базы данных при сохранении компетенций/индикаторов: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'message': message, 'error_type': 'database_error_saving_comp'}
    except Exception as e:
        session.rollback() # Откат при любой другой ошибке
        message = f"Неожиданная ошибка при сохранении компетенций/индикаторов: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'message': message, 'error_type': 'unexpected_error_saving_comp', 'details': str(e)}


    # --- 4. Сохраняем рекомендованные ПС ---
    # Сохраняем только связи FgosRecommendedPs с существующими ProfStandard в БД
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
                # Проверяем, существует ли уже эта связь ФГОС-ПС для данного ФГОС
                existing_link = session.query(FgosRecommendedPs).filter_by(
                    fgos_vo_id=fgos_vo.id, # Связываем с новым/обновляемым ФГОС
                    prof_standard_id=prof_standard.id
                ).first()
                
                if not existing_link:
                     # Создаем связь FgosRecommendedPs
                     link = FgosRecommendedPs(
                         fgos_vo_id=fgos_vo.id,
                         prof_standard_id=prof_standard.id,
                         is_mandatory=False # По умолчанию считаем рекомендованным (если парсер не извлек обязательность)
                         # description = ... # Если парсер найдет доп. описание связи
                     )
                     session.add(link)
                     linked_ps_count += 1
                     logger.debug(f"save_fgos_data: Queued link between FGOS {fgos_vo.id} and PS {prof_standard.code}.")
                else:
                     logger.warning(f"save_fgos_data: Link between FGOS {fgos_vo.id} and PS {prof_standard.code} already exists. Skipping creation.")

            else:
                # Если ПС с таким кодом не найден в нашей БД, мы не можем создать связь.
                # Это ожидаемая ситуация, если ПС еще не был загружен.
                logger.warning(f"save_fgos_data: Recommended PS with code {ps_code} not found in DB. Cannot create link for FGOS {fgos_vo.id}. Please upload this PS first.")

        logger.info(f"save_fgos_data: Queued {linked_ps_count} recommended PS links for saving.")

    except SQLAlchemyError as e:
        session.rollback() # Откат при ошибке БД при сохранении связей ПС
        message = f"Ошибка базы данных при сохранении связей рекомендованных ПС: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'message': message, 'error_type': 'database_error_saving_ps_links'}
    except Exception as e:
        session.rollback() # Откат при любой другой ошибке
        message = f"Неожиданная ошибка при сохранении связей рекомендованных ПС: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'message': message, 'error_type': 'unexpected_error_saving_ps_links', 'details': str(e)}


    # --- Финальный коммит ---
    try:
        session.commit()
        logger.info(f"save_fgos_data: Final commit successful for FGOS ID {fgos_id_to_return}.")
        # Возвращаем успех и ID сохраненного/обновленного ФГОС
        return {'success': True, 'message': 'Данные ФГОС успешно сохранены', 'fgos_id': fgos_id_to_return}
    except SQLAlchemyError as e:
        session.rollback() # Финальный откат, если коммит не удался
        message = f"Финальный коммит не удался при сохранении ФГОС ID {fgos_id_to_return}: {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'message': message, 'error_type': 'database_commit_error'}


def get_fgos_list() -> List[FgosVo]:
    """
    Получает список всех сохраненных ФГОС ВО.

    Returns:
        List[FgosVo]: Список объектов FgosVo.
    """
    try:
        session = db.session
        # Просто возвращаем все ФГОС, можно добавить сортировку/фильтры позже
        # Добавим eager loading для associated educational programs count (через relationship)
        # from sqlalchemy import func, select # Добавьте эти импорты, если используете subquery
        # from sqlalchemy.orm import column_property

        # TODO: добавить count_educational_programs = column_property(select(func.count(EducationalProgram.id)).where(EducationalProgram.fgos_vo_id == FgosVo.id).scalar_subquery()) in model?
        # Если поле count_educational_programs добавлено в модель FgosVo, оно будет загружено автоматически

        # Загружаем связи с ОП, чтобы отобразить их количество или первый АУП
        fgos_list = session.query(FgosVo).options(
             joinedload(FgosVo.educational_programs) # Загружаем связанные ОП
        ).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()
        
        # TODO: Возможно, добавить к каждому FgosVo информацию о количестве связанных ОП
        # or about the primary AUP of a primary linked program if needed for display
        
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
        session: Session = db.session
        # Нет необходимости получать новую сессию, если текущая закрыта в веб-приложении Flask
        # Сессия управляется контекстом запроса.

        fgos = session.query(FgosVo).options(
            # Загружаем связанные сущности
            # !!! ИСПРАВЛЕНИЕ: Загружаем индикаторы через компетенции
            selectinload(FgosVo.competencies).selectinload(Competency.indicators).joinedload(Indicator.competency_type), # Загружаем тип индикатора
            # !!! ИСПРАВЛЕНИЕ: Загружаем рекомендованные ПС
            selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard)
            # TODO: Загрузить связанные ОП, если нужно
            # selectinload(FgosVo.educational_programs)
        ).get(fgos_id)

        if not fgos:
            logger.warning(f"FGOS with id {fgos_id} not found for details.")
            return None

        # Сериализуем основной объект ФГОС
        details = fgos.to_dict()
        details['date'] = details['date'].isoformat() if details.get('date') else None # Форматируем дату

        # Сериализуем компетенции и индикаторы, связанные с этим ФГОС
        uk_competencies_data = []
        opk_competencies_data = []

        # Сортируем компетенции по коду
        sorted_competencies = sorted(fgos.competencies, key=lambda c: c.code)

        for comp in sorted_competencies:
            # Проверяем, что компетенция относится к этому ФГОС (уже гарантировано relationship)
            # и является УК/ОПК (они единственные напрямую связаны через fgos_vo_id)
            if comp.competency_type and comp.competency_type.code in ['УК', 'ОПК']:
                 # Используем .to_dict() из BaseModel для сериализации полей
                 comp_dict = comp.to_dict()
                 comp_dict.pop('fgos', None) # Удаляем объект Fgos
                 comp_dict.pop('competency_type', None) # Удаляем объект CompetencyType
                 comp_dict.pop('based_on_labor_function', None) # Удаляем объект LaborFunction
                 
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
                    # Сериализуем ProfStandard
                    ps_dict = assoc.prof_standard.to_dict()
                    # Удаляем обратные связи, если они загружены
                    ps_dict.pop('generalized_labor_functions', None)
                    ps_dict.pop('fgos_assoc', None)
                    ps_dict.pop('educational_program_assoc', None)

                    recommended_ps_list.append({
                        **ps_dict, # Включаем все поля ПС
                        'is_mandatory': assoc.is_mandatory, # Добавляем метаданные связи
                        'description': assoc.description,
                        'link_id': assoc.id # Добавляем ID связи, если нужно для управления
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
    Управляет своей транзакцией.

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
        session.commit() # Коммит после успешного удаления
        logger.info(f"delete_fgos: FGOS with id {fgos_id} deleted successfully (cascading enabled).")
        return True

    except SQLAlchemyError as e:
        session.rollback() # Откат при ошибке БД
        logger.error(f"delete_fgos: Database error deleting FGOS {fgos_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        session.rollback() # Откат при любой другой ошибке
        logger.error(f"delete_fgos: Unexpected error deleting FGOS {fgos_id}: {e}", exc_info=True)
        return False

# --- Функции для работы с Профстандартами ---

def parse_prof_standard_upload(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Парсит загруженный файл профстандарта, извлекает базовые метаданные и контент.
    Эта функция вызывает парсер из parsers.py
    (Переименована из parse_uploaded_prof_standard для ясности)

    Args:
        file_bytes: Содержимое файла в байтах.
        filename: Имя файла.

    Returns:
        Dict[str, Any]: Словарь с извлеченными данными.
                        Структура должна включать хотя бы {'code': '...', 'name': '...', 'parsed_content': '...'}.
                        Может содержать 'generalized_labor_functions': [...] с детальной структурой.
    """
    # Вызываем парсер из parsers.py
    # Обработка ошибок парсинга должна быть внутри parse_prof_standard или здесь.
    try:
        # TODO: parse_prof_standard_upload (в parsers.py) должна парсить и возвращатьDict
        # с ключами 'code', 'name', 'parsed_content' (markdown), и опционально 'structure'
        # Вызываем парсер
        # from .parsers import parse_prof_standard_file # Нужно импортировать правильную функцию парсера ПС из parsers.py
        # parsed_data = parse_prof_standard_file(file_bytes, filename) # Используем функцию парсера из parsers.py

        # В текущей реализации parsers.py есть parse_uploaded_prof_standard
        # Давайте используем её, но лучше переименовать в parsers.py на parse_prof_standard_from_bytes
        from .parsers import parse_uploaded_prof_standard # Импортируем существующую функцию

        # Вызываем парсер
        parsed_data = parse_uploaded_prof_standard(file_bytes, filename)

        # Проверяем, что парсер вернул хотя бы базовые данные
        if not parsed_data or not parsed_data.get('code') or not parsed_data.get('name'):
             logger.warning(f"parse_prof_standard_upload: Parser failed to extract core metadata for {filename}.")
             # Возвращаем словарь с ошибкой
             return {'success': False, 'message': 'Не удалось извлечь код и название профстандарта из файла.', 'error_type': 'parsing_failed_core'}
             
        # Если парсинг успешный, возвращаем данные
        return {'success': True, 'message': 'Файл профстандарта успешно распарсен.', 'parsed_data': parsed_data}

    except Exception as e:
        logger.error(f"parse_prof_standard_upload: Unexpected error parsing {filename}: {e}", exc_info=True)
        # Возвращаем словарь с ошибкой
        return {'success': False, 'message': f"Неожиданная ошибка при парсинге файла: {e}", 'error_type': 'unexpected_parsing_error', 'details': str(e)}


def save_prof_standard_from_file(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Парсит файл профстандарта и сохраняет его в БД.
    Управляет своей транзакцией.

    Args:
        file_bytes: Содержимое файла в байтах.
        filename: Имя файла.

    Returns:
        Dict[str, Any]: Словарь с результатом операции:
            {
                'success': True/False,
                'message': '...',
                'prof_standard_id': '...' (ID сохраненного ProfStandard, если success=True),
                'error_type': '...' (опционально)
            }
    """
    session: Session = db.session
    try:
        # 1. Парсим файл
        # parse_prof_standard_upload возвращает {success, message, parsed_data, error_type?}
        parse_result = parse_prof_standard_upload(file_bytes, filename)

        if not parse_result.get('success'):
             # Если парсинг не удался, возвращаем результат парсера
             return parse_result

        parsed_data = parse_result['parsed_data']
        ps_code = parsed_data.get('code')
        ps_name = parsed_data.get('name')
        ps_markdown = parsed_data.get('parsed_content')
        # TODO: Извлечь и использовать другие метаданные ПС из парсера (номер, дата приказа, рег. номер/дата)

        # Проверка на обязательные данные после парсинга
        if not ps_code or not ps_name or ps_markdown is None: # parsed_content может быть пустой строкой, но не None
            message = "Парсер не извлек обязательные данные профстандарта (код, название, контент)."
            logger.error(message)
            return {'success': False, 'message': message, 'error_type': 'missing_parsed_data'}


        # 2. Ищем существующий Профстандарт по коду
        existing_ps = session.query(ProfStandard).filter_by(code=ps_code).first()

        if existing_ps:
            # Если существует, обновляем его
            logger.info(f"save_prof_standard_from_file: ProfStandard with code {ps_code} already exists ({existing_ps.id}). Updating...")
            prof_standard = existing_ps
            prof_standard.name = ps_name # Обновляем название
            prof_standard.parsed_content = ps_markdown # Обновляем контент
            # TODO: Обновить другие метаданные, если они есть в парсенных данных
            prof_standard.updated_at = datetime.datetime.utcnow() # Обновляем дату изменения явно

            # TODO: Удалить старую структурированную часть (ОТФ, ТФ, ТД, НУ, НЗ)
            # и сохранить новую, если парсер умеет ее извлекать.
            # Удаление должно быть каскадным или явным.
            # delete_prof_standard_structure(prof_standard.id, session)

            session.add(prof_standard) # Добавляем в сессию (для обновления)

        else:
            # Если не существует, создаем новый
            logger.info(f"save_prof_standard_from_file: Creating new ProfStandard with code {ps_code}.")
            prof_standard = ProfStandard(
                code=ps_code,
                name=ps_name,
                parsed_content=ps_markdown,
                # TODO: Добавить другие метаданные из парсера
            )
            session.add(prof_standard)
            session.flush() # Получаем ID нового объекта

        # TODO: Если парсер умеет извлекать структуру (ОТФ, ТФ, ...), сохранить ее ЗДЕСЬ
        # save_prof_standard_structure(prof_standard.id, parsed_data.get('structure'), session)


        session.commit() # Коммит после успешного создания/обновления
        logger.info(f"save_prof_standard_from_file: ProfStandard {ps_code} saved/updated successfully with ID {prof_standard.id}.")
        return {'success': True, 'message': 'Профстандарт успешно загружен и сохранен', 'prof_standard_id': prof_standard.id, 'code': prof_standard.code, 'name': prof_standard.name}

    except IntegrityError as e:
        session.rollback() # Откат при ошибке уникальности
        message = f"Ошибка уникальности при сохранении профстандарта (код '{ps_code}'): {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'message': message, 'error_type': 'integrity_error'}
    except SQLAlchemyError as e:
        session.rollback() # Откат при любой другой ошибке БД
        message = f"Ошибка базы данных при сохранении профстандарта '{ps_code}': {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'message': message, 'error_type': 'database_error'}
    except Exception as e:
        session.rollback() # Откат при любой другой неожиданной ошибке
        message = f"Неожиданная ошибка при сохранении профстандарта '{ps_code}': {e}"
        logger.error(message, exc_info=True)
        return {'success': False, 'message': message, 'error_type': 'unexpected_error', 'details': str(e)}

# Вспомогательные функции (для будущей имплементации)
# TODO: Реализовать удаление структуры ПС перед обновлением
# def delete_prof_standard_structure(prof_standard_id: int, session: Session):
#     """Удаляет всю структурированную информацию (ОТФ, ТФ, ТД, НУ, НЗ) для данного ПС."""
#     # Реализовать удаление из GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
#     # Возможно, CASCADE DELETE на FK уже достаточно.


# TODO: Реализовать сохранение структуры ПС
# def save_prof_standard_structure(prof_standard_id: int, structure_data: Dict[str, Any], session: Session):
#     """Сохраняет структурированные данные ПС в БД."""
#     # structure_data = {'generalized_labor_functions': [...]}
#     # Реализовать создание записей в GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
#     # и связывание их с ProfStandard и друг с другом.

# TODO: Реализовать удаление ПС
# def delete_prof_standard(prof_standard_id: int, session: Session) -> bool:
#     """Удаляет профстандарт и все связанные с ним сущности."""
#     # Удаление ProfStandard должно каскадно удалить связанные ОТФ, ТФ, и т.д.
#     # А также связи EducationalProgramPs, FgosRecommendedPs, IndicatorPsLink
#     # Нужно проверить настройки ON DELETE CASCADE в моделях.
#     pass


# --- Вспомогательные функции для других модулей (например, для импорта АУП) ---
# Функции для импорта AUP были перенесены в maps.logic.save_excel_data
# Например: delete_aup_by_num, save_excel_data (с session)

# --- Заглушка для NLP ---
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
    # Учитываем, что количество предложений не может превышать общее количество возможных связей
    max_suggestions = len(disciplines) * len(indicators)
    num_suggestions = min(5, max_suggestions) # Ограничиваем количество предложений
    
    # Используем set для хранения уникальных пар (discipline_id, indicator_id)
    generated_links = set()
    
    while len(generated_links) < num_suggestions:
        if not disciplines or not indicators: # Повторная проверка на случай, если списки опустели (хотя маловероятно)
             break
        
        d = random.choice(disciplines)
        i = random.choice(indicators)
        
        link_key = (d['aup_data_id'], i['id'])
        
        if link_key not in generated_links:
            generated_links.add(link_key)
            result.append({
                'aup_data_id': d['aup_data_id'],
                'indicator_id': i['id'],
                'score': round(random.random(), 2) # Случайная оценка релевантности
            })
            
        # Добавляем защиту от бесконечного цикла, если max_suggestions < num_suggestions
        if len(generated_links) >= max_suggestions:
             break
    
    return result
```

```python
# filepath: /home/me/ВКР/maps_backend/cli_commands/db_seed.py
# filepath: /home/me/ВКР/maps_backend/cli_commands/db_seed.py
import click
from flask.cli import with_appcontext
import datetime
import traceback
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import random

# --- Import all necessary models ---
# You need to import 'db' and all models used within the seed_command function
from maps.models import (
    db, SprDiscipline, AupInfo, AupData, SprFaculty, Department,
    SprDegreeEducation, SprFormEducation, SprRop, NameOP, Groups, SprOKCO,
    D_Blocks, D_Part, D_TypeRecord, D_ControlType, D_EdIzmereniya, D_Period, SprBranch, D_Modules
)
from auth.models import Roles, Users
from competencies_matrix.models import (
    CompetencyType, FgosVo, EducationalProgram, Competency, Indicator,
    CompetencyMatrix, EducationalProgramAup, EducationalProgramPs,
    ProfStandard, FgosRecommendedPs, IndicatorPsLink, LaborFunction, # Import LaborFunction
    GeneralizedLaborFunction, LaborAction, RequiredSkill, RequiredKnowledge # Import other PS structure models
)
from cabinet.models import (
    StudyGroups, SprPlace, SprBells, DisciplineTable,
    GradeType, Topics, Students, Tutors, Grade, GradeColumn,
    TutorsOrder, TutorsOrderRow
)

# Assuming Mode model exists, potentially in a general config or base models file
# If it's elsewhere, adjust the import accordingly
# from some_module import Mode # Placeholder for Mode import

@click.command(name='seed_db')
@with_appcontext
def seed_command():
    """Заполняет базу данных начальными/тестовыми данными (Идемпотентно)."""
    print("Starting database seeding...")
    try:
        session = db.session # Получаем сессию
        
        # === БЛОК 1: Основные Справочники (Первоочередные) ===
        print("Seeding Core Lookups...")

        # Используем merge для идемпотентности - он вставит или обновит по PK
        # Сначала справочники без зависимостей
        session.merge(CompetencyType(id=1, code='УК', name='Универсальная'))
        session.merge(CompetencyType(id=2, code='ОПК', name='Общепрофессиональная'))
        session.merge(CompetencyType(id=3, code='ПК', code_name='Профессиональная')) # Уточнено code_name

        session.merge(Roles(id_role=1, name_role='admin'))
        session.merge(Roles(id_role=2, name_role='methodologist'))
        session.merge(Roles(id_role=3, name_role='teacher'))
        session.merge(Roles(id_role=4, name_role='tutor'))
        session.merge(Roles(id_role=5, name_role='student'))

        # Справочники для АУП (ID как в сидере)
        session.merge(SprBranch(id_branch=1, city='Москва', location='Основное подразделение')) # Имя поля уточнено
        session.merge(SprDegreeEducation(id_degree=1, name_deg="Высшее образование - бакалавриат")) # Имя поля уточнено
        session.merge(SprFormEducation(id_form=1, form="Очная")) # Имя поля уточнено
        session.merge(SprRop(id_rop=1, last_name='Иванов', first_name='Иван', middle_name='Иванович', email='rop@example.com', telephone='+70000000000'))
        # Замени на реальные данные для SprOKCO и NameOP если они используются как FK
        session.merge(SprOKCO(program_code='09.03.01', name_okco='Информатика и ВТ')) # Пример ОКСО
        session.merge(NameOP(id_spec=1, program_code='09.03.01', num_profile='01', name_spec='Веб-технологии')) # Пример NameOP

        # Добавляем факультет и кафедру (департамент) - обязательно перед АУП
        faculty_1 = session.merge(SprFaculty(id_faculty=1, name_faculty='Факультет информатики', id_branch=1))
        department_1 = session.merge(Department(id_department=1, name_department='Кафедра веб-технологий'))
        session.commit()  # Коммитим факультет и кафедру

        # Справочники для AupData (ID как в сидере)
        session.merge(D_Blocks(id=1, title="Блок 1. Дисциплины (модули)"))
        session.merge(D_Part(id=1, title="Обязательная часть"))
        session.merge(D_Modules(id=1, title="Базовый модуль", color="#FFFFFF")) # Добавлен цвет
        session.merge(Groups(id_group=1, name_group="Основные", color="#FFFFFF", weight=1)) # Имя поля уточнено
        session.merge(D_TypeRecord(id=1, title="Дисциплина"))
        session.merge(D_ControlType(id=1, title="Экзамен", default_shortname="Экз"))
        session.merge(D_ControlType(id=5, title="Зачет", default_shortname="Зач"))
        session.merge(D_EdIzmereniya(id=1, title="Академ. час"))
        session.merge(D_Period(id=1, title="Семестр 1"))
        session.merge(D_Period(id=2, title="Семестр 2"))

        # Справочники Дисциплин
        session.merge(SprDiscipline(id=1001, title='Основы программирования'))
        session.merge(SprDiscipline(id=1002, title='Базы данных'))
        session.merge(SprDiscipline(id=1003, title='История России'))

        # Коммитим все справочники ПЕРЕД созданием зависимых сущностей
        session.commit()
        print("  - Core lookups seeded/merged.")

        # === БЛОК 2: ФГОС и Образовательные Программы ===
        print("Seeding FGOS...")
        # merge вернет объект, который есть в сессии (или новый)
        # Используем дату в формате YYYY-MM-DD
        fgos1 = session.merge(FgosVo(id=1, number='929', date=datetime.date(2017, 9, 19), direction_code='09.03.01',
                                       direction_name='Информатика и вычислительная техника', education_level='бакалавриат', generation='3++', file_path='ФГОС ВО 090301_B_3_19092017.pdf'))
        # Добавим еще один ФГОС для теста
        fgos2 = session.merge(FgosVo(id=2, number='922', date=datetime.date(2020, 8, 7), direction_code='18.03.01',
                                       direction_name='Химическая технология', education_level='бакалавриат', generation='3+', file_path='ФГОС ВО 180301_B_3_07082020.pdf'))
        session.commit()
        print("  - FGOS 09.03.01 and 18.03.01 checked/merged.")

        print("Seeding Educational Program...")
        # ИСПОЛЬЗУЕМ title
        program1 = session.merge(EducationalProgram(id=1, fgos_vo_id=1, code='09.03.01', title='Веб-технологии (09.03.01)',
                                                     profile='Веб-технологии', qualification='Бакалавр', form_of_education='очная', enrollment_year=2024))
        # Добавим еще одну ОП для теста
        program2 = session.merge(EducationalProgram(id=2, fgos_vo_id=2, code='18.03.01', title='Технология переработки пластических масс и эластомеров (18.03.01)',
                                                    profile='Не указан', qualification='Бакалавр', form_of_education='очная', enrollment_year=2024))

        session.commit()
        print("  - Educational Programs checked/merged.")

        # === БЛОК 3: АУП и его структура ===
        print("Seeding AUP...")
        # merge вернет объект AupInfo
        aup101 = session.merge(AupInfo(id_aup=101, num_aup='B093011451', file='example.xlsx', base='11 классов',
                                          id_faculty=1, id_rop=1, type_educ='Высшее', qualification='Бакалавр',
                                          type_standard='ФГОС 3++', id_department=1, period_educ='4 года',
                                          id_degree=1, id_form=1, years=4, months=0, id_spec=1,
                                          year_beg=2024, year_end=2028, is_actual=1))
        # Добавим еще один АУП для теста
        aup102 = session.merge(AupInfo(id_aup=102, num_aup='B180301XXXX', file='example2.xlsx', base='11 классов',
                                       id_faculty=1, id_rop=1, type_educ='Высшее', qualification='Бакалавр',
                                       type_standard='ФГОС 3+', id_department=1, period_educ='4 года',
                                       id_degree=1, id_form=1, years=4, months=0, id_spec=1,
                                       year_beg=2024, year_end=2028, is_actual=1))

        session.commit()
        print("  - AUPs checked/merged.")

        print("Seeding AUP-Program Links...")
        # Для ассоциативных лучше проверка + add
        link_ep_aup1 = EducationalProgramAup.query.filter_by(educational_program_id=1, aup_id=101).first()
        if not link_ep_aup1:
            link_ep_aup1 = EducationalProgramAup(educational_program_id=1, aup_id=101, is_primary=True)
            session.add(link_ep_aup1)
            print("  - Linked Program 1 and AUP 101.")
        else:
            print("  - Link Program 1 - AUP 101 already exists.")

        link_ep_aup2 = EducationalProgramAup.query.filter_by(educational_program_id=2, aup_id=102).first()
        if not link_ep_aup2:
            link_ep_aup2 = EducationalProgramAup(educational_program_id=2, aup_id=102, is_primary=True)
            session.add(link_ep_aup2)
            print("  - Linked Program 2 and AUP 102.")
        else:
            print("  - Link Program 2 - AUP 102 already exists.")


        session.commit()
        print("  - AUP-Program Links checked/merged.")


        print("Seeding AupData entries...")
        # merge вернет объекты AupData - используем _discipline для имени колонки
        ad501 = session.merge(AupData(
            id=501, id_aup=101, id_discipline=1001, _discipline='Основы программирования',
            id_block=1, shifr='Б1.1.07', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=1, num_row=7, id_type_control=1, # Экзамен
            amount=14400, id_edizm=1, zet=4
        ))
        ad502 = session.merge(AupData(
            id=502, id_aup=101, id_discipline=1002, _discipline='Базы данных',
            id_block=1, shifr='Б1.1.10', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=1, num_row=10, id_type_control=5, # Зачет
            amount=10800, id_edizm=1, zet=3
        ))
        ad503 = session.merge(AupData(
            id=503, id_aup=101, id_discipline=1003, _discipline='История России',
            id_block=1, shifr='Б1.1.01', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=1, num_row=1, id_type_control=5, # Зачет
            amount=7200, id_edizm=1, zet=2
        ))
        # Добавим AupData для второго АУП
        ad504 = session.merge(AupData(
            id=504, id_aup=102, id_discipline=1001, _discipline='Основы программирования',
            id_block=1, shifr='Б1.1.08', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=1, num_row=8, id_type_control=1, # Экзамен
            amount=14400, id_edizm=1, zet=4
        ))
        ad505 = session.merge(AupData(
            id=505, id_aup=102, id_discipline=1003, _discipline='История России',
            id_block=1, shifr='Б1.1.01', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=2, num_row=1, id_type_control=5, # Зачет
            amount=7200, id_edizm=1, zet=2
        ))


        session.commit()
        print("  - AupData entries checked/merged.")

        # === БЛОК 4: Компетенции и Индикаторы ===
        print("Seeding Competencies & Indicators...")
        # Используем merge
        # ВАЖНО: Убедись, что поле fgos_vo_id добавлено в модель Competency и миграцию!

        # УК для ФГОС 09.03.01 (fgos_vo_id=1)
        comp_uk1_fgos1 = session.merge(Competency(id=1, competency_type_id=1, fgos_vo_id=1, code='УК-1', name='Способен осуществлять поиск, критический анализ и синтез информации, применять системный подход для решения поставленных задач'))
        comp_uk2_fgos1 = session.merge(Competency(id=2, competency_type_id=1, fgos_vo_id=1, code='УК-2', name='Способен определять круг задач в рамках поставленной цели и выбирать оптимальные способы их решения...'))
        comp_uk3_fgos1 = session.merge(Competency(id=3, competency_type_id=1, fgos_vo_id=1, code='УК-3', name='Способен осуществлять социальное взаимодействие и реализовывать свою роль в команде'))
        comp_uk4_fgos1 = session.merge(Competency(id=4, competency_type_id=1, fgos_vo_id=1, code='УК-4', name='Способен осуществлять деловую коммуникацию в устной и письменной формах на государственном языке РФ...'))
        comp_uk5_fgos1 = session.merge(Competency(id=5, competency_type_id=1, fgos_vo_id=1, code='УК-5', name='Способен воспринимать межкультурное разнообразие общества...'))
        comp_uk6_fgos1 = session.merge(Competency(id=6, competency_type_id=1, fgos_vo_id=1, code='УК-6', name='Способен управлять своим временем, выстраивать и реализовывать траекторию саморазвития...'))
        comp_uk7_fgos1 = session.merge(Competency(id=7, competency_type_id=1, fgos_vo_id=1, code='УК-7', name='Способен поддерживать должный уровень физической подготовленности...'))
        comp_uk8_fgos1 = session.merge(Competency(id=8, competency_type_id=1, fgos_vo_id=1, code='УК-8', name='Способен создавать и поддерживать в повседневной жизни и в профессиональной деятельности безопасные условия...'))
        comp_uk9_fgos1 = session.merge(Competency(id=9, competency_type_id=1, fgos_vo_id=1, code='УК-9', name='Способен принимать обоснованные экономические решения...'))
        comp_uk10_fgos1 = session.merge(Competency(id=10, competency_type_id=1, fgos_vo_id=1, code='УК-10', name='Способен формировать нетерпимое отношение к проявлениям экстремизма, терроризма, коррупционного поведения...'))

        # ОПК для ФГОС 09.03.01 (fgos_vo_id=1)
        comp_opk1_fgos1 = session.merge(Competency(id=101, competency_type_id=2, fgos_vo_id=1, code='ОПК-1', name='Способен применять естественнонаучные и общеинженерные знания...'))
        comp_opk2_fgos1 = session.merge(Competency(id=102, competency_type_id=2, fgos_vo_id=1, code='ОПК-2', name='Способен принимать принципы работы современных информационных технологий...'))
        comp_opk3_fgos1 = session.merge(Competency(id=103, competency_type_id=2, fgos_vo_id=1, code='ОПК-3', name='Способен решать стандартные задачи профессиональной деятельности на основе информационной и библиографической культуры...'))
        comp_opk4_fgos1 = session.merge(Competency(id=104, competency_type_id=2, fgos_vo_id=1, code='ОПК-4', name='Способен участвовать в разработке стандартов, норм и правил...'))
        comp_opk5_fgos1 = session.merge(Competency(id=105, competency_type_id=2, fgos_vo_id=1, code='ОПК-5', name='Способен инсталлировать программное и аппаратное обеспечение...'))
        comp_opk6_fgos1 = session.merge(Competency(id=106, competency_type_id=2, fgos_vo_id=1, code='ОПК-6', name='Способен разрабатывать бизнес-планы и технические задания...'))
        comp_opk7_fgos1 = session.merge(Competency(id=107, competency_type_id=2, fgos_vo_id=1, code='ОПК-7', name='Способен участвовать в настройке и наладке программно-аппаратных комплексов'))
        comp_opk8_fgos1 = session.merge(Competency(id=108, competency_type_id=2, fgos_vo_id=1, code='ОПК-8', name='Способен разрабатывать алгоритмы и программы, пригодные для практического применения'))
        comp_opk9_fgos1 = session.merge(Competency(id=109, competency_type_id=2, fgos_vo_id=1, code='ОПК-9', name='Способен осваивать методики использования программных средств для решения практических задач'))

        # ПК для ОП Веб-технологии (fgos_vo_id=None, т.к. ПК не берутся из ФГОС)
        comp_pk1 = session.merge(Competency(id=201, competency_type_id=3, fgos_vo_id=None, code='ПК-1', name='Способен выполнять работы по созданию (модификации) и сопровождению ИС, автоматизирующих задачи организационного управления и бизнес-процессы'))
        comp_pk2 = session.merge(Competency(id=202, competency_type_id=3, fgos_vo_id=None, code='ПК-2', name='Способен осуществлять управление проектами в области ИТ на основе полученных планов проектов в условиях, когда проект не выходит за пределы утвержденных параметров'))
        comp_pk3 = session.merge(Competency(id=203, competency_type_id=3, fgos_vo_id=None, code='ПК-3', name='Способен разрабатывать требования и проектировать программное обеспечение'))
        comp_pk4 = session.merge(Competency(id=204, competency_type_id=3, fgos_vo_id=None, code='ПК-4', name='Способен проводить работы по интеграции программных модулей и компонент и проверку работоспособности выпусков программных продуктов'))
        comp_pk5 = session.merge(Competency(id=205, competency_type_id=3, fgos_vo_id=None, code='ПК-5', name='Способен осуществлять концептуальное, функциональное и логическое проектирование систем среднего и крупного масштаба и сложности'))


        # Индикаторы - тоже через merge
        # Для УК-1 (ID=1)
        session.merge(Indicator(id=10, competency_id=1, code='ИУК-1.1', formulation='Анализирует задачу, выделяя ее базовые составляющие', source='Распоряжение 505-Р'))
        session.merge(Indicator(id=11, competency_id=1, code='ИУК-1.2', formulation='Осуществляет поиск, критически оценивает, обобщает, систематизирует и ранжирует информацию...', source='Распоряжение 505-Р'))
        session.merge(Indicator(id=12, competency_id=1, code='ИУК-1.3', formulation='Рассматривает и предлагает рациональные варианты решения...', source='Распоряжение 505-Р'))
        # Для УК-2 (ID=2)
        session.merge(Indicator(id=20, competency_id=2, code='ИУК-2.1', formulation='Формулирует совокупность задач в рамках поставленной цели проекта...', source='Распоряжение 505-Р'))
        session.merge(Indicator(id=21, competency_id=2, code='ИУК-2.2', formulation='Определяет связи между поставленными задачами, основными компонентами проекта...', source='Распоряжение 505-Р'))
        session.merge(Indicator(id=22, competency_id=2, code='ИУК-2.3', formulation='Выбирает оптимальные способы планирования, распределения зон ответственности...', source='Распоряжение 505-Р'))
        # ... и так далее для всех УК и ОПК по Распоряжению 505-Р
        # Для УК-5 (ID=5)
        session.merge(Indicator(id=50, competency_id=5, code='ИУК-5.1', formulation='Анализирует и интерпретирует события, современное состояние общества...', source='Распоряжение 505-Р'))
        # Для ОПК-7 (ID=107)
        session.merge(Indicator(id=170, competency_id=107, code='ИОПК-7.1', formulation='Знает основные языки программирования, операционные системы и оболочки, современные среды разработки программного обеспечения', source='ОП Веб-технологии'))
        # ... и так далее для всех ОПК
        
        # Индикаторы для ПК (ИПК) (Пример для ПК-1 ID=201)
        session.merge(Indicator(id=210, competency_id=201, code='ИПК-1.1', formulation='Знает: методологию и технологии проектирования информационных систем; проектирование обеспечивающих подсистем; приемы программирования приложений.', source='ОП Веб-технологии / ПС 06.015'))
        session.merge(Indicator(id=211, competency_id=201, code='ИПК-1.2', formulation='Умеет: создавать, модифицировать и сопровождать информационные системы для решения задач бизнес-процессов и организационного управления...', source='ОП Веб-технологии / ПС 06.015'))
        session.merge(Indicator(id=212, competency_id=201, code='ИПК-1.3', formulation='Владеет: методами создания и сопровождения информационных систем...', source='ОП Веб-технологии / ПС 06.015'))
        # ... и так далее для всех ПК из таблицы 5 ОП Веб-технологии

        session.commit() # Коммитим компетенции и индикаторы
        print("  - Competencies & Indicators checked/merged.")

        # === БЛОК 4.1: Профессиональные Стандарты (Базовая структура) ===
        print("Seeding Basic Professional Standards Structure...")
        # Добавим несколько Профстандартов и базовую структуру (ОТФ, ТФ)
        # Наполнение всей структуры (ТД, НУ, НЗ) и связей ИДК-ТФ/ТД/НУ/НЗ - это задача парсинга ПС и ручного формирования

        ps_prog = session.merge(ProfStandard(id=1, code='06.001', name='Программист', parsed_content='...')) # Добавить markdown контент
        ps_is = session.merge(ProfStandard(id=2, code='06.015', name='Специалист по информационным системам', parsed_content='...'))
        ps_pm = session.merge(ProfStandard(id=3, code='06.016', name='Руководитель проектов в области ИТ', parsed_content='...'))
        ps_sa = session.merge(ProfStandard(id=4, code='06.022', name='Системный аналитик', parsed_content='...'))

        session.commit()
        print("  - ProfStandards checked/merged.")

        # Добавим базовые ОТФ и ТФ для ПС 06.015 (id=2)
        otf_c_06015 = session.merge(GeneralizedLaborFunction(id=1, prof_standard_id=2, code='C', name='Выполнение работ и управление работами по созданию (модификации) и сопровождению ИС...'))
        session.commit()

        tf_c016_06015 = session.merge(LaborFunction(id=1, generalized_labor_function_id=1, code='C/01.6', name='Определение первоначальных требований заказчика к ИС...'))
        tf_c166_06015 = session.merge(LaborFunction(id=2, generalized_labor_function_id=1, code='C/16.6', name='Проектирование и дизайн ИС...'))
        tf_c186_06015 = session.merge(LaborFunction(id=3, generalized_labor_function_id=1, code='C/18.6', name='Организационное и технологическое обеспечение создания программного кода ИС...'))

        session.commit()
        print("  - Basic ОТФ/ТФ for PS 06.015 seeded.")

        # Свяжем ПК-1 (ID=201) с ТФ C/16.6 (ID=2) и C/18.6 (ID=3) из ПС 06.015 (ID=2) как базовые
        # Это связь Competency.based_on_labor_function_id (один-к-одному для ПК, если ПК основана на одной ТФ)
        # Или ПК может быть основана на нескольких ТФ (тогда нужна доп. таблица или поле text/json)
        # ОП Веб-технологии таблица 5 указывает, что ПК-1 основана на ОТФ C ПС 06.015.
        # Давайте свяжем ПК-1 с ОТФ C (ID=1) в Competency.based_on_labor_function_id (хотя FK на LaborFunction)
        # TODO: Определить точную логику связи ПК с ПС/ОТФ/ТФ в модели
        # Сейчас Competency.based_on_labor_function_id ссылается на LaborFunction.
        # Давайте свяжем ПК-1 с одной из ключевых ТФ, например C/16.6 (id=2)
        comp_pk1 = session.query(Competency).get(201)
        if comp_pk1 and comp_pk1.based_on_labor_function_id is None:
            tf_c166 = session.query(LaborFunction).get(2)
            if tf_c166:
                comp_pk1.based_on_labor_function_id = tf_c166.id
                session.commit()
                print("  - Linked ПК-1 to TФ C/16.6.")
            else:
                print("  - TФ C/16.6 not found, cannot link ПК-1.")


        # Связи ОП Веб-технологии (ID=1) с выбранными ПС (из таблицы 1 ОП)
        # ПС 06.015, 06.016, 06.022 выбраны. ПС 06.001 тоже, т.к. профиль Программист.
        program1 = session.query(EducationalProgram).get(1)
        ps_ids_for_prog1 = session.query(ProfStandard.id).filter(ProfStandard.code.in_(['06.001', '06.015', '06.016', '06.022'])).all()
        ps_ids_for_prog1 = [id for (id,) in ps_ids_for_prog1] # Преобразуем в список ID

        for ps_id in ps_ids_for_prog1:
            link_ep_ps = EducationalProgramPs.query.filter_by(educational_program_id=1, prof_standard_id=ps_id).first()
            if not link_ep_ps:
                link_ep_ps = EducationalProgramPs(educational_program_id=1, prof_standard_id=ps_id)
                session.add(link_ep_ps)
                print(f"  - Linked Program 1 to ProfStandard ID {ps_id}.")
            else:
                 print(f"  - Link Program 1 to ProfStandard ID {ps_id} already exists.")
        session.commit()
        print("  - Program-ProfStandard links seeded.")


        # Связи ФГОС 09.03.01 (ID=1) с рекомендованными ПС (из приложения к ФГОС)
        # ПС 06.001, 06.004, 06.011, 06.015, 06.016, 06.019, 06.022, 06.025, 06.026, 06.027, 06.028
        fgos1 = session.query(FgosVo).get(1)
        recommended_ps_codes_for_fgos1 = ['06.001', '06.004', '06.011', '06.015', '06.016', '06.019', '06.022', '06.025', '06.026', '06.027', '06.028']
        ps_ids_for_fgos1 = session.query(ProfStandard.id).filter(ProfStandard.code.in_(recommended_ps_codes_for_fgos1)).all()
        ps_ids_for_fgos1 = [id for (id,) in ps_ids_for_fgos1]

        for ps_id in ps_ids_for_fgos1:
             link_fgos_ps = FgosRecommendedPs.query.filter_by(fgos_vo_id=1, prof_standard_id=ps_id).first()
             if not link_fgos_ps:
                  link_fgos_ps = FgosRecommendedPs(fgos_vo_id=1, prof_standard_id=ps_id)
                  session.add(link_fgos_ps)
                  print(f"  - Linked FGOS 1 to Recommended ProfStandard ID {ps_id}.")
             else:
                  print(f"  - Link FGOS 1 to Recommended ProfStandard ID {ps_id} already exists.")
        session.commit()
        print("  - FGOS-RecommendedProfStandard links seeded.")


        # Связи Индикаторов с Трудовыми Функция (IndicatorPsLink)
        # Пример: ИПК-1.1 (id=210) -> ТФ C/01.6 (id=1) и C/16.6 (id=2) из ПС 06.015
        # Это нужно, чтобы знать, какие элементы ПС "формируют" данный ИПК
        ind210 = session.query(Indicator).get(210)
        tf_c016 = session.query(LaborFunction).get(1)
        tf_c166 = session.query(LaborFunction).get(2)

        if ind210 and tf_c016:
             link_ind_tf1 = IndicatorPsLink.query.filter_by(indicator_id=210, labor_function_id=1).first()
             if not link_ind_tf1:
                  link_ind_tf1 = IndicatorPsLink(indicator_id=210, labor_function_id=1, is_manual=True, relevance_score=1.0)
                  session.add(link_ind_tf1)
                  print("  - Linked Indicator 210 to LaborFunction 1.")
             else:
                  print("  - Link Indicator 210 to LaborFunction 1 already exists.")

        if ind210 and tf_c166:
             link_ind_tf2 = IndicatorPsLink.query.filter_by(indicator_id=210, labor_function_id=2).first()
             if not link_ind_tf2:
                  link_ind_tf2 = IndicatorPsLink(indicator_id=210, labor_function_id=2, is_manual=True, relevance_score=1.0)
                  session.add(link_ind_tf2)
                  print("  - Linked Indicator 210 to LaborFunction 2.")
             else:
                  print("  - Link Indicator 210 to LaborFunction 2 already exists.")
        session.commit()
        print("  - Indicator-LaborFunction links seeded.")


        # === БЛОК 5: Связи Матрицы Компетенций ===
        print("Seeding Competency Matrix links...")
        # Используем функцию для проверки и добавления
        def add_link_if_not_exists(aup_data_id, indicator_id):
            # Проверяем существование AupData и Indicator в текущей сессии или БД
            aup_data_rec = session.query(AupData).get(aup_data_id)
            indicator_rec = session.query(Indicator).get(indicator_id)
            if not aup_data_rec or not indicator_rec:
                 print(f"    - SKIPPED link ({aup_data_id} <-> {indicator_id}): AupData or Indicator missing!")
                 return False

            exists = session.query(CompetencyMatrix).filter_by(aup_data_id=aup_data_id, indicator_id=indicator_id).first()
            if not exists:
                link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
                session.add(link)
                print(f"    - Added link ({aup_data_id} <-> {indicator_id})")
                return True
            return True

        # Основы программирования (501) -> ИУК-1.1(10), ИУК-1.2(11), ИУК-1.3(12), ИОПК-7.1(170)
        add_link_if_not_exists(501, 10)
        add_link_if_not_exists(501, 11)
        add_link_if_not_exists(501, 12)
        add_link_if_not_exists(501, 170)
        # История России (503) -> ИУК-5.1(50)
        add_link_if_not_exists(503, 50)
        # Базы данных (502) -> ИПК-1.1(210)
        add_link_if_not_exists(502, 210)

        session.commit() # Коммитим связи
        print("  - Matrix links checked/added based on Excel example.")

        # === БЛОК 6: Тестовый Пользователь ===
        print("Seeding Test User...")
        test_user = Users.query.filter_by(login='testuser').first()
        if not test_user:
            test_user = Users(
                # id_user=999, # Позволим БД самой назначить ID через auto-increment
                login='testuser',
                # Устанавливаем хеш пароля 'password'
                password_hash=generate_password_hash('password', method='pbkdf2:sha256'),
                name='Тестовый Методист',
                email='testuser@example.com',
                approved_lk=True # Предполагаем, что для тестов одобрение ЛК не нужно
                # Добавь department_id, если оно обязательно
            )
            session.add(test_user)
            session.commit() # Коммитим пользователя ПЕРЕД назначением роли
            print(f"  - Added test user 'testuser' with id {test_user.id_user}.")

            # Назначаем роль methodologist (ID=2)
            methodologist_role = Roles.query.get(2)
            if methodologist_role:
                # Используем session.query для проверки наличия роли у пользователя
                if methodologist_role not in test_user.roles: # Проверяем через relationship
                    test_user.roles.append(methodologist_role)
                    session.commit()
                    print("  - Assigned 'methodologist' role to 'testuser'.")
                else:
                    print("  - Role 'methodologist' already assigned to 'testuser'.")
            else:
                print("  - WARNING: Role 'methodologist' (ID=2) not found, skipping role assignment.")
        else:
            print("  - Test user 'testuser' already exists.")

        # === BLOCK 7: Admin User ===
        print("Seeding Admin User...")
        admin_user = Users.query.filter_by(login='admin').first()
        if not admin_user:
            admin_user = Users(
                login='admin',
                password_hash=generate_password_hash('admin', method='pbkdf2:sha256'),
                name='Admin User',
                email='admin@example.com',
                approved_lk=True
            )
            session.add(admin_user)
            session.commit()
            print(f"  - Added admin user 'admin' with id {admin_user.id_user}")

            # Assign admin role (ID=1)
            admin_role = Roles.query.get(1)
            if admin_role:
                # Используем session.query для проверки наличия роли у пользователя
                 if admin_role not in admin_user.roles: # Проверяем через relationship
                    admin_user.roles.append(admin_role)
                    session.commit()
                    print("  - Assigned 'admin' role to admin user")
                 else:
                     print("  - Role 'admin' already assigned to admin user")
            else:
                print("  - WARNING: Role 'admin' (ID=1) not found, skipping role assignment")
        else:
            print("  - Admin user 'admin' already exists")

        # === BLOCK 8: Cabinet Models (Academic Cabinet) ===
        print("Seeding Cabinet Models...")

        # Add classroom locations (SprPlace)
        places = [
            SprPlace(id=1, name="Аудитория", prefix="А", is_online=False),
            SprPlace(id=2, name="Online", prefix="", is_online=True),
            SprPlace(id=3, name="Лаборатория", prefix="Л", is_online=False),
            SprPlace(id=4, name="Компьютерный класс", prefix="КК", is_online=False)
        ]
        for place in places:
            session.merge(place) # Используем session.merge
        session.commit()
        print("  - Classroom locations seeded.")

        # Add bell schedule (SprBells)
        bells = [
            SprBells(id=1, order=1, name="9:00 - 10:30"),
            SprBells(id=2, order=2, name="10:40 - 12:10"),
            SprBells(id=3, order=3, name="12:20 - 13:50"),
            SprBells(id=4, order=4, name="14:30 - 16:00"),
            SprBells(id=5, order=5, name="16:10 - 17:40"),
            SprBells(id=6, order=6, name="17:50 - 19:20")
        ]
        for bell in bells:
            session.merge(bell) # Используем session.merge
        session.commit()
        print("  - Bell schedule seeded.")

        # Add study groups (StudyGroups)
        # Используем session.query для проверки
        test_group = session.query(StudyGroups).filter_by(title="211-321").first()
        if not test_group:
            # Remove the explicit ID to allow auto-increment (или использовать session.merge с id)
            test_group = StudyGroups(
                # Remove id=1 to avoid primary key conflicts
                title="211-321",
                num_aup="B093011451" # Привязываем к AUP 101
            )
            session.add(test_group) # Используем session.add
            session.commit()
            print("  - Study group 211-321 added.")
        else:
            # Update the existing record if needed
            test_group.num_aup = "B093011451"
            session.commit()
            print("  - Study group 211-321 already exists, updated if needed.")

        # Add a test student
        test_student = session.query(Students).filter_by(name="Иванов Иван Иванович").first()
        if not test_student:
            test_student = Students(
                name="Иванов Иван Иванович",
                study_group_id=test_group.id,
                lk_id=1001 # ID из ЛК
            )
            session.add(test_student)
            session.commit()
            print("  - Test student added.")
        else:
            print("  - Test student already exists.")

        # Add a test tutor
        test_tutor = session.query(Tutors).filter_by(name="Петров Петр Петрович").first()
        if not test_tutor:
            test_tutor = Tutors(
                name="Петров Петр Петрович",
                lk_id=2001, # ID из ЛК
                post="Доцент",
                id_department=1  # Using the department added earlier
            )
            session.add(test_tutor)
            session.commit()
            print("  - Test tutor added.")
        else:
            print("  - Test tutor already exists.")

        # Create DisciplineTable entry for the test AUP and group
        discipline_table = session.query(DisciplineTable).filter_by(
            id_aup=101, # Привязываем к AUP 101
            id_unique_discipline=1001, # Привязываем к Основам программирования
            study_group_id=test_group.id,
            semester=1
        ).first()

        if not discipline_table:
            # Remove explicit ID if using auto-increment
            discipline_table = DisciplineTable(
                # id=1, # Remove explicit ID
                id_aup=101,  # From seeded AUP
                id_unique_discipline=1001,  # From seeded SprDiscipline
                study_group_id=test_group.id,
                semester=1
            )
            session.add(discipline_table)
            session.commit()
            print("  - Discipline table created.")
        else:
            print("  - Discipline table already exists.")

        # Add grade types (GradeType)
        # Используем session.merge
        grade_types_data = [
            {"id": 1, "name": "Посещаемость", "type": "attendance", "binary": True, "discipline_table_id": discipline_table.id},
            {"id": 2, "name": "Активность", "type": "activity", "binary": False, "discipline_table_id": discipline_table.id},
            {"id": 3, "name": "Задания", "type": "tasks", "binary": False, "discipline_table_id": discipline_table.id}
        ]

        for grade_type_data in grade_types_data:
            # Use session.merge for GradeType
            grade_type = session.merge(GradeType(**grade_type_data))
        session.commit()
        print("  - Grade types created.")

        # Add a couple of topics to the discipline table
        # Используем session.merge
        topics_data = [
            {
                "id": 1,
                "discipline_table_id": discipline_table.id,
                "topic": "Введение в предмет",
                "chapter": "Глава 1",
                "id_type_control": 1,  # Lecture (from D_ControlType)
                "task_link": "https://example.com/task1",
                "task_link_name": "Задание 1",
                "study_group_id": test_group.id,
                "spr_place_id": 1,  # Classroom
                "lesson_order": 1
            },
            {
                "id": 2,
                "discipline_table_id": discipline_table.id,
                "topic": "Основные понятия",
                "chapter": "Глава 1",
                "id_type_control": 1,  # Lecture
                "task_link": "https://example.com/task2",
                "task_link_name": "Задание 2",
                "study_group_id": test_group.id,
                "spr_place_id": 1,  # Classroom
                "lesson_order": 2
            }
        ]

        for topic_data in topics_data:
            # Use session.merge for Topics
            topic = session.merge(Topics(**topic_data))
        session.commit()
        print("  - Topics created.")

        # Add grade columns for the topics and grade types
        # Используем session.merge
        # Получаем все topics и grade_types из сессии после их создания/мерджа
        all_topics = session.query(Topics).all()
        all_grade_types = session.query(GradeType).all() # Все GradeType

        for topic in all_topics:
            for grade_type in all_grade_types:
                # Важно: GradeColumn привязана к DisciplineTable, Topic, GradeType
                # Проверяем, что GradeType привязан к той же DisciplineTable, что и Topic
                if grade_type.discipline_table_id != topic.discipline_table_id:
                    continue # Пропускаем, если GradeType не относится к этой DisciplineTable

                grade_column = session.query(GradeColumn).filter_by(
                    discipline_table_id=topic.discipline_table_id,
                    grade_type_id=grade_type.id,
                    topic_id=topic.id
                ).first()

                if not grade_column:
                    grade_column = GradeColumn(
                        discipline_table_id=topic.discipline_table_id,
                        grade_type_id=grade_type.id,
                        topic_id=topic.id
                    )
                    session.add(grade_column) # Используем session.add
        session.commit()
        print("  - Grade columns created.")

        # Add some sample grades for the student
        # Используем session.merge
        # Получаем все grade columns из сессии
        all_grade_columns = session.query(GradeColumn).all()
        # Получаем тестового студента из сессии
        test_student = session.query(Students).filter_by(name="Иванов Иван Иванович").first()
        if test_student:
            for grade_column in all_grade_columns:
                grade = session.query(Grade).filter_by(
                    student_id=test_student.id,
                    grade_column_id=grade_column.id
                ).first()

                if not grade:
                    # Random grades between 3 and 5
                    value = random.randint(3, 5)

                    # For attendance (binary), use 1 for present
                    # Нужно получить тип из GradeType
                    grade_type = session.query(GradeType).get(grade_column.grade_type_id)
                    if grade_type and grade_type.type == 'attendance':
                        value = 1 # Оценка за посещаемость

                    grade = Grade(
                        student_id=test_student.id,
                        grade_column_id=grade_column.id,
                        value=value
                    )
                    session.add(grade) # Используем session.add
            session.commit()
            print("  - Sample grades created.")
        else:
             print("  - Test student not found, skipping sample grades.")


        print("Cabinet models seeded successfully.")
        print("\nDatabase seeding finished successfully.")

    except (IntegrityError, SQLAlchemyError) as e: # Ловим конкретные ошибки БД
        session.rollback()
        print(f"\n!!! DATABASE ERROR during seeding: {e} !!!")
        print("!!! Seeding stopped. Check foreign key constraints and data order. !!!")
        traceback.print_exc()
    except Exception as e: # Ловим все остальные ошибки
        session.rollback()
        print(f"\n!!! UNEXPECTED ERROR during seeding: {e} !!!")
        traceback.print_exc()

```

```python
# filepath: /home/me/ВКР/maps_backend/competencies_matrix/logic.py
# competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
from sqlalchemy.orm import joinedload, selectinload, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError # Импортируем IntegrityError
from sqlalchemy import exists, and_
import traceback
# Импортируем парсер ФГОС
from .fgos_parser import parse_fgos_pdf, parse_uk_opk_simple # parse_uk_opk_simple тоже может пригодиться в будущем сидере
# Импортируем парсер ПС
from .parsers import parse_prof_standard_upload # Переименовал для ясности
# Импортируем модели ПС, если они не импортируются автоматически через BaseModel или другие связи
from .models import (
    GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
)

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
        session: Session = db.session # Используем сессию явно
        # Используем joinedload для предзагрузки первого AUP
        # Это может ускорить отображение списка, если первый_aup_id используется на фронте
        programs = session.query(EducationalProgram).options( # Используем session.query
             joinedload(EducationalProgram.aup_assoc).joinedload(EducationalProgramAup.aup)
        ).order_by(EducationalProgram.title).all()
        return programs
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_educational_programs_list: {e}", exc_info=True) # Добавлено exc_info
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
        session: Session = db.session # Используем сессию
        program = session.query(EducationalProgram).options( # Используем session.query
            # Эффективно загружаем связанные данные одним запросом
            selectinload(EducationalProgram.fgos),
            selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
            selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard)
        ).get(program_id)

        if not program:
            logger.warning(f"Program with id {program_id} not found for details.")
            return None

        # Сериализуем программу основные поля без связей
        details = program.to_dict() # Используем to_dict из BaseModel

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
                            'name': assoc.prof_standard.name,
                            'is_mandatory': assoc.is_mandatory, # Добавляем метаданные связи
                            'description': assoc.description,
                        })
                    
        details['recommended_ps_list'] = recommended_ps_list

        return details
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_program_details for program_id {program_id}: {e}", exc_info=True)
        return None
    except AttributeError as e: # Может быть при неполноте данных (например, AUP_assoc, но AUP==None)
        logger.error(f"Attribute error likely due to missing relationship/data in get_program_details for program_id {program_id}: {e}", exc_info=True)
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
            selectinload(AupInfo.education_programs_assoc).selectinload(EducationalProgramAup.educational_program).selectinload(EducationalProgram.fgos) # Загружаем FGOS через ОП
        ).get(aup_id)

        if not aup_info:
            logger.warning(f"AUP with id {aup_id} not found for matrix.")
            return None

        # 2. Находим связанную ОП и ФГОС
        program = None
        fgos = None
        if aup_info.education_programs_assoc:
             # Предполагаем, что AUP связан только с одной ОП в контексте матрицы
             # TODO: Уточнить логику, если AUP связан с несколькими ОП
             program_assoc = aup_info.education_programs_assoc[0]
             program = program_assoc.educational_program
             if program and program.fgos:
                  fgos = program.fgos # FGOS уже загружен благодаря selectinload

        if not program:
             logger.warning(f"AUP {aup_id} is not linked to any Educational Program.")
             # TODO: Если АУП не связан с ОП, что показываем? Пустую матрицу? Ошибку?
             # Пока возвращаем None, чтобы фронтенд показал ошибку.
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
            # Пропускаем записи без привязки к дисциплине (например, служебные строки)
            if entry.id_discipline is None or entry.discipline is None:
                continue
            
            # TODO: Возможно, добавить фильтрацию по типам записей AupData (только Дисциплины)
            # if entry.id_type_record != 1: # 1 - Дисциплина, нужно уточнить ID в справочнике D_TypeRecord
            #     continue

            discipline_title = entry.discipline.title
            discipline_data = {
                "aup_data_id": entry.id,
                "discipline_id": entry.id_discipline,
                "title": discipline_title,
                "semester": entry.id_period # Семестр хранится в id_period AupData
            }
            disciplines_list.append(discipline_data)
            aup_data_ids_in_matrix.add(entry.id)

        # Сортировка списка дисциплин уже сделана ORM по id_period и num_row, что обычно соответствует порядку в АУП
        # disciplines_list.sort(key=lambda d: (d.get('semester', 0), d.get('title', ''))) # На всякий случай можно оставить, но ORM должен справиться
        logger.info(f"Found {len(disciplines_list)} relevant AupData entries for AUP {aup_id}.")

        # 4. Получаем релевантные компетенции и их индикаторы
        # УК и ОПК берутся из ФГОС, связанного с ОП
        # ПК берутся из тех, что созданы пользователем и связаны с ОП
        
        relevant_competencies_query = session.query(Competency).options(
            selectinload(Competency.indicators),
            joinedload(Competency.competency_type)
        )

        relevant_competencies = []

        # Получаем УК и ОПК, связанные с данным ФГОС (если ФГОС есть)
        if fgos:
            uk_opk_competencies = relevant_competencies_query.filter(
                Competency.fgos_vo_id == fgos.id # Фильтруем по FK на ФГОС
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


        # Получаем ПК, связанные с данной ОП
        # Логика связи ПК с ОП: Компетенция (ПК) может быть создана на основе ТФ (LaborFunction).
        # LaborFunction принадлежит Профстандарту (ProfStandard).
        # Профстандарт может быть выбран для Образовательной Программы (EducationalProgramPs).
        # Поэтому, чтобы получить ПК для данной ОП, нужно найти все ТФ из ПС, выбранных для этой ОП,
        # и все ПК, основанные на этих ТФ.
        # Также, ПК могут быть созданы не на основе ТФ, а просто вручную и связаны с ОП напрямую (если такая связь есть в модели).
        # На данном этапе (MVP) временно берем ВСЕ ПК, т.к. логика связи ПК с ОП через ПС/ТФ еще не полностью реализована/верифицирована.
        
        # TODO: Реализовать правильную фильтрацию ПК по ОП
        # Вариант 1 (Если ПК напрямую связаны с ОП):
        # pk_competencies = relevant_competencies_query.join(EducationalProgramCompetency).filter(EducationalProgramCompetency.program_id == program.id).all()
        # Вариант 2 (Если ПК связаны через ТФ, ПС, ОП-ПС):
        # pk_competencies = relevant_competencies_query.join(LaborFunction).join(ProfStandard).join(EducationalProgramPs).filter(EducationalProgramPs.educational_program_id == program.id).all()
        # На данном этапе, берем все ПК:
        pk_competencies = relevant_competencies_query.join(CompetencyType).filter(CompetencyType.code == 'ПК').all()
        relevant_competencies.extend(pk_competencies)
        logger.info(f"Found {len(pk_competencies)} ПК competencies (all existing ПК).")


        # Форматируем результат
        competencies_data = []
        indicator_ids_in_matrix = set()
        
        # Сортируем релевантные компетенции перед форматированием
        # Сортировка: сначала УК, потом ОПК, потом ПК; внутри каждого типа - по коду
        type_order = ['УК', 'ОПК', 'ПК']
        relevant_competencies.sort(key=lambda c: (
            type_order.index(c.competency_type.code) if c.competency_type and c.competency_type.code in type_order else len(type_order), # Неизвестные типы в конец
            c.code
        ))

        for comp in relevant_competencies:
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"

            # Используем .to_dict() из BaseModel для сериализации полей
            comp_dict = comp.to_dict()
            comp_dict.pop('fgos', None) # Удаляем объект Fgos
            comp_dict.pop('competency_type', None) # Удаляем объект CompetencyType
            comp_dict.pop('based_on_labor_function', None) # Удаляем объект LaborFunction
            comp_dict.pop('matrix_links', None) # Удаляем связи матрицы, они в отдельном массиве

            comp_dict['type_code'] = type_code # Добавляем код типа явно
            comp_dict['indicators'] = []
            if comp.indicators:
                # Сортируем индикаторы внутри компетенции
                sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                for ind in sorted_indicators:
                    indicator_ids_in_matrix.add(ind.id)
                    # Сериализуем индикатор
                    ind_dict = ind.to_dict()
                    ind_dict.pop('competency', None) # Удаляем родительскую компетенцию
                    ind_dict.pop('labor_functions', None) # Удаляем связанные ТФ
                    ind_dict.pop('matrix_entries', None) # Удаляем связи матрицы
                    comp_dict['indicators'].append(ind_dict)
            competencies_data.append(comp_dict)

        logger.info(f"Formatted {len(competencies_data)} relevant competencies with indicators.")

        # 5. Получаем существующие связи
        existing_links_data = []
        # Проверяем, что списки ID не пустые, чтобы избежать ошибки .in_([])
        if aup_data_ids_in_matrix and indicator_ids_in_matrix:
            # Используем .in_() для эффективного запроса
            existing_links_db = session.query(CompetencyMatrix).filter(
                and_(
                   CompetencyMatrix.aup_data_id.in_(list(aup_data_ids_in_matrix)), # Преобразуем set в list
                   CompetencyMatrix.indicator_id.in_(list(indicator_ids_in_matrix)) # Преобразуем set в list
                )
            ).all()
            # Сериализуем связи
            existing_links_data = [
                link.to_dict() for link in existing_links_db # Используем to_dict из BaseModel
            ]
            logger.info(f"Found {len(existing_links_data)} existing matrix links for relevant AupData and Indicators.")


        # 6. Предложения от NLP (заглушка для MVP)
        # suggestions_data = suggest_links_nlp(disciplines_list, competencies_data) # Заглушка

        # Сериализуем AupInfo в конце
        aup_info_dict = aup_info.as_dict() # Используем as_dict из maps.models.py
        # Удаляем relation properties, если они есть в as_dict
        aup_info_dict.pop('education_programs_assoc', None)
        # Добавляем num_aup если он не попал в as_dict (хотя должен)
        # if 'num_aup' not in aup_info_dict and hasattr(aup_info, 'num_aup'):
        #      aup_info_dict['num_aup'] = aup_info.num_aup


        return {
            "aup_info": aup_info_dict,
            "disciplines": disciplines_list,
            "competencies": competencies_data,
            "links": existing_links_data,
            "suggestions": [] # Заглушка для NLP
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
                'error_type': '...' (о
```

```python
# filepath: /home/me/ВКР/maps_backend/competencies_matrix/logic.py
# competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
from sqlalchemy.orm import joinedload, selectinload, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError # Импортируем IntegrityError
from sqlalchemy import exists, and_
import traceback
# Импортируем парсер ФГОС
from .fgos_parser import parse_fgos_pdf, parse_uk_opk_simple # parse_uk_opk_simple тоже может пригодиться в будущем сидере
# Импортируем парсер ПС
from .parsers import parse_prof_standard_upload # Переименовал для ясности
# Импортируем модели ПС, если они не импортируются автоматически через BaseModel или другие связи
from .models import (
    GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
)

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
        session: Session = db.session # Используем сессию явно
        # Используем joinedload для предзагрузки первого AUP
        # Это может ускорить отображение списка, если первый_aup_id используется на фронте
        programs = session.query(EducationalProgram).options( # Используем session.query
             joinedload(EducationalProgram.aup_assoc).joinedload(EducationalProgramAup.aup)
        ).order_by(EducationalProgram.title).all()
        return programs
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_educational_programs_list: {e}", exc_info=True) # Добавлено exc_info
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
        session: Session = db.session # Используем сессию
        program = session.query(EducationalProgram).options( # Используем session.query
            # Эффективно загружаем связанные данные одним запросом
            selectinload(EducationalProgram.fgos),
            selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
            selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard)
        ).get(program_id)

        if not program:
            logger.warning(f"Program with id {program_id} not found for details.")
            return None

        # Сериализуем программу основные поля без связей
        details = program.to_dict() # Используем to_dict из BaseModel

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
                            'name': assoc.prof_standard.name,
                            'is_mandatory': assoc.is_mandatory, # Добавляем метаданные связи
                            'description': assoc.description,
                        })
                    
        details['recommended_ps_list'] = recommended_ps_list

        return details
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_program_details for program_id {program_id}: {e}", exc_info=True)
        return None
    except AttributeError as e: # Может быть при неполноте данных (например, AUP_assoc, но AUP==None)
        logger.error(f"Attribute error likely due to missing relationship/data in get_program_details for program_id {program_id}: {e}", exc_info=True)
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
            selectinload(AupInfo.education_programs_assoc).selectinload(EducationalProgramAup.educational_program).selectinload(EducationalProgram.fgos) # Загружаем FGOS через ОП
        ).get(aup_id)

        if not aup_info:
            logger.warning(f"AUP with id {aup_id} not found for matrix.")
            return None

        # 2. Находим связанную ОП и ФГОС
        program = None
        fgos = None
        if aup_info.education_programs_assoc:
             # Предполагаем, что AUP связан только с одной ОП в контексте матрицы
             # TODO: Уточнить логику, если AUP связан с несколькими ОП
             program_assoc = aup_info.education_programs_assoc[0]
             program = program_assoc.educational_program
             if program and program.fgos:
                  fgos = program.fgos # FGOS уже загружен благодаря selectinload

        if not program:
             logger.warning(f"AUP {aup_id} is not linked to any Educational Program.")
             # TODO: Если АУП не связан с ОП, что показываем? Пустую матрицу? Ошибку?
             # Пока возвращаем None, чтобы фронтенд показал ошибку.
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
            # Пропускаем записи без привязки к дисциплине (например, служебные строки)
            if entry.id_discipline is None or entry.discipline is None:
                continue
            
            # TODO: Возможно, добавить фильтрацию по типам записей AupData (только Дисциплины)
            # if entry.id_type_record != 1: # 1 - Дисциплина, нужно уточнить ID в справочнике D_TypeRecord
            #     continue

            discipline_title = entry.discipline.title
            discipline_data = {
                "aup_data_id": entry.id,
                "discipline_id": entry.id_discipline,
                "title": discipline_title,
                "semester": entry.id_period # Семестр хранится в id_period AupData
            }
            disciplines_list.append(discipline_data)
            aup_data_ids_in_matrix.add(entry.id)

        # Сортировка списка дисциплин уже сделана ORM по id_period и num_row, что обычно соответствует порядку в АУП
        # disciplines_list.sort(key=lambda d: (d.get('semester', 0), d.get('title', ''))) # На всякий случай можно оставить, но ORM должен справиться
        logger.info(f"Found {len(disciplines_list)} relevant AupData entries for AUP {aup_id}.")

        # 4. Получаем релевантные компетенции и их индикаторы
        # УК и ОПК берутся из ФГОС, связанного с ОП
        # ПК берутся из тех, что созданы пользователем и связаны с ОП
        
        relevant_competencies_query = session.query(Competency).options(
            selectinload(Competency.indicators),
            joinedload(Competency.competency_type)
        )

        relevant_competencies = []

        # Получаем УК и ОПК, связанные с данным ФГОС (если ФГОС есть)
        if fgos:
            uk_opk_competencies = relevant_competencies_query.filter(
                Competency.fgos_vo_id == fgos.id # Фильтруем по FK на ФГОС
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


        # Получаем ПК, связанные с данной ОП
        # Логика связи ПК с ОП: Компетенция (ПК) может быть создана на основе ТФ (LaborFunction).
        # LaborFunction принадлежит Профстандарту (ProfStandard).
        # Профстандарт может быть выбран для Образовательной Программы (EducationalProgramPs).
        # Поэтому, чтобы получить ПК для данной ОП, нужно найти все ТФ из ПС, выбранных для этой ОП,
        # и все ПК, основанные на этих ТФ.
        # Также, ПК могут быть созданы не на основе ТФ, а просто вручную и связаны с ОП напрямую (если такая связь есть в модели).
        # На данном этапе (MVP) временно берем ВСЕ ПК, т.к. логика связи ПК с ОП через ПС/ТФ еще не полностью реализована/верифицирована.
        
        # TODO: Реализовать правильную фильтрацию ПК по ОП
        # Вариант 1 (Если ПК напрямую связаны с ОП):
        # pk_competencies = relevant_competencies_query.join(EducationalProgramCompetency).filter(EducationalProgramCompetency.program_id == program.id).all()
        # Вариант 2 (Если ПК связаны через ТФ, ПС, ОП-ПС):
        # pk_competencies = relevant_competencies_query.join(LaborFunction).join(ProfStandard).join(EducationalProgramPs).filter(EducationalProgramPs.educational_program_id == program.id).all()
        # На данном этапе, берем все ПК:
        pk_competencies = relevant_competencies_query.join(CompetencyType).filter(CompetencyType.code == 'ПК').all()
        relevant_competencies.extend(pk_competencies)
        logger.info(f"Found {len(pk_competencies)} ПК competencies (all existing ПК).")


        # Форматируем результат
        competencies_data = []
        indicator_ids_in_matrix = set()
        
        # Сортируем релевантные компетенции перед форматированием
        # Сортировка: сначала УК, потом ОПК, потом ПК; внутри каждого типа - по коду
        type_order = ['УК', 'ОПК', 'ПК']
        relevant_competencies.sort(key=lambda c: (
            type_order.index(c.competency_type.code) if c.competency_type and c.competency_type.code in type_order else len(type_order), # Неизвестные типы в конец
            c.code
        ))

        for comp in relevant_competencies:
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"

            # Используем .to_dict() из BaseModel для сериализации полей
            comp_dict = comp.to_dict()
            comp_dict.pop('fgos', None) # Удаляем объект Fgos
            comp_dict.pop('competency_type', None) # Удаляем объект CompetencyType
            comp_dict.pop('based_on_labor_function', None) # Удаляем объект LaborFunction
            comp_dict.pop('matrix_links', None) # Удаляем связи матрицы, они в отдельном массиве

            comp_dict['type_code'] = type_code # Добавляем код типа явно
            comp_dict['indicators'] = []
            if comp.indicators:
                # Сортируем индикаторы внутри компетенции
                sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                for ind in sorted_indicators:
                    indicator_ids_in_matrix.add(ind.id)
                    # Сериализуем индикатор
                    ind_dict = ind.to_dict()
                    ind_dict.pop('competency', None) # Удаляем родительскую компетенцию
                    ind_dict.pop('labor_functions', None) # Удаляем связанные ТФ
                    ind_dict.pop('matrix_entries', None) # Удаляем связи матрицы
                    comp_dict['indicators'].append(ind_dict)
            competencies_data.append(comp_dict)

        logger.info(f"Formatted {len(competencies_data)} relevant competencies with indicators.")

        # 5. Получаем существующие связи
        existing_links_data = []
        # Проверяем, что списки ID не пустые, чтобы избежать ошибки .in_([])
        if aup_data_ids_in_matrix and indicator_ids_in_matrix:
            # Используем .in_() для эффективного запроса
            existing_links_db = session.query(CompetencyMatrix).filter(
                and_(
                   CompetencyMatrix.aup_data_id.in_(list(aup_data_ids_in_matrix)), # Преобразуем set в list
                   CompetencyMatrix.indicator_id.in_(list(indicator_ids_in_matrix)) # Преобразуем set в list
                )
            ).all()
            # Сериализуем связи
            existing_links_data = [
                link.to_dict() for link in existing_links_db # Используем to_dict из BaseModel
            ]
            logger.info(f"Found {len(existing_links_data)} existing matrix links for relevant AupData and Indicators.")


        # 6. Предложения от NLP (заглушка для MVP)
        # suggestions_data = suggest_links_nlp(disciplines_list, competencies_data) # Заглушка

        # Сериализуем AupInfo в конце
        aup_info_dict = aup_info.as_dict() # Используем as_dict из maps.models.py
        # Удаляем relation properties, если они есть в as_dict
        aup_info_dict.pop('education_programs_assoc', None)
        # Добавляем num_aup если он не попал в as_dict (хотя должен)
        # if 'num_aup' not in aup_info_dict and hasattr(aup_info, 'num_aup'):
        #      aup_info_dict['num_aup'] = aup_info.num_aup


        return {
            "aup_info": aup_info_dict,
            "disciplines": disciplines_list,
            "competencies": competencies_data,
            "links": existing_links_data,
            "suggestions": [] # Заглушка для NLP
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
                'error_type': '...' (о
```

```python
# filepath: /home/me/ВКР/maps_backend/competencies_matrix/logic.py
# competencies_matrix/logic.py
from typing import Dict, List, Any, Optional
import datetime
from sqlalchemy.orm import joinedload, selectinload, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError # Импортируем IntegrityError
from sqlalchemy import exists, and_
import traceback
# Импортируем парсер ФГОС
from .fgos_parser import parse_fgos_pdf, parse_uk_opk_simple # parse_uk_opk_simple тоже может пригодиться в будущем сидере
# Импортируем парсер ПС
from .parsers import parse_prof_standard_upload # Переименовал для ясности
# Импортируем модели ПС, если они не импортируются автоматически через BaseModel или другие связи
from .models import (
    GeneralizedLaborFunction, LaborFunction, LaborAction, RequiredSkill, RequiredKnowledge
)

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
        session: Session = db.session # Используем сессию явно
        # Используем joinedload для предзагрузки первого AUP
        # Это может ускорить отображение списка, если первый_aup_id используется на фронте
        programs = session.query(EducationalProgram).options( # Используем session.query
             joinedload(EducationalProgram.aup_assoc).joinedload(EducationalProgramAup.aup)
        ).order_by(EducationalProgram.title).all()
        return programs
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_educational_programs_list: {e}", exc_info=True) # Добавлено exc_info
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
        session: Session = db.session # Используем сессию
        program = session.query(EducationalProgram).options( # Используем session.query
            # Эффективно загружаем связанные данные одним запросом
            selectinload(EducationalProgram.fgos),
            selectinload(EducationalProgram.aup_assoc).selectinload(EducationalProgramAup.aup),
            selectinload(EducationalProgram.selected_ps_assoc).selectinload(EducationalProgramPs.prof_standard)
        ).get(program_id)

        if not program:
            logger.warning(f"Program with id {program_id} not found for details.")
            return None

        # Сериализуем программу основные поля без связей
        details = program.to_dict() # Используем to_dict из BaseModel

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
                            'name': assoc.prof_standard.name,
                            'is_mandatory': assoc.is_mandatory, # Добавляем метаданные связи
                            'description': assoc.description,
                        })
                    
        details['recommended_ps_list'] = recommended_ps_list

        return details
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_program_details for program_id {program_id}: {e}", exc_info=True)
        return None
    except AttributeError as e: # Может быть при неполноте данных (например, AUP_assoc, но AUP==None)
        logger.error(f"Attribute error likely due to missing relationship/data in get_program_details for program_id {program_id}: {e}", exc_info=True)
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
            selectinload(AupInfo.education_programs_assoc).selectinload(EducationalProgramAup.educational_program).selectinload(EducationalProgram.fgos) # Загружаем FGOS через ОП
        ).get(aup_id)

        if not aup_info:
            logger.warning(f"AUP with id {aup_id} not found for matrix.")
            return None

        # 2. Находим связанную ОП и ФГОС
        program = None
        fgos = None
        if aup_info.education_programs_assoc:
             # Предполагаем, что AUP связан только с одной ОП в контексте матрицы
             # TODO: Уточнить логику, если AUP связан с несколькими ОП
             program_assoc = aup_info.education_programs_assoc[0]
             program = program_assoc.educational_program
             if program and program.fgos:
                  fgos = program.fgos # FGOS уже загружен благодаря selectinload

        if not program:
             logger.warning(f"AUP {aup_id} is not linked to any Educational Program.")
             # TODO: Если АУП не связан с ОП, что показываем? Пустую матрицу? Ошибку?
             # Пока возвращаем None, чтобы фронтенд показал ошибку.
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
            # Пропускаем записи без привязки к дисциплине (например, служебные строки)
            if entry.id_discipline is None or entry.discipline is None:
                continue
            
            # TODO: Возможно, добавить фильтрацию по типам записей AupData (только Дисциплины)
            # if entry.id_type_record != 1: # 1 - Дисциплина, нужно уточнить ID в справочнике D_TypeRecord
            #     continue

            discipline_title = entry.discipline.title
            discipline_data = {
                "aup_data_id": entry.id,
                "discipline_id": entry.id_discipline,
                "title": discipline_title,
                "semester": entry.id_period # Семестр хранится в id_period AupData
            }
            disciplines_list.append(discipline_data)
            aup_data_ids_in_matrix.add(entry.id)

        # Сортировка списка дисциплин уже сделана ORM по id_period и num_row, что обычно соответствует порядку в АУП
        # disciplines_list.sort(key=lambda d: (d.get('semester', 0), d.get('title', ''))) # На всякий случай можно оставить, но ORM должен справиться
        logger.info(f"Found {len(disciplines_list)} relevant AupData entries for AUP {aup_id}.")

        # 4. Получаем релевантные компетенции и их индикаторы
        # УК и ОПК берутся из ФГОС, связанного с ОП
        # ПК берутся из тех, что созданы пользователем и связаны с ОП
        
        relevant_competencies_query = session.query(Competency).options(
            selectinload(Competency.indicators),
            joinedload(Competency.competency_type)
        )

        relevant_competencies = []

        # Получаем УК и ОПК, связанные с данным ФГОС (если ФГОС есть)
        if fgos:
            uk_opk_competencies = relevant_competencies_query.filter(
                Competency.fgos_vo_id == fgos.id # Фильтруем по FK на ФГОС
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


        # Получаем ПК, связанные с данной ОП
        # Логика связи ПК с ОП: Компетенция (ПК) может быть создана на основе ТФ (LaborFunction).
        # LaborFunction принадлежит Профстандарту (ProfStandard).
        # Профстандарт может быть выбран для Образовательной Программы (EducationalProgramPs).
        # Поэтому, чтобы получить ПК для данной ОП, нужно найти все ТФ из ПС, выбранных для этой ОП,
        # и все ПК, основанные на этих ТФ.
        # Также, ПК могут быть созданы не на основе ТФ, а просто вручную и связаны с ОП напрямую (если такая связь есть в модели).
        # На данном этапе (MVP) временно берем ВСЕ ПК, т.к. логика связи ПК с ОП через ПС/ТФ еще не полностью реализована/верифицирована.
        
        # TODO: Реализовать правильную фильтрацию ПК по ОП
        # Вариант 1 (Если ПК напрямую связаны с ОП):
        # pk_competencies = relevant_competencies_query.join(EducationalProgramCompetency).filter(EducationalProgramCompetency.program_id == program.id).all()
        # Вариант 2 (Если ПК связаны через ТФ, ПС, ОП-ПС):
        # pk_competencies = relevant_competencies_query.join(LaborFunction).join(ProfStandard).join(EducationalProgramPs).filter(EducationalProgramPs.educational_program_id == program.id).all()
        # На данном этапе, берем все ПК:
        pk_competencies = relevant_competencies_query.join(CompetencyType).filter(CompetencyType.code == 'ПК').all()
        relevant_competencies.extend(pk_competencies)
        logger.info(f"Found {len(pk_competencies)} ПК competencies (all existing ПК).")


        # Форматируем результат
        competencies_data = []
        indicator_ids_in_matrix = set()
        
        # Сортируем релевантные компетенции перед форматированием
        # Сортировка: сначала УК, потом ОПК, потом ПК; внутри каждого типа - по коду
        type_order = ['УК', 'ОПК', 'ПК']
        relevant_competencies.sort(key=lambda c: (
            type_order.index(c.competency_type.code) if c.competency_type and c.competency_type.code in type_order else len(type_order), # Неизвестные типы в конец
            c.code
        ))

        for comp in relevant_competencies:
            type_code = comp.competency_type.code if comp.competency_type else "UNKNOWN"

            # Используем .to_dict() из BaseModel для сериализации полей
            comp_dict = comp.to_dict()
            comp_dict.pop('fgos', None) # Удаляем объект Fgos
            comp_dict.pop('competency_type', None) # Удаляем объект CompetencyType
            comp_dict.pop('based_on_labor_function', None) # Удаляем объект LaborFunction
            comp_dict.pop('matrix_links', None) # Удаляем связи матрицы, они в отдельном массиве

            comp_dict['type_code'] = type_code # Добавляем код типа явно
            comp_dict['indicators'] = []
            if comp.indicators:
                # Сортируем индикаторы внутри компетенции
                sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                for ind in sorted_indicators:
                    indicator_ids_in_matrix.add(ind.id)
                    # Сериализуем индикатор
                    ind_dict = ind.to_dict()
                    ind_dict.pop('competency', None) # Удаляем родительскую компетенцию
                    ind_dict.pop('labor_functions', None) # Удаляем связанные ТФ
                    ind_dict.pop('matrix_entries', None) # Удаляем связи матрицы
                    comp_dict['indicators'].append(ind_dict)
            competencies_data.append(comp_dict)

        logger.info(f"Formatted {len(competencies_data)} relevant competencies with indicators.")

        # 5. Получаем существующие связи
        existing_links_data = []
        # Проверяем, что списки ID не пустые, чтобы избежать ошибки .in_([])
        if aup_data_ids_in_matrix and indicator_ids_in_matrix:
            # Используем .in_() для эффективного запроса
            existing_links_db = session.query(CompetencyMatrix).filter(
                and_(
                   CompetencyMatrix.aup_data_id.in_(list(aup_data_ids_in_matrix)), # Преобразуем set в list
                   CompetencyMatrix.indicator_id.in_(list(indicator_ids_in_matrix)) # Преобразуем set в list
                )
            ).all()
            # Сериализуем связи
            existing_links_data = [
                link.to_dict() for link in existing_links_db # Используем to_dict из BaseModel
            ]
            logger.info(f"Found {len(existing_links_data)} existing matrix links for relevant AupData and Indicators.")


        # 6. Предложения от NLP (заглушка для MVP)
        # suggestions_data = suggest_links_nlp(disciplines_list, competencies_data) # Заглушка

        # Сериализуем AupInfo в конце
        aup_info_dict = aup_info.as_dict() # Используем as_dict из maps.models.py
        # Удаляем relation properties, если они есть в as_dict
        aup_info_dict.pop('education_programs_assoc', None)
        # Добавляем num_aup если он не попал в as_dict (хотя должен)
        # if 'num_aup' not in aup_info_dict and hasattr(aup_info, 'num_aup'):
        #      aup_info_dict['num_aup'] = aup_info.num_aup


        return {
            "aup_info": aup_info_dict,
            "disciplines": disciplines_list,
            "competencies": competencies_data,
            "links": existing_links_data,
            "suggestions": [] # Заглушка для NLP
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
                'error_type': '...' (о
```

```python
# filepath: /home/me/ВКР/maps_backend/cli_commands/db_seed.py
# filepath: /home/me/ВКР/maps_backend/cli_commands/db_seed.py
import click
from flask.cli import with_appcontext
import datetime
import traceback
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import random

# --- Import all necessary models ---
# You need to import 'db' and all models used within the seed_command function
from maps.models import (
    db, SprDiscipline, AupInfo, AupData, SprFaculty, Department,
    SprDegreeEducation, SprFormEducation, SprRop, NameOP, Groups, SprOKCO,
    D_Blocks, D_Part, D_TypeRecord, D_ControlType, D_EdIzmereniya, D_Period, SprBranch, D_Modules
)
from auth.models import Roles, Users
from competencies_matrix.models import (
    CompetencyType, FgosVo, EducationalProgram, Competency, Indicator,
    CompetencyMatrix, EducationalProgramAup, EducationalProgramPs,
    ProfStandard, FgosRecommendedPs, IndicatorPsLink, LaborFunction, # Import LaborFunction
    GeneralizedLaborFunction, LaborAction, RequiredSkill, RequiredKnowledge # Import other PS structure models
)
from cabinet.models import (
    StudyGroups, SprPlace, SprBells, DisciplineTable,
    GradeType, Topics, Students, Tutors, Grade, GradeColumn,
    TutorsOrder, TutorsOrderRow
)

# Assuming Mode model exists, potentially in a general config or base models file
# If it's elsewhere, adjust the import accordingly
# from some_module import Mode # Placeholder for Mode import

@click.command(name='seed_db')
@with_appcontext
def seed_command():
    """Заполняет базу данных начальными/тестовыми данными (Идемпотентно)."""
    print("Starting database seeding...")
    try:
        session = db.session # Получаем сессию
        
        # === БЛОК 1: Основные Справочники (Первоочередные) ===
        print("Seeding Core Lookups...")

        # Используем merge для идемпотентности - он вставит или обновит по PK
        # Сначала справочники без зависимостей
        session.merge(CompetencyType(id=1, code='УК', name='Универсальная'))
        session.merge(CompetencyType(id=2, code='ОПК', name='Общепрофессиональная'))
        session.merge(CompetencyType(id=3, code='ПК', code_name='Профессиональная')) # Уточнено code_name

        session.merge(Roles(id_role=1, name_role='admin'))
        session.merge(Roles(id_role=2, name_role='methodologist'))
        session.merge(Roles(id_role=3, name_role='teacher'))
        session.merge(Roles(id_role=4, name_role='tutor'))
        session.merge(Roles(id_role=5, name_role='student'))

        # Справочники для АУП (ID как в сидере)
        session.merge(SprBranch(id_branch=1, city='Москва', location='Основное подразделение')) # Имя поля уточнено
        session.merge(SprDegreeEducation(id_degree=1, name_deg="Высшее образование - бакалавриат")) # Имя поля уточнено
        session.merge(SprFormEducation(id_form=1, form="Очная")) # Имя поля уточнено
        session.merge(SprRop(id_rop=1, last_name='Иванов', first_name='Иван', middle_name='Иванович', email='rop@example.com', telephone='+70000000000'))
        # Замени на реальные данные для SprOKCO и NameOP если они используются как FK
        session.merge(SprOKCO(program_code='09.03.01', name_okco='Информатика и ВТ')) # Пример ОКСО
        session.merge(NameOP(id_spec=1, program_code='09.03.01', num_profile='01', name_spec='Веб-технологии')) # Пример NameOP

        # Добавляем факультет и кафедру (департамент) - обязательно перед АУП
        faculty_1 = session.merge(SprFaculty(id_faculty=1, name_faculty='Факультет информатики', id_branch=1))
        department_1 = session.merge(Department(id_department=1, name_department='Кафедра веб-технологий'))
        session.commit()  # Коммитим факультет и кафедру

        # Справочники для AupData (ID как в сидере)
        session.merge(D_Blocks(id=1, title="Блок 1. Дисциплины (модули)"))
        session.merge(D_Part(id=1, title="Обязательная часть"))
        session.merge(D_Modules(id=1, title="Базовый модуль", color="#FFFFFF")) # Добавлен цвет
        session.merge(Groups(id_group=1, name_group="Основные", color="#FFFFFF", weight=1)) # Имя поля уточнено
        session.merge(D_TypeRecord(id=1, title="Дисциплина"))
        session.merge(D_ControlType(id=1, title="Экзамен", default_shortname="Экз"))
        session.merge(D_ControlType(id=5, title="Зачет", default_shortname="Зач"))
        session.merge(D_EdIzmereniya(id=1, title="Академ. час"))
        session.merge(D_Period(id=1, title="Семестр 1"))
        session.merge(D_Period(id=2, title="Семестр 2"))

        # Справочники Дисциплин
        session.merge(SprDiscipline(id=1001, title='Основы программирования'))
        session.merge(SprDiscipline(id=1002, title='Базы данных'))
        session.merge(SprDiscipline(id=1003, title='История России'))

        # Коммитим все справочники ПЕРЕД созданием зависимых сущностей
        session.commit()
        print("  - Core lookups seeded/merged.")

        # === БЛОК 2: ФГОС и Образовательные Программы ===
        print("Seeding FGOS...")
        # merge вернет объект, который есть в сессии (или новый)
        # Используем дату в формате YYYY-MM-DD
        fgos1 = session.merge(FgosVo(id=1, number='929', date=datetime.date(2017, 9, 19), direction_code='09.03.01',
                                       direction_name='Информатика и вычислительная техника', education_level='бакалавриат', generation='3++', file_path='ФГОС ВО 090301_B_3_19092017.pdf'))
        # Добавим еще один ФГОС для теста
        fgos2 = session.merge(FgosVo(id=2, number='922', date=datetime.date(2020, 8, 7), direction_code='18.03.01',
                                       direction_name='Химическая технология', education_level='бакалавриат', generation='3+', file_path='ФГОС ВО 180301_B_3_07082020.pdf'))
        session.commit()
        print("  - FGOS 09.03.01 and 18.03.01 checked/merged.")

        print("Seeding Educational Program...")
        # ИСПОЛЬЗУЕМ title
        program1 = session.merge(EducationalProgram(id=1, fgos_vo_id=1, code='09.03.01', title='Веб-технологии (09.03.01)',
                                                     profile='Веб-технологии', qualification='Бакалавр', form_of_education='очная', enrollment_year=2024))
        # Добавим еще одну ОП для теста
        program2 = session.merge(EducationalProgram(id=2, fgos_vo_id=2, code='18.03.01', title='Технология переработки пластических масс и эластомеров (18.03.01)',
                                                    profile='Не указан', qualification='Бакалавр', form_of_education='очная', enrollment_year=2024))

        session.commit()
        print("  - Educational Programs checked/merged.")

        # === БЛОК 3: АУП и его структура ===
        print("Seeding AUP...")
        # merge вернет объект AupInfo
        aup101 = session.merge(AupInfo(id_aup=101, num_aup='B093011451', file='example.xlsx', base='11 классов',
                                          id_faculty=1, id_rop=1, type_educ='Высшее', qualification='Бакалавр',
                                          type_standard='ФГОС 3++', id_department=1, period_educ='4 года',
                                          id_degree=1, id_form=1, years=4, months=0, id_spec=1,
                                          year_beg=2024, year_end=2028, is_actual=1))
        # Добавим еще один АУП для теста
        aup102 = session.merge(AupInfo(id_aup=102, num_aup='B180301XXXX', file='example2.xlsx', base='11 классов',
                                       id_faculty=1, id_rop=1, type_educ='Высшее', qualification='Бакалавр',
                                       type_standard='ФГОС 3+', id_department=1, period_educ='4 года',
                                       id_degree=1, id_form=1, years=4, months=0, id_spec=1,
                                       year_beg=2024, year_end=2028, is_actual=1))

        session.commit()
        print("  - AUPs checked/merged.")

        print("Seeding AUP-Program Links...")
        # Для ассоциативных лучше проверка + add
        link_ep_aup1 = EducationalProgramAup.query.filter_by(educational_program_id=1, aup_id=101).first()
        if not link_ep_aup1:
            link_ep_aup1 = EducationalProgramAup(educational_program_id=1, aup_id=101, is_primary=True)
            session.add(link_ep_aup1)
            print("  - Linked Program 1 and AUP 101.")
        else:
            print("  - Link Program 1 - AUP 101 already exists.")

        link_ep_aup2 = EducationalProgramAup.query.filter_by(educational_program_id=2, aup_id=102).first()
        if not link_ep_aup2:
            link_ep_aup2 = EducationalProgramAup(educational_program_id=2, aup_id=102, is_primary=True)
            session.add(link_ep_aup2)
            print("  - Linked Program 2 and AUP 102.")
        else:
            print("  - Link Program 2 - AUP 102 already exists.")


        session.commit()
        print("  - AUP-Program Links checked/merged.")


        print("Seeding AupData entries...")
        # merge вернет объекты AupData - используем _discipline для имени колонки
        ad501 = session.merge(AupData(
            id=501, id_aup=101, id_discipline=1001, _discipline='Основы программирования',
            id_block=1, shifr='Б1.1.07', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=1, num_row=7, id_type_control=1, # Экзамен
            amount=14400, id_edizm=1, zet=4
        ))
        ad502 = session.merge(AupData(
            id=502, id_aup=101, id_discipline=1002, _discipline='Базы данных',
            id_block=1, shifr='Б1.1.10', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=1, num_row=10, id_type_control=5, # Зачет
            amount=10800, id_edizm=1, zet=3
        ))
        ad503 = session.merge(AupData(
            id=503, id_aup=101, id_discipline=1003, _discipline='История России',
            id_block=1, shifr='Б1.1.01', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=1, num_row=1, id_type_control=5, # Зачет
            amount=7200, id_edizm=1, zet=2
        ))
        # Добавим AupData для второго АУП
        ad504 = session.merge(AupData(
            id=504, id_aup=102, id_discipline=1001, _discipline='Основы программирования',
            id_block=1, shifr='Б1.1.08', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=1, num_row=8, id_type_control=1, # Экзамен
            amount=14400, id_edizm=1, zet=4
        ))
        ad505 = session.merge(AupData(
            id=505, id_aup=102, id_discipline=1003, _discipline='История России',
            id_block=1, shifr='Б1.1.01', id_part=1, id_module=1, id_group=1,
            id_type_record=1, id_period=2, num_row=1, id_type_control=5, # Зачет
            amount=7200, id_edizm=1, zet=2
        ))


        session.commit()
        print("  - AupData entries checked/merged.")

        # === БЛОК 4: Компетенции и Индикаторы ===
        print("Seeding Competencies & Indicators...")
        # Используем merge
        # ВАЖНО: Убедись, что поле fgos_vo_id добавлено в модель Competency и миграцию!

        # УК для ФГОС 09.03.01 (fgos_vo_id=1)
        comp_uk1_fgos1 = session.merge(Competency(id=1, competency_type_id=1, fgos_vo_id=1, code='УК-1', name='Способен осуществлять поиск, критический анализ и синтез информации, применять системный подход для решения поставленных задач'))
        comp_uk2_fgos1 = session.merge(Competency(id=2, competency_type_id=1, fgos_vo_id=1, code='УК-2', name='Способен определять круг задач в рамках поставленной цели и выбирать оптимальные способы их решения...'))
        comp_uk3_fgos1 = session.merge(Competency(id=3, competency_type_id=1, fgos_vo_id=1, code='УК-3', name='Способен осуществлять социальное взаимодействие и реализовывать свою роль в команде'))
        comp_uk4_fgos1 = session.merge(Competency(id=4, competency_type_id=1, fgos_vo_id=1, code='УК-4', name='Способен осуществлять деловую коммуникацию в устной и письменной формах на государственном языке РФ...'))
        comp_uk5_fgos1 = session.merge(Competency(id=5, competency_type_id=1, fgos_vo_id=1, code='УК-5', name='Способен воспринимать межкультурное разнообразие общества...'))
        comp_uk6_fgos1 = session.merge(Competency(id=6, competency_type_id=1, fgos_vo_id=1, code='УК-6', name='Способен управлять своим временем, выстраивать и реализовывать траекторию саморазвития...'))
        comp_uk7_fgos1 = session.merge(Competency(id=7, competency_type_id=1, fgos_vo_id=1, code='УК-7', name='Способен поддерживать должный уровень физической подготовленности...'))
        comp_uk8_fgos1 = session.merge(Competency(id=8, competency_type_id=1, fgos_vo_id=1, code='УК-8', name='Способен создавать и поддерживать в повседневной жизни и в профессиональной деятельности безопасные условия...'))
        comp_uk9_fgos1 = session.merge(Competency(id=9, competency_type_id=1, fgos_vo_id=1, code='УК-9', name='Способен принимать обоснованные экономические решения...'))
        comp_uk10_fgos1 = session.merge(Competency(id=10, competency_type_id=1, fgos_vo_id=1, code='УК-10', name='Способен формировать нетерпимое отношение к проявлениям экстремизма, терроризма, коррупционного поведения...'))

        # ОПК для ФГОС 09.03.01 (fgos_vo_id=1)
        comp_opk1_fgos1 = session.merge(Competency(id=101, competency_type_id=2, fgos_vo_id=1, code='ОПК-1', name='Способен применять естественнонаучные и общеинженерные знания...'))
        comp_opk2_fgos1 = session.merge(Competency(id=102, competency_type_id=2, fgos_vo_id=1, code='ОПК-2', name='Способен принимать принципы работы современных информационных технологий...'))
        comp_opk3_fgos1 = session.merge(Competency(id=103, competency_type_id=2, fgos_vo_id=1, code='ОПК-3', name='Способен решать стандартные задачи профессиональной деятельности на основе информационной и библиографической культуры...'))
        comp_opk4_fgos1 = session.merge(Competency(id=104, competency_type_id=2, fgos_vo_id=1, code='ОПК-4', name='Способен участвовать в разработке стандартов, норм и правил...'))
        comp_opk5_fgos1 = session.merge(Competency(id=105, competency_type_id=2, fgos_vo_id=1, code='ОПК-5', name='Способен инсталлировать программное и аппаратное обеспечение...'))
        comp_opk6_fgos1 = session.merge(Competency(id=106, competency_type_id=2, fgos_vo_id=1, code='ОПК-6', name='Способен разрабатывать бизнес-планы и технические задания...'))
        comp_opk7_fgos1 = session.merge(Competency(id=107, competency_type_id=2, fgos_vo_id=1, code='ОПК-7', name='Способен участвовать в настройке и наладке программно-аппаратных комплексов'))
        comp_opk8_fgos1 = session.merge(Competency(id=108, competency_type_id=2, fgos_vo_id=1, code='ОПК-8', name='Способен разрабатывать алгоритмы и программы, пригодные для практического применения'))
        comp_opk9_fgos1 = session.merge(Competency(id=109, competency_type_id=2, fgos_vo_id=1, code='ОПК-9', name='Способен осваивать методики использования программных средств для решения практических задач'))

        # ПК для ОП Веб-технологии (fgos_vo_id=None, т.к. ПК не берутся из ФГОС)
        comp_pk1 = session.merge(Competency(id=201, competency_type_id=3, fgos_vo_id=None, code='ПК-1', name='Способен выполнять работы по созданию (модификации) и сопровождению ИС, автоматизирующих задачи организационного управления и бизнес-процессы'))
        comp_pk2 = session.merge(Competency(id=202, competency_type_id=3, fgos_vo_id=None, code='ПК-2', name='Способен осуществлять управление проектами в области ИТ на основе полученных планов проектов в условиях, когда проект не выходит за пределы утвержденных параметров'))
        comp_pk3 = session.merge(Competency(id=203, competency_type_id=3, fgos_vo_id=None, code='ПК-3', name='Способен разрабатывать требования и проектировать программное обеспечение'))
        comp_pk4 = session.merge(Competency(id=204, competency_type_id=3, fgos_vo_id=None, code='ПК-4', name='Способен проводить работы по интеграции программных модулей и компонент и проверку работоспособности выпусков программных продуктов'))
        comp_pk5 = session.merge(Competency(id=205, competency_type_id=3, fgos_vo_id=None, code='ПК-5', name='Способен осуществлять концептуальное, функциональное и логическое проектирование систем среднего и крупного масштаба и сложности'))


        # Индикаторы - тоже через merge
        # Для УК-1 (ID=1)
        session.merge(Indicator(id=10, competency_id=1, code='ИУК-1.1', formulation='Анализирует задачу, выделяя ее базовые составляющие', source='Распоряжение 505-Р'))
        session.merge(Indicator(id=11, competency_id=1, code='ИУК-1.2', formulation='Осуществляет поиск, критически оценивает, обобщает, систематизирует и ранжирует информацию...', source='Распоряжение 505-Р'))
        session.merge(Indicator(id=12, competency_id=1, code='ИУК-1.3', formulation='Рассматривает и предлагает рациональные варианты решения...', source='Распоряжение 505-Р'))
        # Для УК-2 (ID=2)
        session.merge(Indicator(id=20, competency_id=2, code='ИУК-2.1', formulation='Формулирует совокупность задач в рамках поставленной цели проекта...', source='Распоряжение 505-Р'))
        session.merge(Indicator(id=21, competency_id=2, code='ИУК-2.2', formulation='Определяет связи между поставленными задачами, основными компонентами проекта...', source='Распоряжение 505-Р'))
        session.merge(Indicator(id=22, competency_id=2, code='ИУК-2.3', formulation='Выбирает оптимальные способы планирования, распределения зон ответственности...', source='Распоряжение 505-Р'))
        # ... и так далее для всех УК и ОПК по Распоряжению 505-Р
        # Для УК-5 (ID=5)
        session.merge(Indicator(id=50, competency_id=5, code='ИУК-5.1', formulation='Анализирует и интерпретирует события, современное состояние общества...', source='Распоряжение 505-Р'))
        # Для ОПК-7 (ID=107)
        session.merge(Indicator(id=170, competency_id=107, code='ИОПК-7.1', formulation='Знает основные языки программирования, операционные системы и оболочки, современные среды разработки программного обеспечения', source='ОП Веб-технологии'))
        # ... и так далее для всех ОПК
        
        # Индикаторы для ПК (ИПК) (Пример для ПК-1 ID=201)
        session.merge(Indicator(id=210, competency_id=201, code='ИПК-1.1', formulation='Знает: методологию и технологии проектирования информационных систем; проектирование обеспечивающих подсистем; приемы программирования приложений.', source='ОП Веб-технологии / ПС 06.015'))
        session.merge(Indicator(id=211, competency_id=201, code='ИПК-1.2', formulation='Умеет: создавать, модифицировать и сопровождать информационные системы для решения задач бизнес-процессов и организационного управления...', source='ОП Веб-технологии / ПС 06.015'))
        session.merge(Indicator(id=212, competency_id=201, code='ИПК-1.3', formulation='Владеет: методами создания и сопровождения информационных систем...', source='ОП Веб-технологии / ПС 06.015'))
        # ... и так далее для всех ПК из таблицы 5 ОП Веб-технологии

        session.commit() # Коммитим компетенции и индикаторы
        print("  - Competencies & Indicators checked/merged.")

        # === БЛОК 4.1: Профессиональные Стандарты (Базовая структура) ===
        print("Seeding Basic Professional Standards Structure...")
        # Добавим несколько Профстандартов и базовую структуру (ОТФ, ТФ)
        # Наполнение всей структуры (ТД, НУ, НЗ) и связей ИДК-ТФ/ТД/НУ/НЗ - это задача парсинга ПС и ручного формирования

        ps_prog = session.merge(ProfStandard(id=1, code='06.001', name='Программист', parsed_content='...')) # Добавить markdown контент
        ps_is = session.merge(ProfStandard(id=2, code='06.015', name='Специалист по информационным системам', parsed_content='...'))
        ps_pm = session.merge(ProfStandard(id=3, code='06.016', name='Руководитель проектов в области ИТ', parsed_content='...'))
        ps_sa = session.merge(ProfStandard(id=4, code='06.022', name='Системный аналитик', parsed_content='...'))

        session.commit()
        print("  - ProfStandards checked/merged.")

        # Добавим базовые ОТФ и ТФ для ПС 06.015 (id=2)
        otf_c_06015 = session.merge(GeneralizedLaborFunction(id=1, prof_standard_id=2, code='C', name='Выполнение работ и управление работами по созданию (модификации) и сопровождению ИС...'))
        session.commit()

        tf_c016_06015 = session.merge(LaborFunction(id=1, generalized_labor_function_id=1, code='C/01.6', name='Определение первоначальных требований заказчика к ИС...'))
        tf_c166_06015 = session.merge(LaborFunction(id=2, generalized_labor_function_id=1, code='C/16.6', name='Проектирование и дизайн ИС...'))
        tf_c186_06015 = session.merge(LaborFunction(id=3, generalized_labor_function_id=1, code='C/18.6', name='Организационное и технологическое обеспечение создания программного кода ИС...'))

        session.commit()
        print("  - Basic ОТФ/ТФ for PS 06.015 seeded.")

        # Свяжем ПК-1 (ID=201) с ТФ C/16.6 (ID=2) и C/18.6 (ID=3) из ПС 06.015 (ID=2) как базовые
        # Это связь Competency.based_on_labor_function_id (один-к-одному для ПК, если ПК основана на одной ТФ)
        # Или ПК может быть основана на нескольких ТФ (тогда нужна доп. таблица или поле text/json)
        # ОП Веб-технологии таблица 5 указывает, что ПК-1 основана на ОТФ C ПС 06.015.
        # Давайте свяжем ПК-1 с одной из ключевых ТФ, например C/16.6 (id=2)
        comp_pk1 = session.query(Competency).get(201)
        if comp_pk1 and comp_pk1.based_on_labor_function_id is None:
            tf_c166 = session.query(LaborFunction).get(2)
            if tf_c166:
                comp_pk1.based_on_labor_function_id = tf_c166.id
                session.commit()
                print("  - Linked ПК-1 to TФ C/16.6.")
            else:
                print("  - TФ C/16.6 not found, cannot link ПК-1.")


        # Связи ОП Веб-технологии (ID=1) с выбранными ПС (из таблицы 1 ОП)
        # ПС 06.015, 06.016, 06.022 выбраны. ПС 06.001 тоже, т.к. профиль Программист.
        program1 = session.query(EducationalProgram).get(1)
        ps_ids_for_prog1 = session.query(ProfStandard.id).filter(ProfStandard.code.in_(['06.001', '06.015', '06.016', '06.022'])).all()
        ps_ids_for_prog1 = [id for (id,) in ps_ids_for_prog1] # Преобразуем в список ID

        for ps_id in ps_ids_for_prog1:
            link_ep_ps = EducationalProgramPs.query.filter_by(educational_program_id=1, prof_standard_id=ps_id).first()
            if not link_ep_ps:
                link_ep_ps = EducationalProgramPs(educational_program_id=1, prof_standard_id=ps_id)
                session.add(link_ep_ps)
                print(f"  - Linked Program 1 to ProfStandard ID {ps_id}.")
            else:
                 print(f"  - Link Program 1 to ProfStandard ID {ps_id} already exists.")
        session.commit()
        print("  - Program-ProfStandard links seeded.")


        # Связи ФГОС 09.03.01 (ID=1) с рекомендованными ПС (из приложения к ФГОС)
        # ПС 06.001, 06.004, 06.011, 06.015, 06.016, 06.019, 06.022, 06.025, 06.026, 06.027, 06.028
        fgos1 = session.query(FgosVo).get(1)
        recommended_ps_codes_for_fgos1 = ['06.001', '06.004', '06.011', '06.015', '06.016', '06.019', '06.022', '06.025', '06.026', '06.027', '06.028']
        ps_ids_for_fgos1 = session.query(ProfStandard.id).filter(ProfStandard.code.in_(recommended_ps_codes_for_fgos1)).all()
        ps_ids_for_fgos1 = [id for (id,) in ps_ids_for_fgos1]

        for ps_id in ps_ids_for_fgos1:
             link_fgos_ps = FgosRecommendedPs.query.filter_by(fgos_vo_id=1, prof_standard_id=ps_id).first()
             if not link_fgos_ps:
                  link_fgos_ps = FgosRecommendedPs(fgos_vo_id=1, prof_standard_id=ps_id)
                  session.add(link_fgos_ps)
                  print(f"  - Linked FGOS 1 to Recommended ProfStandard ID {ps_id}.")
             else:
                  print(f"  - Link FGOS 1 to Recommended ProfStandard ID {ps_id} already exists.")
        session.commit()
        print("  - FGOS-RecommendedProfStandard links seeded.")


        # Связи Индикаторов с Трудовыми Функция (IndicatorPsLink)
        # Пример: ИПК-1.1 (id=210) -> ТФ C/01.6 (id=1) и C/16.6 (id=2) из ПС 06.015
        # Это нужно, чтобы знать, какие элементы ПС "формируют" данный ИПК
        ind210 = session.query(Indicator).get(210)
        tf_c016 = session.query(LaborFunction).get(1)
        tf_c166 = session.query(LaborFunction).get(2)

        if ind210 and tf_c016:
             link_ind_tf1 = IndicatorPsLink.query.filter_by(indicator_id=210, labor_function_id=1).first()
             if not link_ind_tf1:
                  link_ind_tf1 = IndicatorPsLink(indicator_id=210, labor_function_id=1, is_manual=True, relevance_score=1.0)
                  session.add(link_ind_tf1)
                  print("  - Linked Indicator 210 to LaborFunction 1.")
             else:
                  print("  - Link Indicator 210 to LaborFunction 1 already exists.")

        if ind210 and tf_c166:
             link_ind_tf2 = IndicatorPsLink.query.filter_by(indicator_id=210, labor_function_id=2).first()
             if not link_ind_tf2:
                  link_ind_tf2 = IndicatorPsLink(indicator_id=210, labor_function_id=2, is_manual=True, relevance_score=1.0)
                  session.add(link_ind_tf2)
                  print("  - Linked Indicator 210 to LaborFunction 2.")
             else:
                  print("  - Link Indicator 210 to LaborFunction 2 already exists.")
        session.commit()
        print("  - Indicator-LaborFunction links seeded.")


        # === БЛОК 5: Связи Матрицы Компетенций ===
        print("Seeding Competency Matrix links...")
        # Используем функцию для проверки и добавления
        def add_link_if_not_exists(aup_data_id, indicator_id):
            # Проверяем существование AupData и Indicator в текущей сессии или БД
            aup_data_rec = session.query(AupData).get(aup_data_id)
            indicator_rec = session.query(Indicator).get(indicator_id)
            if not aup_data_rec or not indicator_rec:
                 print(f"    - SKIPPED link ({aup_data_id} <-> {indicator_id}): AupData or Indicator missing!")
                 return False

            exists = session.query(CompetencyMatrix).filter_by(aup_data_id=aup_data_id, indicator_id=indicator_id).first()
            if not exists:
                link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id, is_manual=True)
                session.add(link)
                print(f"    - Added link ({aup_data_id} <-> {indicator_id})")
                return True
            return True

        # Основы программирования (501) -> ИУК-1.1(10), ИУК-1.2(11), ИУК-1.3(12), ИОПК-7.1(170)
        add_link_if_not_exists(501, 10)
        add_link_if_not_exists(501, 11)
        add_link_if_not_exists(501, 12)
        add_link_if_not_exists(501, 170)
        # История России (503) -> ИУК-5.1(50)
        add_link_if_not_exists(503, 50)
        # Базы данных (502) -> ИПК-1.1(210)
        add_link_if_not_exists(502, 210)

        session.commit() # Коммитим связи
        print("  - Matrix links checked/added based on Excel example.")

        # === БЛОК 6: Тестовый Пользователь ===
        print("Seeding Test User...")
        test_user = Users.query.filter_by(login='testuser').first()
        if not test_user:
            test_user = Users(
                # id_user=999, # Позволим БД самой назначить ID через auto-increment
                login='testuser',
                # Устанавливаем хеш пароля 'password'
                password_hash=generate_password_hash('password', method='pbkdf2:sha256'),
                name='Тестовый Методист',
                email='testuser@example.com',
                approved_lk=True # Предполагаем, что для тестов одобрение ЛК не нужно
                # Добавь department_id, если оно обязательно
            )
            session.add(test_user)
            session.commit() # Коммитим пользователя ПЕРЕД назначением роли
            print(f"  - Added test user 'testuser' with id {test_user.id_user}.")

            # Назначаем роль methodologist (ID=2)
            methodologist_role = Roles.query.get(2)
            if methodologist_role:
                # Используем session.query для проверки наличия роли у пользователя
                if methodologist_role not in test_user.roles: # Проверяем через relationship
                    test_user.roles.append(methodologist_role)
                    session.commit()
                    print("  - Assigned 'methodologist' role to 'testuser'.")
                else:
                    print("  - Role 'methodologist' already assigned to 'testuser'.")
            else:
                print("  - WARNING: Role 'methodologist' (ID=2) not found, skipping role assignment.")
        else:
            print("  - Test user 'testuser' already exists.")

        # === BLOCK 7: Admin User ===
        print("Seeding Admin User...")
        admin_user = Users.query.filter_by(login='admin').first()
        if not admin_user:
            admin_user = Users(
                login='admin',
                password_hash=generate_password_hash('admin', method='pbkdf2:sha256'),
                name='Admin User',
                email='admin@example.com',
                approved_lk=True
            )
            session.add(admin_user)
            session.commit()
            print(f"  - Added admin user 'admin' with id {admin_user.id_user}")

            # Assign admin role (ID=1)
            admin_role = Roles.query.get(1)
            if admin_role:
                # Используем session.query для проверки наличия роли у пользователя
                 if admin_role not in admin_user.roles: # Проверяем через relationship
                    admin_user.roles.append(admin_role)
                    session.commit()
                    print("  - Assigned 'admin' role to admin user")
                 else:
                     print("  - Role 'admin' already assigned to admin user")
            else:
                print("  - WARNING: Role 'admin' (ID=1) not found, skipping role assignment")
        else:
            print("  - Admin user 'admin' already exists")

        # === BLOCK 8: Cabinet Models (Academic Cabinet) ===
        print("Seeding Cabinet Models...")

        # Add classroom locations (SprPlace)
        places = [
            SprPlace(id=1, name="Аудитория", prefix="А", is_online=False),
            SprPlace(id=2, name="Online", prefix="", is_online=True),
            SprPlace(id=3, name="Лаборатория", prefix="Л", is_online=False),
            SprPlace(id=4, name="Компьютерный класс", prefix="КК", is_online=False)
        ]
        for place in places:
            session.merge(place) # Используем session.merge
        session.commit()
        print("  - Classroom locations seeded.")

        # Add bell schedule (SprBells)
        bells = [
            SprBells(id=1, order=1, name="9:00 - 10:30"),
            SprBells(id=2, order=2, name="10:40 - 12:10"),
            SprBells(id=3, order=3, name="12:20 - 13:50"),
            SprBells(id=4, order=4, name="14:30 - 16:00"),
            SprBells(id=5, order=5, name="16:10 - 17:40"),
            SprBells(id=6, order=6, name="17:50 - 19:20")
        ]
        for bell in bells:
            session.merge(bell) # Используем session.merge
        session.commit()
        print("  - Bell schedule seeded.")

        # Add study groups (StudyGroups)
        # Используем session.query для проверки
        test_group = session.query(StudyGroups).filter_by(title="211-321").first()
        if not test_group:
            # Remove the explicit ID to allow auto-increment (или использовать session.merge с id)
            test_group = StudyGroups(
                # Remove id=1 to avoid primary key conflicts
                title="211-321",
                num_aup="B093011451" # Привязываем к AUP 101
            )
            session.add(test_group) # Используем session.add
            session.commit()
            print("  - Study group 211-321 added.")
        else:
            # Update the existing record if needed
            test_group.num_aup = "B093011451"
            session.commit()
            print("  - Study group 211-321 already exists, updated if needed.")

        # Add a test student
        test_student = session.query(Students).filter_by(name="Иванов Иван Иванович").first()
        if not test_student:
            test_student = Students(
                name="Иванов Иван Иванович",
                study_group_id=test_group.id,
                lk_id=1001 # ID из ЛК
            )
            session.add(test_student)
            session.commit()
            print("  - Test student added.")
        else:
            print("  - Test student already exists.")

        # Add a test tutor
        test_tutor = session.query(Tutors).filter_by(name="Петров Петр Петрович").first()
        if not test_tutor:
            test_tutor = Tutors(
                name="Петров Петр Петрович",
                lk_id=2001, # ID из ЛК
                post="Доцент",
                id_department=1  # Using the department added earlier
            )
            session.add(test_tutor)
            session.commit()
            print("  - Test tutor added.")
        else:
            print("  - Test tutor already exists.")

        # Create DisciplineTable entry for the test AUP and group
        discipline_table = session.query(DisciplineTable).filter_by(
            id_aup=101, # Привязываем к AUP 101
            id_unique_discipline=1001, # Привязываем к Основам программирования
            study_group_id=test_group.id,
            semester=1
        ).first()

        if not discipline_table:
            # Remove explicit ID if using auto-increment
            discipline_table = DisciplineTable(
                # id=1, # Remove explicit ID
                id_aup=101,  # From seeded AUP
                id_unique_discipline=1001,  # From seeded SprDiscipline
                study_group_id=test_group.id,
                semester=1
            )
            session.add(discipline_table) # Используем session.add
            session.commit()
            print("  - Discipline table created.")
        else:
            print("  - Discipline table already exists.")

        # Add grade types (GradeType)
        # Используем session.merge
        grade_types_data = [
            {"id": 1, "name": "Посещаемость", "type": "attendance", "binary": True, "discipline_table_id": discipline_table.id},
            {"id": 2, "name": "Активность", "type": "activity", "binary": False, "discipline_table_id": discipline_table.id},
            {"id": 3, "name": "Задания", "type": "tasks", "binary": False, "discipline_table_id": discipline_table.id}
        ]

        for grade_type_data in grade_types_data:
            # Use session.merge for GradeType
            grade_type = session.merge(GradeType(**grade_type_data))
        session.commit()
        print("  - Grade types created.")

        # Add a couple of topics to the discipline table
        # Используем session.merge
        topics_data = [
            {
                "id": 1,
                "discipline_table_id": discipline_table.id,
                "topic": "Введение в предмет",
                "chapter": "Глава 1",
                "id_type_control": 1,  # Lecture (from D_ControlType)
                "task_link": "https://example.com/task1",
                "task_link_name": "Задание 1",
                "study_group_id": test_group.id,
                "spr_place_id": 1,  # Classroom
                "lesson_order": 1
            },
            {
                "id": 2,
                "discipline_table_id": discipline_table.id,
                "topic": "Основные понятия",
                "chapter": "Глава 1",
                "id_type_control": 1,  # Lecture
                "task_link": "https://example.com/task2",