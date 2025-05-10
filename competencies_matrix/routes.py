# competencies_matrix/routes.py
"""
Маршруты (API endpoints) для модуля матрицы компетенций.
"""

from flask import request, jsonify, abort
from . import competencies_matrix_bp
from typing import Optional
from .logic import (
    get_educational_programs_list, get_program_details,
    get_matrix_for_aup, update_matrix_link,
    create_competency, create_indicator,
    parse_fgos_file, save_fgos_data, get_fgos_list, get_fgos_details, delete_fgos,
    parse_prof_standard_file,
    get_external_aups_list, get_external_aup_disciplines
)
from .logic import save_prof_standard_data

from auth.logic import login_required, approved_required, admin_only
import logging
from maps.models import db

logger = logging.getLogger(__name__)

# Группа эндпоинтов для работы с образовательными программами (ОП)
@competencies_matrix_bp.route('/programs', methods=['GET'])
@login_required
@approved_required
def get_programs():
    """Получение списка всех образовательных программ"""
    programs = get_educational_programs_list()
    result = [p.to_dict(rules=['-aup_assoc', '-selected_ps_assoc', '-fgos']) for p in programs]
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
# ИЗМЕНЕНИЕ: Маршрут теперь принимает aup_num как строку
@competencies_matrix_bp.route('/matrix/<string:aup_num>', methods=['GET']) # <--- ИЗМЕНЕНО с int:aup_id на string:aup_num
@login_required
@approved_required
def get_matrix(aup_num: str): # <--- ИЗМЕНЕНО имя параметра и тип
    """
    Получение данных для матрицы компетенций конкретного АУП по его номеру.
    Использует num_aup для поиска соответствующей локальной записи AupInfo.
    """
    logger.info(f"Received GET request for matrix for AUP num: {aup_num}")
    matrix_data = get_matrix_for_aup(aup_num) # Передаем num_aup в логику

    if not matrix_data:
        logger.warning(f"Matrix data not found for AUP num: {aup_num}. This could mean local AupInfo, EP, or FGOS is missing/not linked.")
        return jsonify({"error": f"Данные матрицы для АУП с номером {aup_num} не найдены (проверьте наличие АУП, его связь с ОП и ФГОС в локальной БД)"}), 404

    logger.info(f"Successfully fetched matrix data for AUP num: {aup_num}")
    return jsonify(matrix_data)

@competencies_matrix_bp.route('/matrix/link', methods=['POST', 'DELETE'])
@login_required
@approved_required
def manage_matrix_link():
    """
    Создает или удаляет связь Дисциплина(АУП)-ИДК в матрице.
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

    if result['success']:
        if is_creating:
            status_code = 201 if result['status'] == 'created' else 200
            return jsonify({"status": result['status'], "message": result.get('message', "Операция выполнена")}), status_code
        else: # DELETE
            status_code = 200 if result['status'] == 'deleted' else 404
            return jsonify({"status": result['status'], "message": result.get('message', "Операция выполнена")}), status_code
    else:
        error_msg = result.get('message', "Не удалось выполнить операцию")
        status_code = 400
        if result.get('error_type') == 'indicator_not_found': status_code = 404
        elif result.get('error_type') == 'database_error': status_code = 500
        logger.error(f"Error processing matrix link request: {result.get('message')}. Details: {result.get('details')}")
        return jsonify({"status": "error", "message": error_msg}), status_code


@competencies_matrix_bp.route('/competencies', methods=['POST'])
@login_required
@approved_required
def create_new_competency():
    data = request.get_json()
    if not data or 'type_code' not in data or 'code' not in data or 'name' not in data:
        abort(400, description="Отсутствуют обязательные поля: type_code, code, name")
    competency = create_competency(data)
    if not competency:
        return jsonify({"error": "Не удалось создать компетенцию. Возможно, уже существует или не найден тип."}), 400
    return jsonify(competency.to_dict(rules=['-indicators'])), 201

@competencies_matrix_bp.route('/indicators', methods=['POST'])
@login_required
@approved_required
def create_new_indicator():
    data = request.get_json()
    if not data or 'competency_id' not in data or 'code' not in data or 'formulation' not in data:
        abort(400, description="Отсутствуют обязательные поля: competency_id, code, formulation")
    indicator = create_indicator(data)
    if not indicator:
        return jsonify({"error": "Не удалось создать индикатор. Возможно, уже существует или не найдена компетенция."}), 400
    return jsonify(indicator.to_dict(rules=['-competency'])), 201

# --- Эндпоинты для ФГОС ВО ---
@competencies_matrix_bp.route('/fgos', methods=['GET'])
@login_required
@approved_required
def get_all_fgos():
    fgos_list = get_fgos_list()
    result = [f.to_dict(rules=['-competencies', '-recommended_ps_assoc', '-educational_programs']) for f in fgos_list]
    return jsonify(result)

@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['GET'])
@login_required
@approved_required
def get_fgos_details_route(fgos_id):
    details = get_fgos_details(fgos_id)
    if not details:
        return jsonify({"error": "ФГОС ВО не найден"}), 404
    return jsonify(details)

@competencies_matrix_bp.route('/fgos/upload', methods=['POST'])
@login_required
@approved_required
@admin_only
def upload_fgos():
    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден в запросе"}), 400
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Файл не выбран или неверный формат (требуется PDF)"}), 400
    try:
        file_bytes = file.read()
        parsed_data = parse_fgos_file(file_bytes, file.filename)
        if not parsed_data or not parsed_data.get('metadata'):
            return jsonify({"error": "Не удалось извлечь основные метаданные из файла ФГОС"}), 400
        return jsonify(parsed_data), 200
    except ValueError as e:
        logger.error(f"FGOS Parsing Error for {file.filename}: {e}")
        return jsonify({"error": f"Ошибка парсинга файла: {e}"}), 400
    except Exception as e:
        logger.error(f"Unexpected error processing FGOS upload for {file.filename}: {e}", exc_info=True)
        return jsonify({"error": f"Неожиданная ошибка сервера при обработке файла: {e}"}), 500

@competencies_matrix_bp.route('/fgos/save', methods=['POST'])
@login_required
@approved_required
@admin_only
def save_fgos():
    data = request.get_json()
    parsed_data = data.get('parsed_data')
    filename = data.get('filename')
    options = data.get('options', {})
    if not parsed_data or not filename:
        return jsonify({"error": "Некорректные данные для сохранения"}), 400
    try:
        saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=options.get('force_update', False))
        if saved_fgos is None:
            return jsonify({"error": "Ошибка при сохранении данных ФГОС в базу данных"}), 500
        return jsonify({"success": True, "fgos_id": saved_fgos.id, "message": "Данные ФГОС успешно сохранены."}), 201
    except Exception as e:
        logger.error(f"Error saving FGOS data from file {filename}: {e}", exc_info=True)
        return jsonify({"error": f"Неожиданная ошибка сервера при сохранении: {e}"}), 500

@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_fgos_route(fgos_id):
    try:
        deleted = delete_fgos(fgos_id, db.session)
        if deleted:
            return jsonify({"success": True, "message": "ФГОС успешно удален"}), 200
        else:
            return jsonify({"success": False, "error": "ФГОС не найден или не удалось удалить"}), 404
    except Exception as e:
        logger.error(f"Error deleting FGOS {fgos_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"Неожиданная ошибка сервера при удалении: {e}"}), 500

# --- Эндпоинты для Профессиональных Стандартов ---
@competencies_matrix_bp.route('/profstandards/upload', methods=['POST'])
@login_required
@approved_required
@admin_only
def upload_profstandard():
    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден в запросе"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Файл не выбран"}), 400
    try:
        file_bytes = file.read()
        # parse_prof_standard_file теперь возвращает словарь с ключом 'parsed_data' или 'error'
        result = parse_prof_standard_file(file_bytes, file.filename) # Эта функция теперь вызывает парсер
        
        if not result.get('success'):
            status_code = 400 # Дефолтный код ошибки
            if result.get('error_type') == 'parsing_error': status_code = 400
            elif result.get('error_type') == 'database_error': status_code = 500
            elif result.get('error_type') == 'integrity_error': status_code = 409 # Conflict
            elif result.get('error_type') == 'already_exists': status_code = 409 # Conflict

            return jsonify({"status": "error", "message": result.get('error', 'Ошибка обработки файла ПС')}), status_code
        parsed_data_for_save = result.get('parsed_data')
        if parsed_data_for_save:
            # Предполагаем, что force_update пока всегда false для CLI, или передаем из запроса
            saved_ps = save_prof_standard_data(parsed_data_for_save, file.filename, db.session, force_update=False)
            if saved_ps:
                return jsonify({
                    "status": "success",
                    "message": "Профессиональный стандарт успешно загружен и сохранен.",
                    "prof_standard_id": saved_ps.id,
                    "code": saved_ps.code,
                    "name": saved_ps.name
                }), 201
            else:
                # Ошибка сохранения, логирование внутри save_prof_standard_data
                return jsonify({"status": "error", "message": "Ошибка при сохранении данных профессионального стандарта."}), 500
        else:
            # Этого не должно произойти, если result['success'] == True
             return jsonify({"status": "error", "message": "Парсинг успешен, но нет данных для сохранения."}), 500


    except Exception as e:
        logger.error(f"Unexpected error in /profstandards/upload for {file.filename}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Неожиданная ошибка сервера при обработке файла: {e}"}), 500


# --- Новая группа эндпоинтов для работы с внешней БД КД ---

# --- Эндпоинты для работы с внешней БД КД ---
@competencies_matrix_bp.route('/external/aups', methods=['GET'])
@login_required
@approved_required
def get_external_aups():
    try:
        program_code: Optional[str] = request.args.get('program_code')
        # ИЗМЕНЕНИЕ: Теперь используем profile_name, как определено в filters фронтенда
        profile_name_filter: Optional[str] = request.args.get('profile_name') # или 'profile_num', если это предпочтительнее
        form_education_name: Optional[str] = request.args.get('form_education')
        year_beg_str: Optional[str] = request.args.get('year_beg')
        year_beg: Optional[int] = int(year_beg_str) if year_beg_str and year_beg_str.isdigit() else None
        degree_education_name: Optional[str] = request.args.get('degree_education')
        search_query: Optional[str] = request.args.get('search')
        offset_str: Optional[str] = request.args.get('offset', default='0')
        offset: int = int(offset_str) if offset_str and offset_str.isdigit() else 0
        limit_str: Optional[str] = request.args.get('limit', default='20')
        limit: Optional[int] = int(limit_str) if limit_str and limit_str.isdigit() else 20

        aups_result = get_external_aups_list(
            program_code=program_code,
            # ИЗМЕНЕНИЕ: Передаем profile_name, а не profile_num
            profile_name=profile_name_filter,
            form_education_name=form_education_name,
            year_beg=year_beg,
            degree_education_name=degree_education_name,
            search_query=search_query,
            offset=offset,
            limit=limit
        )
        return jsonify(aups_result), 200
    except Exception as e:
        logger.error(f"Error in /external/aups: {e}", exc_info=True)
        return jsonify({"error": f"Ошибка сервера при получении списка АУП из внешней БД: {e}"}), 500

@competencies_matrix_bp.route('/external/aups/<int:aup_id>/disciplines', methods=['GET'])
@login_required
@approved_required
def get_external_aup_disciplines_route(aup_id):
    try:
        disciplines_list = get_external_aup_disciplines(aup_id)
        return jsonify(disciplines_list), 200
    except Exception as e:
        logger.error(f"Error in /external/aups/{aup_id}/disciplines: {e}", exc_info=True)
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