# competencies_matrix/routes.py
"""
Маршруты (API endpoints) для модуля матрицы компетенций.
Здесь определены все API-точки входа для работы с матрицами компетенций,
образовательными программами, ФГОС, профстандартами и т.д.
"""

from flask import request, jsonify, abort
from . import competencies_matrix_bp
from typing import Optional
from .logic import (
    get_educational_programs_list, get_program_details, 
    get_matrix_for_aup, update_matrix_link,
    create_competency, create_indicator,
    parse_fgos_file, save_fgos_data, get_fgos_list, get_fgos_details, delete_fgos,
    # parse_prof_standard_file, # Added from existing code, was missing in prompt's logic import list
    get_external_aups_list, get_external_aup_disciplines # New imports
)
from auth.logic import login_required, approved_required, admin_only
import logging
# Импортируем db для корректного rollback в except
from maps.models import db

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
    result = [p.to_dict(rules=['-fgos.educational_programs']) for p in programs]
    
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
@competencies_matrix_bp.route('/matrix/num/<string:aup_num>', methods=['GET'])
@login_required
@approved_required
def get_matrix(aup_num):
    """
    Получение данных для матрицы компетенций конкретного АУП по его номеру.
    Использует num_aup для поиска соответствующей локальной записи AupInfo.
    """
    logger.info(f"Received GET request for matrix for AUP num: {aup_num}")
    # Вызываем логику, передавая номер АУП
    matrix_data = get_matrix_for_aup(aup_num)
    
    if not matrix_data:
        # Возвращаем 404, если локальная запись AupInfo по этому num_aup не найдена
        return jsonify({"error": f"АУП с номером {aup_num} не найден в локальной БД или не связан с образовательной программой"}), 404
        
    logger.info(f"Successfully fetched matrix data for AUP num: {aup_num}")
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
        error_msg = "Не удалось выполнить операцию"
        status_code = 400
        
        if result.get('error') == 'aup_data_not_found':
            error_msg = f"Запись AupData (id: {aup_data_id}) не найдена"
            status_code = 404
        elif result.get('error') == 'indicator_not_found':
            error_msg = f"Индикатор (id: {indicator_id}) не найден"
            status_code = 404
        elif result.get('error') == 'database_error':
            error_msg = "Ошибка базы данных при выполнении операции"
            status_code = 500
            
        return jsonify({"status": "error", "message": error_msg}), status_code

# Группа эндпоинтов для работы с компетенциями и индикаторами
@competencies_matrix_bp.route('/competencies', methods=['POST'])
@login_required
@approved_required
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
    
    competency = create_competency(data)
    if not competency:
        return jsonify({"error": "Не удалось создать компетенцию"}), 400
    
    return jsonify(competency.to_dict()), 201

@competencies_matrix_bp.route('/indicators', methods=['POST'])
@login_required
@approved_required
def create_new_indicator():
    """
    Создание нового индикатора достижения компетенции (ИДК).
    Принимает JSON с полями:
    - competency_id: ID родительской компетенции
    - code: Код индикатора (ИУК-1.1, ИОПК-2.3, ИПК-3.2 и т.д.)
    - formulation: Формулировка индикатора
    - source_description: (опционально) Описание источника
    - labor_function_ids: (опционально) Список ID трудовых функций
    """
    data = request.get_json()
    
    # Проверка необходимых полей
    if not data or 'competency_id' not in data or 'code' not in data or 'formulation' not in data:
        return jsonify({"error": "Отсутствуют обязательные поля"}), 400
    
    indicator = create_indicator(data)
    if not indicator:
        return jsonify({"error": "Не удалось создать индикатор"}), 400
    
    return jsonify(indicator.to_dict()), 201

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
        parsed_data = parse_fgos_file(file_bytes, file.filename)

        if not parsed_data:
            return jsonify({"error": "Не удалось распарсить файл ФГОС или извлечь основные данные"}), 400

        # TODO: Добавить в ответ информацию о существующем ФГОС, если найден (для сравнения на фронтенде)
        # Можно вызвать get_fgos_details, если найден ФГОС с такими же ключевыми параметрами
        
        return jsonify(parsed_data), 200 # Возвращаем парсенные данные

    except Exception as e:
        logger.error(f"Error processing FGOS upload for {file.filename}: {e}", exc_info=True)
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

    try:
        # Вызываем функцию сохранения данных
        # Передаем сессию явно
        saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=options.get('force_update', False))

        if saved_fgos is None:
            # Если save_fgos_data вернула None, значит произошла ошибка БД или валидации внутри
            # (логирование ошибки должно быть внутри save_fgos_data)
            return jsonify({"error": "Ошибка при сохранении данных ФГОС в базу данных"}), 500
            
        # Если save_fgos_data вернула объект, который уже существовал и force_update=False,
        # то это не ошибка, просто дубликат. Фронтенд должен был это обработать на шаге preview.
        # Но API все равно должен вернуть информацию.
        # Проверяем, был ли это новый объект или существующий
        is_new = saved_fgos._sa_instance_state.key is None or saved_fgos._sa_instance_state.key.persistent is None

        return jsonify({
            "success": True,
            "fgos_id": saved_fgos.id,
            "message": "Данные ФГОС успешно сохранены." if is_new else "Данные ФГОС успешно обновлены."
        }), 201 # 201 Created или 200 OK, 201 более уместен для создания/обновления


    except Exception as e:
        logger.error(f"Error saving FGOS data from file {filename}: {e}", exc_info=True)
        # Если произошла ошибка, и она не была поймана внутри save_fgos_data с откатом, откатываем здесь
        db.session.rollback()
        return jsonify({"error": f"Неожиданная ошибка сервера при сохранении: {e}"}), 500

@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only # Удаление ФГОС - действие администратора
def delete_fgos_route(fgos_id):
    """Удаление ФГОС ВО по ID"""
    try:
        deleted = delete_fgos(fgos_id, db.session)
        if deleted:
            return jsonify({"success": True, "message": "ФГОС успешно удален"}), 200
        else:
            return jsonify({"success": False, "error": "ФГОС не найден или не удалось удалить"}), 404

    except Exception as e:
        logger.error(f"Error deleting FGOS {fgos_id}: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"success": False, "error": f"Неожиданная ошибка сервера при удалении: {e}"}), 500

# Группа эндпоинтов для работы с профессиональными стандартами (ПС)
@competencies_matrix_bp.route('/profstandards/upload', methods=['POST'])
@login_required
@approved_required
def upload_profstandard():
    """
    Загрузка файла профессионального стандарта (HTML/Markdown).
    Парсит и сохраняет в БД профстандарт и его структуру.
    Принимает multipart/form-data с файлом.
    """
    # from .logic import parse_prof_standard_file as parse_prof_standard_logic_function # This line is redundant
    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден в запросе"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Файл не выбран"}), 400
    
    # Читаем содержимое файла
    file_bytes = file.read()
    result = parse_prof_standard_file(file_bytes, file.filename) # Uses the imported function
    
    if not result or not result.get('success'):
        return jsonify({"error": result.get('error', 'Ошибка при обработке файла')}), 400
    
    return jsonify(result), 201

# --- Новая группа эндпоинтов для работы с внешней БД КД ---

@competencies_matrix_bp.route('/external/aups', methods=['GET'])
@login_required
@approved_required
# @admin_only # Просмотр списка АУП доступен методистам
def get_external_aups():
    """
    Поиск и получение списка АУП из внешней БД КД по заданным параметрам.
    Поддерживает фильтрацию и пагинацию.
    """
    try:
        # Получаем параметры фильтрации и пагинации из запроса
        program_code: Optional[str] = request.args.get('program_code')
        profile_num: Optional[str] = request.args.get('profile_num')
        # ИСПРАВЛЕНИЕ: Меняем имя аргумента на form_education_name, чтобы соответствовать логике
        form_education_name: Optional[str] = request.args.get('form_education') 
        year_beg: Optional[int] = request.args.get('year_beg', type=int)
        # ИСПРАВЛЕНИЕ: Меняем имя аргумента на degree_education_name, чтобы соответствовать логике
        degree_education_name: Optional[str] = request.args.get('degree_education') 
        search_query: Optional[str] = request.args.get('search') # Общий текстовый поиск
        offset: int = request.args.get('offset', default=0, type=int)
        # ИСПРАВЛЕНИЕ: Добавляем проверку на None для limit, если он не был передан в запросе
        limit_param = request.args.get('limit', default=20, type=int) 
        limit: Optional[int] = limit_param if limit_param is not None else 20


        # Вызываем логику для получения данных из внешней БД
        aups_list = get_external_aups_list(
            program_code=program_code,
            profile_num=profile_num,
            form_education_name=form_education_name, # ИСПРАВЛЕНИЕ: Передаем правильное имя
            year_beg=year_beg,
            degree_education_name=degree_education_name, # ИСПРАВЛЕНИЕ: Передаем правильное имя
            search_query=search_query,
            offset=offset,
            limit=limit
        )

        return jsonify(aups_list), 200

    except Exception as e:
        # Логирование и откат при ошибке
        logger.error(f"Error in /aups: {e}", exc_info=True)
        # db.session.rollback() # Откат уже в get_external_aups_list при ошибке
        return jsonify({"error": f"Ошибка сервера при получении списка АУП из внешней БД: {e}"}), 500

@competencies_matrix_bp.route('/external/aups/<int:aup_id>/disciplines', methods=['GET'])
@login_required
@approved_required
# @admin_only # Просмотр доступен методистам
def get_external_aup_disciplines_route(aup_id):
    """
    Получение списка дисциплин (AupData записей) для конкретного АУП из внешней БД КД.
    Возвращает сырые записи AupData.
    """
    try:
        # Вызываем логику для получения данных из внешней БД
        disciplines_list = get_external_aup_disciplines(aup_id)

        return jsonify(disciplines_list), 200

    except Exception as e:
        logger.error(f"Error in /aups/{aup_id}/disciplines: {e}", exc_info=True)
        # db.session.rollback() # Откат уже в get_external_aup_disciplines при ошибке
        return jsonify({"error": f"Ошибка сервера при получении списка дисциплин из внешней БД: {e}"}), 500

# TODO: Возможно, добавить API для получения опций фильтров (списки кодов ОП, профилей, форм, годов из внешней БД КД)
# GET /api/competencies/external/filters/programs
# GET /api/competencies/external/filters/forms
# GET /api/competencies/external/filters/years etc.

# Дальнейшие эндпоинты можно добавить по мере необходимости:
# - CRUD для образовательных программ
# - Управление связями ОП-АУП и ОП-ПС
# - API для NLP-модуля
# - Генерация отчетов
# - и т.д.