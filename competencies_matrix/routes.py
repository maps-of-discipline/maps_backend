# competencies_matrix/routes.py
"""
Маршруты (API endpoints) для модуля матрицы компетенций.
"""

from flask import request, jsonify, abort
from . import competencies_matrix_bp
from typing import Optional
from .logic import (
    get_educational_programs_list, get_program_details,
    get_matrix_for_aup, update_matrix_link, # update_matrix_link теперь возвращает статус
    create_competency, create_indicator,
    parse_fgos_file, save_fgos_data, get_fgos_list, get_fgos_details, delete_fgos,
    # parse_prof_standard_file as logic_parse_ps_file, # Переименовано в parse_prof_standard_file
    parse_prof_standard_file, # Импортируем оркестратор парсинга из logic.py
    get_external_aups_list, get_external_aup_disciplines # New imports
)
# Импортируем save_prof_standard_data из logic
from .logic import save_prof_standard_data # <-- Добавлен импорт

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
    programs = get_educational_programs_list()

    # Сериализуем результат в список словарей
    # Убедитесь, что to_dict доступен и настроен на модели EducationalProgram
    # и что он не вызывает рекурсию через relationships при сериализации
    result = [p.to_dict() for p in programs] # Убрал rule, т.к. to_dict должен быть безопасным

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

    # update_matrix_link теперь возвращает словарь со статусом и сообщением
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
                # DELETE должен вернуть 404 если не найдено
                return jsonify({"status": "not_found", "message": "Связь для удаления не найдена"}), 404
    else:  # Обработка ошибок, когда success=False
        # update_matrix_link уже возвращает details об ошибке
        error_msg = result.get('message', "Не удалось выполнить операцию")
        status_code = 400 # Дефолтный код ошибки

        # Если в результате есть конкретный тип ошибки, используем его для кода
        if result.get('error_type') == 'indicator_not_found':
            status_code = 404
        elif result.get('error_type') == 'aup_data_not_found': # Этот тип ошибки больше не генерируется в logic.py
             status_code = 404
        elif result.get('error_type') == 'database_error':
            status_code = 500
        # Добавьте другие типы ошибок, если они появятся в update_matrix_link

        # Логируем полную ошибку, включая детали
        logger.error(f"Error processing matrix link request: {result.get('message')}. Details: {result.get('details')}")

        # Возвращаем только безопасные для фронтенда сообщения
        return jsonify({"status": "error", "message": error_msg}), status_code


# Группа эндпоинтов для работы с компетенциями и индикаторами
@competencies_matrix_bp.route('/competencies', methods=['POST'])
@login_required
@approved_required
def create_new_competency():
    """
    Создание новой компетенции (обычно ПК на основе профстандарта).
    """
    data = request.get_json()

    # Проверка необходимых полей
    if not data or 'type_code' not in data or 'code' not in data or 'name' not in data:
        abort(400, description="Отсутствуют обязательные поля: type_code, code, name")

    # create_competency возвращает объект или None
    competency = create_competency(data)
    if not competency:
        # Логирование ошибки уже внутри create_competency
        return jsonify({"error": "Не удалось создать компетенцию. Возможно, уже существует или не найден тип."}), 400

    # Убедитесь, что to_dict доступен и настроен
    return jsonify(competency.to_dict()), 201

@competencies_matrix_bp.route('/indicators', methods=['POST'])
@login_required
@approved_required
def create_new_indicator():
    """
    Создание нового индикатора достижения компетенции (ИДК).
    """
    data = request.get_json()

    # Проверка необходимых полей
    if not data or 'competency_id' not in data or 'code' not in data or 'formulation' not in data:
        abort(400, description="Отсутствуют обязательные поля: competency_id, code, formulation")

    # create_indicator возвращает объект или None
    indicator = create_indicator(data)
    if not indicator:
        # Логирование ошибки уже внутри create_indicator
        return jsonify({"error": "Не удалось создать индикатор. Возможно, уже существует или не найдена компетенция."}), 400

    # Убедитесь, что to_dict доступен и настроен
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
    # Исключаем Relationships, если они не нужны в списке
    result = [f.to_dict(rules=['-competencies', '-recommended_ps_assoc', '-educational_programs']) for f in fgos_list]
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

    # Проверка расширения файла на .pdf
    if not file.filename.lower().endswith('.pdf'):
         return jsonify({"error": "Поддерживаются только файлы формата PDF"}), 400

    try:
        file_bytes = file.read()
        parsed_data = parse_fgos_file(file_bytes, file.filename)

        if not parsed_data or not parsed_data.get('metadata'):
            # parse_fgos_file выбрасывает ValueError при критичных ошибках парсинга
            # Если вернулось без ошибки, но данных мало - считаем невалидным
            return jsonify({"error": "Не удалось извлечь основные метаданные из файла ФГОС"}), 400

        # Возвращаем парсенные данные, включая метаданные, УК/ОПК (без индикаторов) и рекомендованные ПС
        # Frontend будет использовать эти данные для отображения предпросмотра
        return jsonify(parsed_data), 200

    except ValueError as e: # Ловим ошибки парсинга, выброшенные parse_fgos_file
        logger.error(f"FGOS Parsing Error for {file.filename}: {e}")
        return jsonify({"error": f"Ошибка парсинга файла: {e}"}), 400
    except Exception as e:
        logger.error(f"Unexpected error processing FGOS upload for {file.filename}: {e}", exc_info=True)
        return jsonify({"error": f"Неожиданная ошибка сервера при обработке файла: {e}"}), 500


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
        # save_fgos_data управляет своей транзакцией (savepoint), но коммит/роллбек при ошибке БД внутри
        saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=options.get('force_update', False))

        if saved_fgos is None:
            # Если save_fgos_data вернула None, значит произошла ошибка БД или валидации внутри
            # (логирование ошибки уже внутри save_fgos_data)
            return jsonify({"error": "Ошибка при сохранении данных ФГОС в базу данных"}), 500

        # save_fgos_data возвращает объект FgosVo, который был сохранен или обновлен
        # Frontend может проверить existence_fgos_record на этапе предпросмотра
        # Здесь просто подтверждаем успех
        return jsonify({
            "success": True,
            "fgos_id": saved_fgos.id,
            "message": "Данные ФГОС успешно сохранены."
        }), 201 # 201 Created или 200 OK, 201 более уместен для создания/обновления


    except Exception as e:
        logger.error(f"Error saving FGOS data from file {filename}: {e}", exc_info=True)
        # Если произошла ошибка, которая не была поймана внутри save_fgos_data
        # db.session.rollback() # Откат должен быть внутри save_fgos_data при ошибке БД
        return jsonify({"error": f"Неожиданная ошибка сервера при сохранении: {e}"}), 500

@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only # Удаление ФГОС - действие администратора
def delete_fgos_route(fgos_id):
    """Удаление ФГОС ВО по ID"""
    try:
        # delete_fgos управляет своей транзакцией (commit/rollback)
        deleted = delete_fgos(fgos_id, db.session)
        if deleted:
            return jsonify({"success": True, "message": "ФГОС успешно удален"}), 200
        else:
            # delete_fgos вернет False если не найдет или не сможет удалить
            return jsonify({"success": False, "error": "ФГОС не найден или не удалось удалить"}), 404

    except Exception as e:
        logger.error(f"Error deleting FGOS {fgos_id}: {e}", exc_info=True)
        # db.session.rollback() # Откат должен быть внутри delete_fgos при ошибке БД
        return jsonify({"success": False, "error": f"Неожиданная ошибка сервера при удалении: {e}"}), 500

# Группа эндпоинтов для работы с профессиональными стандартами (ПС)
@competencies_matrix_bp.route('/profstandards/upload', methods=['POST'])
@login_required
@approved_required
@admin_only # Загрузка ПС - действие администратора
def upload_profstandard():
    """
    Загрузка файла профессионального стандарта (HTML/Markdown/PDF).
    Парсит, извлекает структуру и сохраняет в БД профстандарт и его структуру.
    Принимает multipart/form-data с файлом.
    """
    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден в запросе"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Файл не выбран"}), 400

    # TODO: Добавить проверку расширения файла (HTML, DOCX, PDF?)

    try:
        # Читаем содержимое файла
        file_bytes = file.read()
        # Вызываем логику парсинга и сохранения
        # parse_prof_standard_file теперь оркестрирует парсинг и сохранение
        result = parse_prof_standard_file(file_bytes, file.filename)

        if not result.get('success'):
            # Логирование ошибки уже внутри parse_prof_standard_file
            status_code = 400 # Дефолтный код ошибки
            if result.get('error_type') == 'parsing_error': status_code = 400
            elif result.get('error_type') == 'database_error': status_code = 500
            elif result.get('error_type') == 'integrity_error': status_code = 409 # Conflict
            elif result.get('error_type') == 'already_exists': status_code = 409 # Conflict

            return jsonify({"status": "error", "message": result.get('error', 'Ошибка обработки файла')}), status_code

        # Если успех
        saved_prof_standard = result.get('prof_standard')
        if saved_prof_standard:
             return jsonify({
                 "status": "success",
                 "message": "Профессиональный стандарт успешно загружен и обработан.",
                 "prof_standard_id": saved_prof_standard.id,
                 "code": saved_prof_standard.code,
                 "name": saved_prof_standard.name
             }), 201 # 201 Created


    except Exception as e:
        logger.error(f"Unexpected error in /profstandards/upload for {file.filename}: {e}", exc_info=True)
        # db.session.rollback() # Оркестратор должен откатывать при ошибке БД
        return jsonify({"status": "error", "message": f"Неожиданная ошибка сервера при обработке файла: {e}"}), 500


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
        profile_num: Optional[str] = request.args.get('profile_num') # <-- Читаем profile_num
        profile_name: Optional[str] = request.args.get('profile_name') # <-- Читаем profile_name
        form_education_name: Optional[str] = request.args.get('form_education')
        year_beg: Optional[int] = request.args.get('year_beg', type=int)
        degree_education_name: Optional[str] = request.args.get('degree_education')
        search_query: Optional[str] = request.args.get('search') # Общий текстовый поиск
        offset: int = request.args.get('offset', default=0, type=int)
        limit_param = request.args.get('limit', default=20, type=int)
        limit: Optional[int] = limit_param if limit_param is not None and limit_param > 0 else 20 # Убедимся, что лимит > 0

        # Вызываем логику для получения данных из внешней БД, передавая ОБА параметра профиля
        aups_list = get_external_aups_list(
            program_code=program_code,
            profile_num=profile_num, # <-- Передаем profile_num
            profile_name=profile_name, # <-- Передаем profile_name
            form_education_name=form_education_name,
            year_beg=year_beg,
            degree_education_name=degree_education_name,
            search_query=search_query,
            offset=offset,
            limit=limit
        )

        return jsonify(aups_list), 200

    except Exception as e:
        # Логирование и откат при ошибке
        logger.error(f"Error in /aups: {e}", exc_info=True)
        # При обращении к внешней БД нет необходимости в rollback
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
        # get_external_aup_disciplines теперь ожидает External AUP ID (integer)
        disciplines_list = get_external_aup_disciplines(aup_id)

        for d in disciplines_list:
            if d.get('amount') is not None:
                 d['amount'] = d['amount'] / 100

        return jsonify(disciplines_list), 200

    except Exception as e:
        logger.error(f"Error in /aups/{aup_id}/disciplines: {e}", exc_info=True)
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