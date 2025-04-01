# competencies_matrix/routes.py
from flask import jsonify, request, Response, abort
from . import competencies_matrix_bp # Импортируем Blueprint из __init__.py
from .logic import ( # Импортируем функции бизнес-логики
    get_educational_programs_list,
    get_program_details,
    get_matrix_for_aup,
    update_matrix_link,
    create_competency,
    # ... другие функции ...
    parse_prof_standard_file # Функция для парсинга
)
# Важно: импортируем db и модели из основного приложения или общего места
from maps.models import db, AupData, SprDiscipline, TblAup # Предполагаем, что они доступны
# Импортируем модели нашего модуля
from .models import EducationalProgram, Competency, Indicator, CompetencyMatrix

# Защита роутов (пример, может быть реализовано через декораторы в logic.py или middleware)
from auth.logic import login_required, check_permission # Импортируем из модуля auth

# --- Роуты для Образовательных Программ ---
@competencies_matrix_bp.route('/programs', methods=['GET'])
@login_required(request) # Пример защиты роута
def list_programs():
    """
    GET /api/competencies/programs
    Возвращает список образовательных программ.
    """
    programs = get_educational_programs_list()
    return jsonify([p.to_dict() for p in programs])

@competencies_matrix_bp.route('/programs/<int:program_id>', methods=['GET'])
@login_required(request)
def get_program(program_id):
    """
    GET /api/competencies/programs/<program_id>
    Возвращает детальную информацию по образовательной программе,
    включая связанный ФГОС, список выбранных и рекомендованных ПС, список АУП.
    """
    program_data = get_program_details(program_id)
    if not program_data:
        abort(404, description="Образовательная программа не найдена")
    # Сериализация может быть сложной из-за вложенности,
    # лучше использовать схемы или настроить serialize_rules в моделях
    return jsonify(program_data) # Функция get_program_details должна вернуть dict


# --- Роуты для Матрицы Компетенций ---
@competencies_matrix_bp.route('/matrix/<int:aup_id>', methods=['GET'])
@login_required(request)
# @check_permission('view_matrix') # Пример проверки прав
def get_matrix(aup_id):
    """
    GET /api/competencies/matrix/<aup_id>
    Возвращает данные для построения матрицы компетенций для конкретного АУП.
    Включает список дисциплин, список ИДК и существующие связи.
    Опционально: может включать предложения от NLP.
    """
    # Здесь должна быть логика получения данных из logic.py
    matrix_data = get_matrix_for_aup(aup_id)
    if matrix_data is None:
         abort(404, description="АУП не найден или нет данных для матрицы")

    # Пример структуры ответа:
    # {
    #   "aup_info": { "id": aup_id, "num_aup": "...", ... },
    #   "disciplines": [ { "id": ..., "title": "...", "semester": ..., "aup_data_id": ... }, ...],
    #   "competencies": [
    #     { "id": ..., "code": "УК-1", "name": "...", "type": "УК",
    #       "indicators": [ { "id": ..., "code": "ИУК-1.1", "formulation": "...", "source": "..." }, ...]
    #     }, ...
    #   ],
    #   "links": [ { "aup_data_id": ..., "indicator_id": ... }, ... ],
    #   "suggestions": [ { "aup_data_id": ..., "indicator_id": ..., "score": 0.85 }, ... ] // Опционально
    # }
    return jsonify(matrix_data)


@competencies_matrix_bp.route('/matrix/link', methods=['POST', 'DELETE'])
@login_required(request)
# @check_permission('edit_matrix')
def manage_matrix_link():
    """
    POST /api/competencies/matrix/link - Создает связь Дисциплина(АУП)-ИДК
    DELETE /api/competencies/matrix/link - Удаляет связь Дисциплина(АУП)-ИДК
    Тело запроса (JSON): { "aup_data_id": ..., "indicator_id": ... }
    """
    data = request.get_json()
    if not data or 'aup_data_id' not in data or 'indicator_id' not in data:
        abort(400, description="Необходимы aup_data_id и indicator_id")

    aup_data_id = data['aup_data_id']
    indicator_id = data['indicator_id']

    success = update_matrix_link(
        aup_data_id,
        indicator_id,
        create=(request.method == 'POST') # True для POST, False для DELETE
    )

    if success:
        return jsonify({"status": "success"}), 200 if request.method == 'POST' else 204
    else:
        # Логика должна вернуть причину неудачи (например, 404 если не найдены ID)
        abort(404, description="Не удалось создать/удалить связь: AUP data entry или Indicator не найден")


# --- Роуты для управления Компетенциями/ИДК (Пример) ---
@competencies_matrix_bp.route('/competencies', methods=['POST'])
@login_required(request)
# @check_permission('manage_competencies')
def add_competency():
    """
    POST /api/competencies/competencies
    Создает новую компетенцию (вероятно, ПК на основе ТФ).
    Тело запроса (JSON): { "type_code": "ПК", "code": "ПК-5", "name": "...", "based_on_tf_id": ... }
    """
    data = request.get_json()
    # TODO: Валидация входных данных (использовать schemas.py)
    if not data or 'type_code' not in data or 'code' not in data or 'name' not in data:
         abort(400, description="Необходимы type_code, code, name")

    new_competency = create_competency(data) # Функция логики

    if new_competency:
        return jsonify(new_competency.to_dict()), 201
    else:
         abort(500, description="Не удалось создать компетенцию") # Или 400/404 если были проблемы с данными

# --- Роут для парсинга ПС (Пример) ---
@competencies_matrix_bp.route('/prof-standards/parse', methods=['POST'])
@login_required(request)
# @check_permission('manage_prof_standards')
def parse_prof_standard():
    """
    POST /api/competencies/prof-standards/parse
    Принимает файл HTML профстандарта, парсит его и сохраняет в БД.
    Ожидает файл в `request.files['file']`.
    """
    if 'file' not in request.files:
        abort(400, description="Файл не найден в запросе")

    file = request.files['file']
    if file.filename == '':
        abort(400, description="Имя файла не должно быть пустым")

    if file: # Добавить проверку расширения, если нужно
        try:
            # Важно: Не сохраняем файл напрямую, читаем в память или временный файл
            html_content = file.read() # Читаем байты
            # Передаем контент и кодировку (если известна) в парсер
            # Функция parse_prof_standard_file должна содержать логику вызова
            # html_to_markdown_parser_enhanced и сохранения в БД
            result = parse_prof_standard_file(html_content)

            if result.get("success"):
                return jsonify({
                    "message": "Профстандарт успешно разобран и сохранен",
                    "prof_standard_id": result.get("prof_standard_id"),
                    "markdown_preview": result.get("markdown", "")[:500] + "..." # Превью
                }), 201
            else:
                abort(500, description=f"Ошибка парсинга: {result.get('error', 'Неизвестная ошибка')}")
        except Exception as e:
            abort(500, description=f"Внутренняя ошибка сервера при обработке файла: {str(e)}")

    abort(400, description="Некорректный файл")


# ... Другие роуты для CRUD операций с ИДК, ПС, ТФ и т.д. ...