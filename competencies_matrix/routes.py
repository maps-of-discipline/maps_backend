# competencies_matrix/routes.py
"""
Маршруты (API endpoints) для модуля матрицы компетенций.
Здесь определены все API-точки входа для работы с матрицами компетенций,
образовательными программами, ФГОС, профстандартами и т.д.
"""

from flask import request, jsonify, abort
from . import competencies_matrix_bp
from .logic import (
    get_educational_programs_list, get_program_details, 
    get_matrix_for_aup, update_matrix_link,
    create_competency, create_indicator,
    parse_prof_standard_file,
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
    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден в запросе"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Файл не выбран"}), 400
    
    # Читаем содержимое файла
    file_bytes = file.read()
    result = parse_prof_standard_file(file_bytes, file.filename)
    
    if not result or not result.get('success'):
        return jsonify({"error": result.get('error', 'Ошибка при обработке файла')}), 400
    
    return jsonify(result), 201

# Дальнейшие эндпоинты можно добавить по мере необходимости:
# - CRUD для образовательных программ
# - Управление связями ОП-АУП и ОП-ПС
# - API для NLP-модуля
# - Генерация отчетов
# - и т.д.