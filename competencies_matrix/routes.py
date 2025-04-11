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
    parse_prof_standard_file
)
from auth.logic import login_required, approved_required
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
    (Версия с улучшенной обработкой ответа)
    """
    data = request.get_json()
    if not data or 'aup_data_id' not in data or 'indicator_id' not in data:
        abort(400, description="Отсутствуют обязательные поля: aup_data_id, indicator_id")

    aup_data_id = data['aup_data_id']
    indicator_id = data['indicator_id']
    is_creating = (request.method == 'POST')

    success = update_matrix_link(
        aup_data_id,
        indicator_id,
        create=is_creating
    )

    if success:
        if is_creating:
            return jsonify({"message": "Связь успешно создана"}), 201
        else:
            return jsonify({"message": "Связь успешно удалена (или не существовала)"}), 200
    else:
        abort(400, description="Не удалось создать/удалить связь: возможно, AupData или Indicator не найдены, или произошла ошибка БД.")

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