# filepath: competencies_matrix/routes.py
from flask import request, jsonify, abort
from . import competencies_matrix_bp
from typing import Optional

from .logic import (
    get_educational_programs_list, get_program_details,
    get_matrix_for_aup, update_matrix_link,
    create_competency, create_indicator,
    parse_fgos_file, save_fgos_data, get_fgos_list, get_fgos_details, delete_fgos,
    handle_prof_standard_upload_parsing,
    save_prof_standard_data, 
    get_prof_standards_list, get_prof_standard_details,
    get_all_competencies as logic_get_all_competencies,
    get_all_indicators as logic_get_all_indicators,
    update_competency as logic_update_competency,
    delete_competency as logic_delete_competency,
    update_indicator as logic_update_indicator,
    delete_indicator as logic_delete_indicator,
    get_external_aups_list, get_external_aup_disciplines,
    delete_prof_standard as logic_delete_profstandard, 
)

from auth.logic import login_required, approved_required, admin_only
import logging
from .models import db, Competency, Indicator, CompetencyType, ProfStandard 
from sqlalchemy.orm import joinedload 
from sqlalchemy.exc import IntegrityError 

logger = logging.getLogger(__name__)

# Educational Programs Endpoints
@competencies_matrix_bp.route('/programs', methods=['GET'])
@login_required
@approved_required
def get_programs():
    programs_list = get_educational_programs_list() 
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
    details = get_program_details(program_id)
    if not details:
        return jsonify({"error": "Образовательная программа не найдена"}), 404
    return jsonify(details)


# Competency Matrix Endpoints
@competencies_matrix_bp.route('/matrix/<string:aup_num>', methods=['GET'])
@login_required
@approved_required
def get_matrix(aup_num: str):
    """Get data for the competency matrix of a specific AUP by its number."""
    logger.info(f"Received GET request for matrix for AUP num: {aup_num}")
    
    try:
        matrix_data = get_matrix_for_aup(aup_num)

        if matrix_data is None or matrix_data.get('source') == 'not_found':
            error_message = matrix_data.get('error_details', f"Данные матрицы для АУП с номером {aup_num} не найдены.") if matrix_data else f"Данные матрицы для АУП с номером {aup_num} не найдены."
            logger.warning(f"Matrix data not found or source='not_found' for AUP num: {aup_num}. Error: {error_message}")
            return jsonify({"error": error_message}), 404

        logger.info(f"Successfully fetched matrix data for AUP num: {aup_num}")
        return jsonify(matrix_data)
        
    except Exception as e:
        logger.error(f"Error in GET /matrix/{aup_num}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при получении матрицы: {e}")


@competencies_matrix_bp.route('/matrix/link', methods=['POST', 'DELETE'])
@login_required
@approved_required
def manage_matrix_link():
    """Create or delete a Discipline(AUP)-Indicator link in the matrix."""
    data = request.get_json()
    if not data or 'aup_data_id' not in data or 'indicator_id' not in data:
        abort(400, description="Отсутствуют обязательные поля: aup_data_id, indicator_id")

    aup_data_id = data['aup_data_id']
    indicator_id = data['indicator_id']
    is_creating = (request.method == 'POST')

    # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
    result = update_matrix_link(aup_data_id, indicator_id, create=is_creating)

    if result['success']:
        db.session.commit() # ЯВНЫЙ КОММИТ, если логика не делает его сама
        if is_creating:
            status_code = 201 if result['status'] == 'created' else 200
            return jsonify({"status": result['status'], "message": result.get('message', "Операция выполнена")}), status_code
        else:
            status_code = 200 if result['status'] == 'deleted' else 404
            return jsonify({"status": result['status'], "message": result.get('message', "Операция выполнена")}), status_code
    else:
        db.session.rollback() # ЯВНЫЙ ОТКАТ при ошибке
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
def get_all_competencies_route():
    """Get list of all competencies."""
    try:
        competencies = logic_get_all_competencies()
        return jsonify(competencies), 200
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
    try:
        # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
        competency = create_competency(data, db.session) # Передаем db.session
        
        if not competency:
            db.session.rollback() # ЯВНЫЙ ОТКАТ при неудаче в логике
            return jsonify({"error": "Не удалось создать компетенцию. Проверьте данные или возможно, она уже существует."}), 400
        
        db.session.commit() # ЯВНЫЙ КОММИТ
        return jsonify(competency.to_dict(rules=['-indicators'], include_type=True, include_educational_programs=True)), 201
    except ValueError as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ при ошибке валидации
        logger.error(f"Validation error creating competency: {e}")
        return jsonify({"error": str(e)}), 400
    except IntegrityError as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ при ошибке целостности
        logger.error(f"Integrity error creating competency: {e.orig}", exc_info=True)
        return jsonify({"error": "Компетенция с таким кодом уже существует для этого типа и ФГОС (если применимо)."}), 409
    except Exception as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ при неожиданной ошибке
        logger.error(f"Unexpected error creating competency: {e}", exc_info=True)
        return jsonify({"error": f"Неожиданная ошибка сервера при создании компетенции: {e}"}), 500


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
        # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
        updated_comp_dict = logic_update_competency(comp_id, data, db.session)

        if updated_comp_dict is not None:
            db.session.commit() # ЯВНЫЙ КОММИТ
            return jsonify(updated_comp_dict), 200
        else:
            db.session.rollback() # ЯВНЫЙ ОТКАТ
            return jsonify({"error": "Компетенция не найдена"}), 404
    except ValueError as ve:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.warning(f"Update competency route: Validation error for competency {comp_id}: {ve}")
        return jsonify({"error": str(ve)}), 400
    except IntegrityError as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Integrity error updating competency {comp_id}: {e.orig}", exc_info=True)
        return jsonify({"error": "Компетенция с таким кодом уже существует."}), 409
    except Exception as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Error updating competency {comp_id} in route: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось обновить компетенцию: {e}"}), 500


@competencies_matrix_bp.route('/competencies/<int:comp_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_competency_route(comp_id):
    """Delete a competency by ID."""
    try:
        # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
        deleted = logic_delete_competency(comp_id, db.session) 

        if deleted:
            db.session.commit() # ЯВНЫЙ КОММИТ
            return jsonify({"success": True, "message": "Компетенция успешно удалена"}), 200
        else:
            db.session.rollback() # ЯВНЫЙ ОТКАТ
            return jsonify({"success": False, "error": "Компетенция не найдена"}), 404
    except Exception as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Error deleting competency {comp_id}: {e}", exc_info=True)
        abort(500, description=f"Не удалось удалить компетенцию: {e}")


@competencies_matrix_bp.route('/indicators', methods=['GET'])
@login_required
@approved_required
def get_all_indicators_route():
    """Get list of all indicators."""
    try:
        indicators = logic_get_all_indicators()
        return jsonify(indicators), 200
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
    try:
        # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
        indicator = create_indicator(data, db.session)
        if not indicator:
            db.session.rollback() # ЯВНЫЙ ОТКАТ
            return jsonify({"error": "Не удалось создать индикатор. Проверьте данные или возможно, он уже существует/родительская компетенция не найдена."}), 400
        db.session.commit() # ЯВНЫЙ КОММИТ
        return jsonify(indicator.to_dict(rules=['-matrix_entries'], include_competency=True)), 201
    except ValueError as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Validation error creating indicator: {e}")
        return jsonify({"error": str(e)}), 400
    except IntegrityError as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Integrity error creating indicator: {e.orig}", exc_info=True)
        return jsonify({"error": "Индикатор с таким кодом уже существует для этой компетенции."}), 409
    except Exception as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Unexpected error creating indicator: {e}", exc_info=True)
        return jsonify({"error": f"Неожиданная ошибка сервера при создании индикатора: {e}"}), 500


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
        # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
        updated_ind = logic_update_indicator(ind_id, data, db.session) 

        if updated_ind:
            db.session.commit() # ЯВНЫЙ КОММИТ
            return jsonify(updated_ind.to_dict(rules=['-matrix_entries'], include_competency=True)), 200
        else:
            db.session.rollback() # ЯВНЫЙ ОТКАТ
            return jsonify({"error": "Индикатор не найден"}), 404
    except ValueError as ve: 
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.warning(f"Update indicator route: Validation error for indicator {ind_id}: {ve}")
        return jsonify({"error": str(ve)}), 400
    except IntegrityError as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Integrity error updating indicator {ind_id}: {e.orig}", exc_info=True)
        return jsonify({"error": "Индикатор с таким кодом уже существует для этой компетенции."}), 409
    except Exception as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Error updating indicator {ind_id}: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось обновить индикатор: {e}"}), 500


@competencies_matrix_bp.route('/indicators/<int:ind_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_indicator_route(ind_id):
    """Delete an indicator by ID."""
    try:
        # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
        deleted = logic_delete_indicator(ind_id, db.session) 

        if deleted:
            db.session.commit() # ЯВНЫЙ КОММИТ
            return jsonify({"success": True, "message": "Индикатор успешно удалена"}), 200
        else:
            db.session.rollback() # ЯВНЫЙ ОТКАТ
            return jsonify({"success": False, "error": "Индикатор не найден"}), 404
    except Exception as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Error deleting indicator {ind_id}: {e}", exc_info=True)
        abort(500, description=f"Не удалось удалить индикатор: {e}")


# FGOS Endpoints
@competencies_matrix_bp.route('/fgos', methods=['GET'])
@login_required
@approved_required
def get_all_fgos():
    """Get list of all saved FGOS VO."""
    fgos_list = get_fgos_list()
    result = [f.to_dict() for f in fgos_list]
    return jsonify(result), 200

@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['GET'])
@login_required
@approved_required
def get_fgos_details_route(fgos_id):
    """Get detailed information about a FGOS VO by ID."""
    try:
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
        # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
        saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=options.get('force_update', False))
        
        if saved_fgos is None:
             db.session.rollback() # ЯВНЫЙ ОТКАТ
             abort(500, description="Ошибка при сохранении данных ФГОС в базу данных.")
        
        db.session.commit() # ЯВНЫЙ КОММИТ
        return jsonify({
            "success": True,
            "fgos_id": saved_fgos.id,
            "message": "Данные ФГОС успешно сохранены."
        }), 201

    except IntegrityError as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Integrity error saving FGOS: {e.orig}", exc_info=True)
        return jsonify({"error": "ФГОС с такими метаданными (направление, номер, дата) уже существует."}), 409
    except Exception as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Error saving FGOS data from file {filename}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при сохранении: {e}")


@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_fgos_route(fgos_id):
    """Delete a FGOS VO by ID."""
    try:
        # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
        deleted = delete_fgos(fgos_id, db.session) 

        if deleted:
            db.session.commit() # ЯВНЫЙ КОММИТ
            return jsonify({"success": True, "message": "ФГОС успешно удален"}), 200
        else:
            db.session.rollback() # ЯВНЫЙ ОТКАТ
            return jsonify({"success": False, "error": "ФГОС не найден"}), 404
    except Exception as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Error deleting FGOS {fgos_id}: {e}", exc_info=True)
        abort(500, description=f"Не удалось удалить ФГОС: {e}")


# Professional Standards Endpoints
@competencies_matrix_bp.route('/profstandards/parse-preview', methods=['POST'])
@login_required
@approved_required
@admin_only
def parse_profstandard_for_preview():
    """Upload a Professional Standard file (XML) for parsing and preview."""
    if 'file' not in request.files:
        abort(400, description="Файл не найден в запросе")
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.xml'):
        abort(400, description="Файл не выбран или неверный формат (требуется XML)")

    try:
        file_bytes = file.read()
        parse_result = handle_prof_standard_upload_parsing(file_bytes, file.filename)

        if not parse_result.get('success'):
            status_code = 400
            if parse_result.get('error_type') == 'not_implemented': status_code = 501
            elif parse_result.get('error_type') == 'parsing_error': status_code = 400
            elif parse_result.get('error_type') == 'unsupported_format': status_code = 415
            logger.error(f"Parse PS for preview: Failed processing file {file.filename}. Error: {parse_result.get('error')}. Type: {parse_result.get('error_type')}")
            return jsonify({
                "status": "error",
                "message": parse_result.get('error', 'Ошибка обработки файла ПС'),
                "error_type": parse_result.get('error_type', 'unknown')
            }), status_code

        parsed_data = parse_result.get('parsed_data')
        ps_code = parsed_data.get('code')
        
        existing_ps_record = None
        if ps_code:
            existing_ps = db.session.query(ProfStandard).filter_by(code=ps_code).first()
            if existing_ps:
                # ИСПРАВЛЕНО: Вызываем get_prof_standard_details, который возвращает полную структуру
                existing_ps_record = get_prof_standard_details(existing_ps.id)
                # Если get_prof_standard_details возвращает None (например, если ID невалиден),
                # то existing_ps_record останется None.
        
        response_data = {
            "status": "success",
            "message": "Файл успешно распознан. Проверьте данные перед сохранением.",
            "parsed_data": parsed_data,
            "filename": file.filename,
            "existing_ps_record": existing_ps_record # Теперь это полная структура, если найдено
        }
        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"Parse PS for preview: Unexpected error in /profstandards/parse-preview for {file.filename}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при обработке файла: {e}")

@competencies_matrix_bp.route('/profstandards/save', methods=['POST'])
@login_required
@approved_required
@admin_only
def save_profstandard():
    """Save parsed Professional Standard data to the DB after user confirmation."""
    data = request.get_json()
    parsed_data = data.get('parsed_data')
    filename = data.get('filename')
    options = data.get('options', {})
    
    if not parsed_data or not filename or not parsed_data.get('code'):
        abort(400, description="Некорректные данные для сохранения (отсутствуют parsed_data, filename или код ПС)")

    try:
        # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
        saved_ps = save_prof_standard_data(parsed_data, filename, db.session, force_update=options.get('force_update', False))
        
        if saved_ps is None:
             db.session.rollback() # ЯВНЫЙ ОТКАТ
             abort(500, description="Ошибка при сохранении данных профессионального стандарта.")
        
        db.session.commit() # ЯВНЫЙ КОММИТ
        status_code = 201
        message = "Профессиональный стандарт успешно сохранен."
        
        return jsonify({
            "status": "success",
            "message": message,
            "prof_standard_id": saved_ps.id,
            "code": saved_ps.code,
            "name": saved_ps.name
        }), status_code

    except IntegrityError as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Integrity error saving PS: {e.orig}", exc_info=True)
        return jsonify({"error": "Профессиональный стандарт с таким кодом уже существует."}), 409
    except Exception as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Error saving PS data from file {filename}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при сохранении: {e}")


@competencies_matrix_bp.route('/profstandards', methods=['GET'])
@login_required
@approved_required
def get_all_profstandards():
    """Get list of all saved Professional Standards."""
    try:
        prof_standards = get_prof_standards_list()
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
        details = get_prof_standard_details(ps_id)
        if not details:
            return jsonify({"error": "Профстандарт не найден"}), 404
        return jsonify(details), 200
    except Exception as e:
        logger.error(f"Error in GET /profstandards/<id>: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось получить профстандарт: {e}"}), 500


@competencies_matrix_bp.route('/profstandards/<int:ps_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_profstandard(ps_id):
    """Delete a Professional Standard by ID."""
    try:
        # ИСПРАВЛЕНО: УБРАНО with db.session.begin()
        deleted = logic_delete_profstandard(ps_id, db.session) 

        if deleted:
            db.session.commit() # ЯВНЫЙ КОММИТ
            return jsonify({"success": True, "message": "Профессиональный стандарт успешно удален"}), 200
        else:
            db.session.rollback() # ЯВНЫЙ ОТКАТ
            return jsonify({"success": False, "error": "Профессиональный стандарт не найден"}), 404
    except Exception as e:
        db.session.rollback() # ЯВНЫЙ ОТКАТ
        logger.error(f"Error deleting professional standard {ps_id}: {e}", exc_info=True)
        abort(500, description=f"Не удалось удалить профессиональный стандарт: {e}")


# External KD DB Endpoints
@competencies_matrix_bp.route('/external/aups', methods=['GET'])
@login_required
@approved_required
def get_external_aups():
    """Get list of AUPs from the external KD DB with filters and pagination."""
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
    """Get list of discipline entries (AupData) for a specific AUP by its ID from external KD DB."""
    try:
        disciplines_list = get_external_aup_disciplines(aup_id);
        return jsonify(disciplines_list), 200;
    except Exception as e:
        logger.error(f"Error in GET /external/aups/{aup_id}/disciplines: {e}", exc_info=True)
        abort(500, description=f"Ошибка сервера при получении списка дисциплин из внешней БД: {e}");