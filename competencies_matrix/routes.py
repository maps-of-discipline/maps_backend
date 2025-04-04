# competencies_matrix/routes.py
from flask import jsonify, request, Response, abort
from . import competencies_matrix_bp  # Импортируем Blueprint из __init__.py
from .logic import (  # Импортируем функции бизнес-логики
    get_educational_programs_list,
    get_program_details,
    get_matrix_for_aup,
    update_matrix_link,
    create_competency,
    parse_prof_standard_file  # Функция для парсинга
)
# Импортируем db и модели из основного приложения и нашего модуля
from maps.models import db, AupData, SprDiscipline
from .models import EducationalProgram, Competency, Indicator, CompetencyMatrix

# Импортируем декоратор аутентификации (адаптируем под существующую систему)
from auth.logic import login_required

# --- Роуты для Образовательных Программ ---
@competencies_matrix_bp.route('/programs', methods=['GET'])
@login_required(request)  # Пример защиты роута
def list_programs():
    """
    GET /api/competencies/programs
    Возвращает список образовательных программ.
    """
    try:
        programs = get_educational_programs_list()
        return jsonify([p.to_dict() for p in programs])
    except Exception as e:
        abort(500, description=f"Ошибка при получении списка ОП: {str(e)}")


@competencies_matrix_bp.route('/programs/<int:program_id>', methods=['GET'])
@login_required(request)
def get_program(program_id):
    """
    GET /api/competencies/programs/<program_id>
    Возвращает детальную информацию по образовательной программе,
    включая связанный ФГОС, список выбранных и рекомендованных ПС, список АУП.
    """
    try:
        program_data = get_program_details(program_id)
        if not program_data:
            abort(404, description="Образовательная программа не найдена")
        return jsonify(program_data)
    except Exception as e:
        abort(500, description=f"Ошибка при получении данных ОП: {str(e)}")


# --- Роуты для Матрицы Компетенций ---
@competencies_matrix_bp.route('/matrix/<int:aup_id>', methods=['GET'])
@login_required(request)
def get_matrix(aup_id):
    """
    GET /api/competencies/matrix/<aup_id>
    Возвращает данные для построения матрицы компетенций для конкретного АУП.
    Включает список дисциплин, список ИДК и существующие связи.
    Опционально: может включать предложения от NLP.
    """
    try:
        matrix_data = get_matrix_for_aup(aup_id)
        if matrix_data is None:
            abort(404, description="АУП не найден или нет данных для матрицы")
        return jsonify(matrix_data)
    except Exception as e:
        abort(500, description=f"Ошибка при получении матрицы: {str(e)}")


@competencies_matrix_bp.route('/matrix/link', methods=['POST', 'DELETE'])
@login_required(request)
def manage_matrix_link():
    """
    POST /api/competencies/matrix/link - Создает связь Дисциплина(АУП)-ИДК
    DELETE /api/competencies/matrix/link - Удаляет связь Дисциплина(АУП)-ИДК
    Тело запроса (JSON): { "aup_data_id": ..., "indicator_id": ... }
    """
    try:
        data = request.get_json()
        if not data or 'aup_data_id' not in data or 'indicator_id' not in data:
            abort(400, description="Необходимы aup_data_id и indicator_id")

        aup_data_id = data['aup_data_id']
        indicator_id = data['indicator_id']

        success = update_matrix_link(
            aup_data_id,
            indicator_id,
            create=(request.method == 'POST')  # True для POST, False для DELETE
        )

        if success:
            return jsonify({"status": "success"}), 200 if request.method == 'POST' else 204
        else:
            abort(404, description="Не удалось создать/удалить связь: AUP data entry или Indicator не найден")
    except Exception as e:
        abort(500, description=f"Ошибка при управлении связью: {str(e)}")


# --- Роуты для управления Компетенциями/ИДК ---
@competencies_matrix_bp.route('/competencies', methods=['POST'])
@login_required(request)
def add_competency():
    """
    POST /api/competencies/competencies
    Создает новую компетенцию (вероятно, ПК на основе ТФ).
    Тело запроса (JSON): { "type_code": "ПК", "code": "ПК-5", "name": "...", "based_on_tf_id": ... }
    """
    try:
        data = request.get_json()
        if not data or 'type_code' not in data or 'code' not in data or 'name' not in data:
            abort(400, description="Необходимы type_code, code, name")

        new_competency = create_competency(data)

        if new_competency:
            return jsonify(new_competency.to_dict()), 201
        else:
            abort(400, description="Не удалось создать компетенцию. Проверьте данные.")
    except Exception as e:
        abort(500, description=f"Ошибка при создании компетенции: {str(e)}")


# --- Роут для парсинга ПС ---
@competencies_matrix_bp.route('/prof-standards/parse', methods=['POST'])
@login_required(request)
def parse_prof_standard():
    """
    POST /api/competencies/prof-standards/parse
    Загрузка и парсинг файла профстандарта.
    """
    try:
        if 'file' not in request.files:
            abort(400, description="Нет файла в запросе")
        
        file = request.files['file']
        if file.filename == '':
            abort(400, description="Не выбран файл")
        
        # Читаем файл и вызываем парсер
        file_data = file.read()
        filename = file.filename
        
        parsed_data = parse_prof_standard_file(file_data, filename)
        
        if parsed_data:
            return jsonify(parsed_data), 201
        else:
            abort(400, description="Не удалось распарсить файл профстандарта")
    except Exception as e:
        abort(500, description=f"Ошибка при парсинге профстандарта: {str(e)}")


# Заглушка для проверки работоспособности API
@competencies_matrix_bp.route('/health-check', methods=['GET'])
def health_check():
    """
    GET /api/competencies/health-check
    Проверка работоспособности API модуля competencies_matrix.
    """
    return jsonify({
        "status": "ok",
        "module": "competencies_matrix",
        "timestamp": db.func.now()
    })