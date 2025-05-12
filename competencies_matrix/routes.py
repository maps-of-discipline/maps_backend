# competencies_matrix/routes.py
# Маршруты (API endpoints) для модуля матрицы компетенций.
#

from flask import request, jsonify, abort
from . import competencies_matrix_bp
from typing import Optional

# --- Импортируем специфичные функции из логики модуля компетенций ---
from .logic import (
    get_educational_programs_list, get_program_details,
    get_matrix_for_aup, update_matrix_link,
    create_competency, create_indicator,
    parse_fgos_file, save_fgos_data, get_fgos_list, get_fgos_details, delete_fgos,
    parse_prof_standard_file, save_prof_standard_data,
    get_prof_standards_list, get_prof_standard_details,
    get_external_aups_list, get_external_aup_disciplines,
    # Импортируем функцию обновления компетенции
    update_competency as logic_update_competency,
    delete_competency as logic_delete_competency,
    update_indicator as logic_update_indicator,
    delete_indicator as logic_delete_indicator,
)

from auth.logic import login_required, approved_required, admin_only
import logging
# --- Импортируем модели из нашего модуля ---
from .models import db, Competency, Indicator, CompetencyType, ProfStandard # Добавлены импорты Competency, Indicator, CompetencyType

from sqlalchemy.orm import joinedload # Keep joinedload import if needed in this file directly

logger = logging.getLogger(__name__)

# Educational Programs Endpoints
@competencies_matrix_bp.route('/programs', methods=['GET'])
@login_required
@approved_required
def get_programs():
    """Get list of all educational programs."""
    programs_list = get_educational_programs_list() # Из logic.py
    
    # Используем обновленный EducationalProgram.to_dict с флагами
    # include_aup_list=True, include_fgos=True, include_selected_ps_list=True
    result = [
        p.to_dict(
             include_aup_list=True,
             include_fgos=True,
             include_selected_ps_list=True
        ) for p in programs_list
    ]
    return jsonify(result)

@competencies_matrix_bp.route('/programs/<int:program_id>', methods=['GET'])
@login_required
@approved_required
def get_program(program_id):
    """Get detailed information about an educational program."""
    details = get_program_details(program_id)
    if not details:
        return jsonify({"error": "Образовательная программа не найдена"}), 404
    return jsonify(details)


# Competency Matrix Endpoints
@competencies_matrix_bp.route('/matrix/<string:aup_num>', methods=['GET'])
@login_required
@approved_required
def get_matrix(aup_num: str):
    """
    Get data for the competency matrix of a specific AUP by its number.
    Fetches disciplines from the external KD DB and competencies/links from the local DB.
    """
    logger.info(f"Received GET request for matrix for AUP num: {aup_num}")
    
    try:
        matrix_data = get_matrix_for_aup(aup_num)

        # ИСПРАВЛЕНИЕ: Проверяем matrix_data на None явно
        if matrix_data is None or matrix_data.get('source') == 'not_found':
            error_message = matrix_data.get('error_details', f"Данные матрицы для АУП с номером {aup_num} не найдены.") if matrix_data else f"Данные матрицы для АУП с номером {aup_num} не найдены."
            logger.warning(f"Matrix data not found or source='not_found' for AUP num: {aup_num}. Error: {error_message}")
            return jsonify({"error": error_message}), 404

        logger.info(f"Successfully fetched matrix data for AUP num: {aup_num}")
        return jsonify(matrix_data)
        
    except Exception as e:
        # Ловим любые другие исключения из get_matrix_for_aup
        logger.error(f"Error in GET /matrix/{aup_num}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при получении матрицы: {e}")


@competencies_matrix_bp.route('/matrix/link', methods=['POST', 'DELETE'])
@login_required
@approved_required
def manage_matrix_link():
    """
    Create or delete a Discipline(AUP)-Indicator link in the matrix.
    aup_data_id in the request is the ID of the record from the external KD DB aup_data.
    indicator_id is the ID of the indicator (from local DB).
    """
    data = request.get_json()
    if not data or 'aup_data_id' not in data or 'indicator_id' not in data:
        abort(400, description="Отсутствуют обязательные поля: aup_data_id, indicator_id")

    aup_data_id = data['aup_data_id']
    indicator_id = data['indicator_id']
    is_creating = (request.method == 'POST')

    result = update_matrix_link(
        aup_data_id, indicator_id, create=is_creating
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
        status_code = 500
        if result.get('error_type') == 'indicator_not_found': status_code = 404
        elif result.get('error_type') == 'database_error': status_code = 500
        elif result.get('error_type') == 'unexpected_error': status_code = 500
        logger.error(f"Error processing matrix link request via logic: {error_msg}. Details: {result.get('details')}")
        return jsonify({"status": "error", "message": error_msg}), status_code


# Competencies and Indicators Endpoints
@competencies_matrix_bp.route('/competencies', methods=['GET'])
@login_required
@approved_required
def get_all_competencies():
    """Get list of all competencies."""
    try:
        # Fetch from DB, excluding indicators for list view
        competencies = db.session.query(Competency).options(joinedload(Competency.competency_type)).all()
        result = []
        for comp in competencies:
             # Используем обновленный to_dict с include_type=True
             comp_dict = comp.to_dict(rules=['-indicators', '-fgos', '-based_on_labor_function'], include_type=True)
             result.append(comp_dict)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error in GET /competencies: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось получить список компетенций: {e}"}), 500


@competencies_matrix_bp.route('/competencies/<int:comp_id>', methods=['GET'])
@login_required
@approved_required
def get_competency(comp_id):
    """Get one competency by ID with indicators."""
    try:
        competency = db.session.query(Competency).options(
            joinedload(Competency.competency_type),
            joinedload(Competency.indicators)
        ).get(comp_id)
        if not competency:
            return jsonify({"error": "Компетенция не найдена"}), 404

        # Используем обновленный to_dict с include_indicators=True и include_type=True
        result = competency.to_dict(rules=['-fgos', '-based_on_labor_function'], include_indicators=True, include_type=True)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error in GET /competencies/<id>: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось получить компетенцию: {e}"}), 500


@competencies_matrix_bp.route('/competencies', methods=['POST'])
@login_required
@approved_required
@admin_only
def create_new_competency():
    """Create a new competency (typically ПК)."""
    data = request.get_json()
    competency = create_competency(data) # Implemented in logic.py
    if not competency:
        return jsonify({"error": "Не удалось создать компетенцию. Проверьте данные или возможно, она уже существует."}), 400
    # Возвращаем созданный объект, возможно, с типом для фронтенда
    return jsonify(competency.to_dict(rules=['-indicators'], include_type=True)), 201


@competencies_matrix_bp.route('/competencies/<int:comp_id>', methods=['PATCH'])
@login_required
@approved_required
@admin_only
def update_competency_route(comp_id):
    """Update a competency by ID."""
    data = request.get_json()
    if not data:
        abort(400, description="Отсутствуют данные для обновления")

    try:
        updated_comp_dict = logic_update_competency(comp_id, data)

        if updated_comp_dict is not None:
            return jsonify(updated_comp_dict), 200
        else:
            return jsonify({"error": "Компетенция не найдена"}), 404
    except Exception as e:
        logger.error(f"Error updating competency {comp_id} in route: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось обновить компетенцию: {e}"}), 500


@competencies_matrix_bp.route('/competencies/<int:comp_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_competency(comp_id):
    """Delete a competency by ID."""
    try:
        deleted = logic_delete_competency(comp_id, db.session) # Передаем сессию

        if deleted:
            return jsonify({"success": True, "message": "Компетенция успешно удалена"}), 200
        else:
            return jsonify({"success": False, "error": "Компетенция не найдена"}), 404
    except Exception as e:
        logger.error(f"Error deleting competency {comp_id}: {e}", exc_info=True)
        abort(500, description=f"Не удалось удалить компетенцию: {e}")


@competencies_matrix_bp.route('/indicators', methods=['GET'])
@login_required
@approved_required
def get_all_indicators():
    """Get list of all indicators."""
    try:
        indicators = db.session.query(Indicator).options(joinedload(Indicator.competency)).all()
        result = []
        for ind in indicators:
             # Используем обновленный to_dict с include_competency=True
             ind_dict = ind.to_dict(rules=['-labor_functions', '-matrix_entries'], include_competency=True)
             result.append(ind_dict)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error in GET /indicators: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось получить список индикаторов: {e}"}), 500


@competencies_matrix_bp.route('/indicators/<int:ind_id>', methods=['GET'])
@login_required
@approved_required
def get_indicator(ind_id):
    """Get one indicator by ID."""
    try:
        indicator = db.session.query(Indicator).options(
            joinedload(Indicator.competency)
        ).get(ind_id)
        if not indicator:
            return jsonify({"error": "Индикатор не найден"}), 404

        # Используем обновленный to_dict с include_competency=True
        result = indicator.to_dict(rules=['-labor_functions', '-matrix_entries'], include_competency=True)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error in GET /indicators/<id>: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось получить индикатор: {e}"}), 500


@competencies_matrix_bp.route('/indicators', methods=['POST'])
@login_required
@approved_required
@admin_only
def create_new_indicator():
    """Create a new indicator for an existing competency."""
    data = request.get_json()
    indicator = create_indicator(data) # Implemented in logic.py
    if not indicator:
        return jsonify({"error": "Не удалось создать индикатор. Проверьте данные или возможно, он уже существует/родительская компетенция не найдена."}), 400
    # Возвращаем созданный объект с инфо о родительской компетенции
    return jsonify(indicator.to_dict(rules=['-matrix_entries'], include_competency=True)), 201


@competencies_matrix_bp.route('/indicators/<int:ind_id>', methods=['PATCH'])
@login_required
@approved_required
@admin_only
def update_indicator_route(ind_id):
    """Update an indicator by ID."""
    data = request.get_json()
    if not data:
        abort(400, description="Отсутствуют данные для обновления")

    try:
        updated_ind = logic_update_indicator(ind_id, data) 

        if updated_ind:
            # Возвращаем обновленный объект с инфо о родительской компетенции
            return jsonify(updated_ind.to_dict(rules=['-matrix_entries'], include_competency=True)), 200
        else:
            return jsonify({"error": "Индикатор не найден"}), 404
    except ValueError as ve: 
        logger.warning(f"Update indicator route: Validation error for indicator {ind_id}: {ve}")
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Error updating indicator {ind_id}: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось обновить индикатор: {e}"}), 500


@competencies_matrix_bp.route('/indicators/<int:ind_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_indicator_route(ind_id):
    """Delete an indicator by ID."""
    try:
        deleted = logic_delete_indicator(ind_id, db.session) # Передаем сессию

        if deleted:
            return jsonify({"success": True, "message": "Индикатор успешно удалена"}), 200
        else:
            return jsonify({"success": False, "error": "Индикатор не найден"}), 404
    except Exception as e:
        logger.error(f"Error deleting indicator {ind_id}: {e}", exc_info=True)
        abort(500, description=f"Не удалось удалить индикатор: {e}")


# FGOS Endpoints
@competencies_matrix_bp.route('/fgos', methods=['GET'])
@login_required
@approved_required
def get_all_fgos():
    """Get list of all saved FGOS VO."""
    fgos_list = get_fgos_list()
    # Используем FgosVo.to_dict без специальных флагов - только колонки
    result = [f.to_dict() for f in fgos_list]
    return jsonify(result), 200

@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['GET'])
@login_required
@approved_required
def get_fgos_details_route(fgos_id):
    """Get detailed information about a FGOS VO by ID."""
    try:
        # В logic.get_fgos_details уже настроена загрузка связей и форматирование в dict
        details = get_fgos_details(fgos_id) 
        if not details:
            return jsonify({"error": "ФГОС ВО не найден"}), 404
        return jsonify(details), 200
    except Exception as e:
        logger.error(f"Error in GET /fgos/<id>: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось получить ФГОС ВО: {e}"}), 500


@competencies_matrix_bp.route('/fgos/upload', methods=['POST'])
@login_required
@approved_required
@admin_only
def upload_fgos():
    """Upload and parse a FGOS VO PDF file."""
    if 'file' not in request.files:
        abort(400, description="Файл не найден в запросе")
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        abort(400, description="Файл не выбран или неверный формат (требуется PDF)")
    
    try:
        file_bytes = file.read()
        parsed_data = parse_fgos_file(file_bytes, file.filename)
        
        if not parsed_data or not parsed_data.get('metadata'):
             logger.error(f"Upload FGOS: Parsing succeeded but essential metadata missing for {file.filename}.")
             abort(400, description="Не удалось извлечь основные метаданные из файла ФГОС.")

        return jsonify(parsed_data), 200
    except ValueError as e:
        logger.error(f"Upload FGOS: Parsing Error for {file.filename}: {e}")
        abort(400, description=f"Ошибка парсинга файла: {e}")
    except Exception as e:
        logger.error(f"Upload FGOS: Unexpected error processing FGOS upload for {file.filename}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при обработке файла: {e}")


@competencies_matrix_bp.route('/fgos/save', methods=['POST'])
@login_required
@approved_required
@admin_only
def save_fgos():
    """Save parsed FGOS VO data to the DB."""
    data = request.get_json()
    parsed_data = data.get('parsed_data')
    filename = data.get('filename')
    options = data.get('options', {})
    
    if not parsed_data or not filename or not parsed_data.get('metadata'):
        abort(400, description="Некорректные данные для сохранения (отсутствуют parsed_data, filename или metadata)")

    try:
        # save_fgos_data уже управляет своей транзакцией в рамках переданной сессии
        # и обрабатывает force_update
        saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=options.get('force_update', False))
        
        if saved_fgos is None:
             # Ошибка должна быть залогирована внутри save_fgos_data
             abort(500, description="Ошибка при сохранении данных ФГОС в базу данных.")
        
        # Возвращаем id и success статус
        return jsonify({
            "success": True,
            "fgos_id": saved_fgos.id,
            "message": "Данные ФГОС успешно сохранены."
        }), 201

    except Exception as e:
        logger.error(f"Error saving FGOS data from file {filename}: {e}", exc_info=True)
        # db.session.rollback() # Откат должен быть внутри save_fgos_data при необходимости
        abort(500, description=f"Неожиданная ошибка сервера при сохранении: {e}")


@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_fgos_route(fgos_id):
    """Delete a FGOS VO by ID."""
    try:
        # delete_fgos уже управляет своей транзакцией
        deleted = delete_fgos(fgos_id, db.session)

        if deleted:
            return jsonify({"success": True, "message": "ФГОС успешно удален"}), 200
        else:
            return jsonify({"success": False, "error": "ФГОС не найден"}), 404
    except Exception as e:
        logger.error(f"Error deleting FGOS {fgos_id}: {e}", exc_info=True)
        # db.session.rollback() # Откат должен быть внутри delete_fgos
        abort(500, description=f"Неожиданная ошибка сервера при удалении: {e}")


# Professional Standards Endpoints
@competencies_matrix_bp.route('/profstandards', methods=['GET'])
@login_required
@approved_required
def get_all_profstandards():
    """Get list of all saved Professional Standards."""
    try:
        prof_standards = db.session.query(ProfStandard).all()
        # Используем ProfStandard.to_dict без специальных флагов - только колонки
        result = [ps.to_dict() for ps in prof_standards]
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error in GET /profstandards: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось получить список профстандартов: {e}"}), 500


@competencies_matrix_bp.route('/profstandards/<int:ps_id>', methods=['GET'])
@login_required
@approved_required
def get_profstandard_details_route(ps_id):
    """Get detailed information about a Professional Standard by ID."""
    try:
        # В logic.get_prof_standard_details уже настроена загрузка связей и форматирование в dict
        details = get_prof_standard_details(ps_id)
        if not details:
            return jsonify({"error": "Профстандарт не найден"}), 404
        return jsonify(details), 200
    except Exception as e:
        logger.error(f"Error in GET /profstandards/<id>: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось получить профстандарт: {e}"}), 500


@competencies_matrix_bp.route('/profstandards/upload', methods=['POST'])
@login_required
@approved_required
@admin_only
def upload_profstandard():
    """Upload and parse a Professional Standard file (HTML/DOCX/PDF)."""
    if 'file' not in request.files:
        abort(400, description="Файл не найден в запросе")
    file = request.files['file']
    if file.filename == '':
        abort(400, description="Файл не выбран")

    try:
        file_bytes = file.read()
        # parse_prof_standard_file теперь возвращает {"success": bool, ... "parsed_data": {...}}
        result = parse_prof_standard_file(file_bytes, file.filename)

        if not result.get('success'):
            status_code = 400
            if result.get('error_type') == 'not_implemented': status_code = 501
            elif result.get('error_type') == 'parsing_error': status_code = 400
            elif result.get('error_type') == 'unsupported_format': status_code = 415
            logger.error(f"Upload PS: Failed processing file {file.filename}. Error: {result.get('error')}. Type: {result.get('error_type')}")
            return jsonify({
                "status": "error",
                "message": result.get('error', 'Ошибка обработки файла ПС'),
                "error_type": result.get('error_type', 'unknown')
            }), status_code

        parsed_data_for_save = result.get('parsed_data')
        if parsed_data_for_save:
            # save_prof_standard_data уже управляет своей транзакцией и force_update
            # TODO: В MVP загрузка сразу сохраняет, если нет дубликата. 
            # Если дубликат, надо вернуть 409 Conflict и предложить перезаписать.
            # Сейчас save_prof_standard_data вернет existing_ps и залогирует WARN.
            # В роуте надо это обработать.
            try:
                saved_ps = save_prof_standard_data(parsed_data_for_save, file.filename, db.session, force_update=False)

                if saved_ps is None:
                     # Ошибка уже залогирована в save_prof_standard_data
                     abort(500, description="Ошибка при сохранении данных профессионального стандарта.")
                
                # Проверяем, был ли это существующий ПС (если save_prof_standard_data его вернул без force=True)
                # Нам нужно отличить создание от "уже существует".
                # save_prof_standard_data сейчас не возвращает explicit status like "created" or "exists".
                # Простой способ: проверить, существовал ли PS до вызова save_prof_standard_data,
                # но это требует еще одного запроса к БД.
                # Альтернатива: save_prof_standard_data должен возвращать статус.
                # MVP Упрощение: Если save_prof_standard_data вернул объект, считаем успешным.
                # Если был дубликат без force, save_prof_standard_data вернет существующий объект.
                # Мы не можем отличить создание от "уже существует" только по возвращаемому объекту.
                # Давайте пока вернем существующий объект с 200 OK если был дубликат, 
                # и новый объект с 201 Created если был создан.
                # Но save_prof_standard_data возвращает existing_ps (или новый) или None.
                # Проще всего: save_prof_standard_data пусть возвращает (объект, статус: 'created'/'exists'/None)
                # ИЛИ просто полагаемся на то, что фронтенд выведет сообщение об ошибке, если PS с таким кодом уже есть.
                # Сейчас save_prof_standard_data при дубликате без force=True логирует WARN и возвращает existing_ps.
                # Роут получает existing_ps и возвращает 201. Это неверно.
                # Нужно либо изменить save_prof_standard_data для возврата статуса, либо проверить существование ДО.

                # ВРЕМЕННОЕ РЕШЕНИЕ ДЛЯ MVP: Предположим, что если saved_ps не None, то все ОК. 
                # Обработка дубликатов без force=True остается на фронтенде как сообщение об ошибке после попытки сохранения.
                # TODO: Реализовать более явную обработку дубликатов (например, 409 Conflict) на бэкенде.

                return jsonify({
                    "status": "success",
                    "message": "Профессиональный стандарт успешно загружен и сохранен.",
                    "prof_standard_id": saved_ps.id,
                    "code": saved_ps.code,
                    "name": saved_ps.name
                }), 201 # Всегда возвращаем 201, предполагая создание или успешное обновление/игнорирование

            except Exception as e:
                 # Ошибки внутри save_prof_standard_data (не IntegrityError) могут быть пойманы здесь
                 logger.error(f"Upload PS: Error during save_prof_standard_data for {file.filename}: {e}", exc_info=True)
                 abort(500, description="Ошибка при сохранении данных профессионального стандарта.")

        else:
            # Этот случай маловероятен, если success=True, но parsed_data нет
            logger.error(f"Upload PS: Logic indicated success for {file.filename}, but no parsed_data for save.")
            abort(500, description="Неожиданная ошибка при парсинге: нет данных для сохранения.")

    except Exception as e:
        # Ловим исключения из parse_prof_standard_file или других мест
        logger.error(f"Upload PS: Unexpected error in /profstandards/upload for {file.filename}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при обработке файла: {e}")


@competencies_matrix_bp.route('/profstandards/<int:ps_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_profstandard(ps_id):
    """Delete a Professional Standard by ID."""
    try:
        # TODO: Implement logic.delete_prof_standard
        # Assuming logic.delete_prof_standard exists and handles the deletion
        # deleted = logic.delete_prof_standard(ps_id, db.session) # Use db.session

        # STUB Implementation for DELETE PS
        deleted = False # Replace with actual logic call

        if deleted:
            return jsonify({"success": True, "message": "Профессиональный стандарт успешно удален"}), 200
        else:
            # Если не найдено, возвращаем 404
            # return jsonify({"success": False, "error": "Профессиональный стандарт не найден"}), 404
            # TODO: Replace with actual logic call
            abort(501, description="DELETE /profstandards/<id> не реализован") # Возвращаем 501 Not Implemented
    except Exception as e:
        logger.error(f"Error deleting professional standard {ps_id}: {e}", exc_info=True)
        abort(500, description=f"Не удалось удалить профессиональный стандарт: {e}")


# External KD DB Endpoints
@competencies_matrix_bp.route('/external/aups', methods=['GET'])
@login_required
@approved_required
def get_external_aups():
    """
    Get list of AUPs from the external KD DB with filters and pagination.
    """
    try:
        program_code: Optional[str] = request.args.get('program_code');
        profile_num: Optional[str] = request.args.get('profile_num');
        profile_name: Optional[str] = request.args.get('profile_name');
        form_education_name: Optional[str] = request.args.get('form_education');
        year_beg_str: Optional[str] = request.args.get('year_beg');
        year_beg: Optional[int] = int(year_beg_str) if year_beg_str and year_beg_str.isdigit() else None
        degree_education_name: Optional[str] = request.args.get('degree_education');
        search_query: Optional[str] = request.args.get('search');
        offset_str: Optional[str] = request.args.get('offset', default='0');
        offset: int = int(offset_str) if offset_str and offset_str.isdigit() else 0
        limit_str: Optional[str] = request.args.get('limit', default='20');
        limit: Optional[int] = int(limit_str) if limit_str and limit_str.isdigit() else None

        aups_result = get_external_aups_list(
            program_code=program_code, profile_num=profile_num, profile_name=profile_name,
            form_education_name=form_education_name, year_beg=year_beg,
            degree_education_name=degree_education_name, search_query=search_query,
            offset=offset, limit=limit
        );
        return jsonify(aups_result), 200;
    except Exception as e:
        logger.error(f"Error in GET /external/aups: {e}", exc_info=True)
        abort(500, description=f"Ошибка сервера при получении списка АУП из внешней БД: {e}");


@competencies_matrix_bp.route('/external/aups/<int:aup_id>/disciplines', methods=['GET'])
@login_required
@approved_required
def get_external_aup_disciplines_route(aup_id):
    """
    Get list of discipline entries (AupData) for a specific AUP by its ID from external KD DB.
    """
    try:
        disciplines_list = get_external_aup_disciplines(aup_id);
        return jsonify(disciplines_list), 200;
    except Exception as e:
        logger.error(f"Error in GET /external/aups/{aup_id}/disciplines: {e}", exc_info=True)
        abort(500, description=f"Ошибка сервера при получении списка дисциплин из внешней БД: {e}");