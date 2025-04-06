# competencies_matrix/routes.py
from flask import jsonify, request, Response, abort
from . import competencies_matrix_bp
# Импортируем все необходимые функции из logic
from .logic import (
    get_educational_programs_list,
    get_program_details,
    get_matrix_for_aup,
    update_matrix_link,
    create_competency,
    create_indicator, # Добавили импорт
    parse_prof_standard_file
)
# Импортируем декоратор аутентификации
from auth.logic import login_required

# --- Роуты для Образовательных Программ ---
@competencies_matrix_bp.route('/programs', methods=['GET'])
@login_required(request)
def list_programs():
    """
    GET /api/competencies/programs
    Возвращает список образовательных программ.
    """
    try:
        programs = get_educational_programs_list()
        # Используем .to_dict() из моделей (если он там есть и настроен)
        return jsonify([p.to_dict() for p in programs])
    except Exception as e:
        print(f"Error in list_programs: {e}")
        abort(500, description="Ошибка сервера при получении списка программ")

@competencies_matrix_bp.route('/programs/<int:program_id>', methods=['GET'])
@login_required(request)
def get_program(program_id):
    """
    GET /api/competencies/programs/<program_id>
    Возвращает детальную информацию по ОП.
    """
    try:
        program_data = get_program_details(program_id)
        if not program_data:
            abort(404, description="Образовательная программа не найдена")
        return jsonify(program_data)
    except Exception as e:
        print(f"Error in get_program for id {program_id}: {e}")
        abort(500, description="Ошибка сервера при получении деталей программы")

# --- Роуты для Матрицы Компетенций ---
@competencies_matrix_bp.route('/matrix/<int:aup_id>', methods=['GET'])
@login_required(request)
# @check_permission('view_matrix') # TODO: Добавить проверку прав
def get_matrix(aup_id):
    """
    GET /api/competencies/matrix/<aup_id>
    Возвращает данные для построения матрицы для АУП.
    """
    try:
        matrix_data = get_matrix_for_aup(aup_id)
        if matrix_data is None:
             abort(404, description="АУП не найден или нет данных для матрицы")
        # Структура ответа определяется функцией get_matrix_for_aup
        return jsonify(matrix_data)
    except Exception as e:
        print(f"Error in get_matrix for aup_id {aup_id}: {e}")
        abort(500, description="Ошибка сервера при получении данных матрицы")

@competencies_matrix_bp.route('/matrix/link', methods=['POST', 'DELETE'])
@login_required(request)
# @check_permission('edit_matrix') # TODO: Добавить проверку прав
def manage_matrix_link():
    """
    POST /api/competencies/matrix/link - Создает связь Дисциплина(АУП)-ИДК
    DELETE /api/competencies/matrix/link - Удаляет связь Дисциплина(АУП)-ИДК
    Тело запроса (JSON): { "aup_data_id": <int>, "indicator_id": <int> }
    """
    try:
        data = request.get_json()
        if not data or 'aup_data_id' not in data or 'indicator_id' not in data:
            abort(400, description="Необходимы 'aup_data_id' и 'indicator_id' в теле запроса")

        # Проверка типов данных (можно улучшить схемами валидации)
        try:
            aup_data_id = int(data['aup_data_id'])
            indicator_id = int(data['indicator_id'])
        except (ValueError, TypeError):
             abort(400, description="'aup_data_id' и 'indicator_id' должны быть целыми числами")

        is_creating = (request.method == 'POST')
        success = update_matrix_link(aup_data_id, indicator_id, create=is_creating)

        if success:
            # Возвращаем 200 для POST (успешно создано или уже существовало)
            # Возвращаем 204 для DELETE (успешно удалено или уже не существовало)
            status_code = 200 if is_creating else 204
            response_body = {"status": "success"} if is_creating else ''
            return jsonify(response_body) if response_body else ('', status_code)
        else:
            # Если logic вернул False, значит не найдены aup_data_id или indicator_id
            abort(404, description="Не удалось выполнить операцию: AupData или Indicator не найдены")

    except Exception as e:
        print(f"Error in manage_matrix_link: {e}")
        abort(500, description="Ошибка сервера при обновлении связи в матрице")


# --- Роуты для управления Компетенциями ---
@competencies_matrix_bp.route('/competencies', methods=['POST'])
@login_required(request)
# @check_permission('manage_competencies') # TODO: Добавить проверку прав
def add_competency():
    """
    POST /api/competencies/competencies
    Создает новую компетенцию.
    Тело запроса (JSON): { "type_code": "ПК", "code": "ПК-5", "name": "...", ... }
    """
    try:
        data = request.get_json()
        if not data:
            abort(400, description="Тело запроса не может быть пустым")

        # TODO: Валидация данных с использованием schemas.py

        new_competency = create_competency(data) # Вызов функции логики

        if new_competency:
            # Возвращаем созданный объект и статус 201 Created
            return jsonify(new_competency.to_dict()), 201
        else:
            # Если logic вернул None, значит были проблемы с данными (напр., не найден тип)
            abort(400, description="Не удалось создать компетенцию. Проверьте входные данные (тип, код, имя).")
    except Exception as e:
        print(f"Error in add_competency: {e}")
        abort(500, description="Ошибка сервера при создании компетенции")

# --- Роуты для управления Индикаторами ---
@competencies_matrix_bp.route('/indicators', methods=['POST'])
@login_required(request)
# @check_permission('manage_competencies') # TODO: Добавить проверку прав
def add_indicator():
    """
    POST /api/competencies/indicators
    Создает новый индикатор достижения компетенции (ИДК).
    Тело запроса (JSON): { "competency_id": ..., "code": "ИПК-1.1", "formulation": "...", ... }
    """
    try:
        data = request.get_json()
        if not data:
            abort(400, description="Тело запроса не может быть пустым")

        # TODO: Валидация данных с использованием schemas.py

        new_indicator = create_indicator(data) # Вызов функции логики

        if new_indicator:
            # Возвращаем созданный объект и статус 201 Created
            return jsonify(new_indicator.to_dict()), 201
        else:
            # Если logic вернул None, значит были проблемы (напр., не найдена компетенция)
             abort(400, description="Не удалось создать индикатор. Проверьте competency_id и другие данные.")
    except Exception as e:
        print(f"Error in add_indicator: {e}")
        abort(500, description="Ошибка сервера при создании индикатора")

# --- Роут для парсинга ПС ---
@competencies_matrix_bp.route('/prof-standards/parse', methods=['POST'])
@login_required(request)
# @check_permission('manage_prof_standards') # TODO: Добавить проверку прав
def parse_prof_standard():
    """
    POST /api/competencies/prof-standards/parse
    Принимает файл профстандарта (HTML/Markdown), парсит его
    и сохраняет/обновляет основную информацию и текст в БД.
    Ожидает файл в поле 'file'.
    """
    try:
        if 'file' not in request.files:
            abort(400, description="Файл не найден в данных формы (ожидается поле 'file')")

        file = request.files['file']
        if file.filename == '':
            abort(400, description="Имя файла не должно быть пустым")

        # Читаем файл в байтах
        file_bytes = file.read()
        filename = file.filename # Сохраняем оригинальное имя файла

        # Вызываем функцию логики для парсинга и сохранения
        result = parse_prof_standard_file(file_bytes, filename) # Передаем байты

        if result and result.get('success'):
            # Возвращаем результат с ID созданного/обновленного ПС
            return jsonify(result), 201
        else:
            error_message = result.get('error', 'Неизвестная ошибка парсинга') if result else 'Ошибка парсинга'
            abort(400, description=error_message) # 400, т.к. проблема скорее всего в файле

    except Exception as e:
        print(f"Error in parse_prof_standard: {e}")
        abort(500, description=f"Ошибка сервера при обработке файла профстандарта: {e}")


# --- Health Check ---
@competencies_matrix_bp.route('/health-check', methods=['GET'])
def health_check():
    """Проверка доступности модуля."""
    return jsonify({"status": "ok", "module": "competencies_matrix"})

# TODO: Добавить остальные CRUD эндпоинты для:
# - EducationalProgram (POST, PATCH, DELETE)
# - FgosVo (GET list, GET by id, POST, PATCH, DELETE)
# - ProfStandard (GET list, GET by id/code, PATCH, DELETE)
# - Competency (GET list, GET by id/code, PATCH, DELETE)
# - Indicator (GET list by competency, GET by id/code, PATCH, DELETE)
# - Связей (ПС-ОП, ПС-ФГОС, АУП-ОП, ИДК-ПС_элемент)