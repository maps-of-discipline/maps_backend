# filepath: competencies_matrix/routes.py
from flask import request, jsonify, abort, send_file
from . import competencies_matrix_bp
from typing import Optional, List

from .logic import (
    get_educational_programs_list, get_program_details,
    get_matrix_for_aup, update_matrix_link,
    create_competency, create_indicator,
    parse_fgos_file, save_fgos_data, get_fgos_list, get_fgos_details, delete_fgos as logic_delete_fgos,
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
    search_prof_standards as logic_search_prof_standards,
    generate_prof_standard_excel_export_logic,
    process_uk_indicators_disposition_file,
    save_uk_indicators_from_disposition,
    handle_pk_name_correction,
    handle_pk_ipk_generation,
    create_educational_program,
    batch_create_pk_and_ipk,
    delete_educational_program, 
)

from auth.logic import login_required, approved_required, admin_only
import logging, datetime, io
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

@competencies_matrix_bp.route('/programs', methods=['POST'])
@login_required
@approved_required
@admin_only 
def create_program_route():
    """Создает новую образовательную программу (ОПОП) на основе данных от фронтенда."""
    data = request.get_json()
    if not data:
        abort(400, description="Отсутствуют данные в теле запроса.")
    try:
        new_program_obj = create_educational_program(data, db.session)
        db.session.commit()
        
        return jsonify(new_program_obj.to_dict(include_aup_list=True, include_fgos=True)), 201

    except ValueError as e:
        db.session.rollback()
        logger.error(f"Validation error creating program: {e}")
        return jsonify({"error": str(e)}), 400
    except IntegrityError:
        db.session.rollback()
        logger.error(f"Integrity error creating program", exc_info=True)
        return jsonify({"error": "Образовательная программа с такими параметрами (код, профиль, год, форма) уже существует."}), 409
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error creating program: {e}", exc_info=True)
        return jsonify({"error": f"Неожиданная ошибка сервера при создании образовательной программы."}), 500


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
 
    try:
        result = update_matrix_link(aup_data_id, indicator_id, create=is_creating)
 
        if result['success']:
            db.session.commit()
            if is_creating:
                status_code = 201 if result['status'] == 'created' else 200
                return jsonify({"status": result['status'], "message": result.get('message', "Операция выполнена")}), status_code
            else:
                status_code = 200 if result['status'] == 'deleted' else 404 if result['status'] == 'not_found' else 200
                return jsonify({"status": result['status'], "message": result.get('message', "Операция выполнена")}), status_code
        else:
            db.session.rollback()
            error_msg = result.get('message', "Не удалось выполнить операцию")
            status_code = 500
            if result.get('error_type') == 'aup_data_not_found': status_code = 404
            if result.get('error_type') == 'indicator_not_found': status_code = 404
            logger.error(f"Error processing matrix link request via logic: {error_msg}. Details: {result.get('details')}")
            return jsonify({"status": "error", "message": error_msg}), status_code
    except Exception as e:
        db.session.rollback()
        logger.error(f"Exception in manage_matrix_link: {e}", exc_info=True)
        return jsonify({"error": "Внутренняя ошибка сервера при обработке связи."}), 500


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
        competency = create_competency(data, db.session)
        
        if not competency:
            db.session.rollback()
            return jsonify({"error": "Не удалось создать компетенцию. Проверьте данные или возможно, она уже существует."}), 400
        
        db.session.commit()
        return jsonify(competency.to_dict(rules=['-indicators'], include_type=True, include_educational_programs=True)), 201
    except ValueError as e:
        db.session.rollback()
        logger.error(f"Validation error creating competency: {e}")
        return jsonify({"error": str(e)}), 400
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Integrity error creating competency: {e.orig}", exc_info=True)
        return jsonify({"error": "Компетенция с таким кодом уже существует для этого типа и ФГОС (если применимо)."}), 409
    except Exception as e:
        db.session.rollback()
        logger.error(f"Неожиданная ошибка сервера при создании компетенции: {e}", exc_info=True)
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
        updated_comp_dict = logic_update_competency(comp_id, data, db.session)
 
        if updated_comp_dict is not None:
            db.session.commit()
            return jsonify(updated_comp_dict), 200
        else:
            db.session.rollback()
            return jsonify({"error": "Компетенция не найдена"}), 404
    except ValueError as ve:
        db.session.rollback()
        logger.warning(f"Update competency route: Validation error for competency {comp_id}: {ve}")
        return jsonify({"error": str(ve)}), 400
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Integrity error updating competency {comp_id}: {e.orig}", exc_info=True)
        return jsonify({"error": "Компетенция с таким кодом уже существует."}), 409
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating competency {comp_id} in route: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось обновить компетенцию: {e}"}), 500


@competencies_matrix_bp.route('/competencies/<int:comp_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_competency_route(comp_id):
    """Delete a competency by ID."""
    try:
        deleted = logic_delete_competency(comp_id, db.session)
 
        if deleted:
            db.session.commit()
            return jsonify({"success": True, "message": "Компетенция успешно удалена"}), 200
        else:
            db.session.rollback()
            return jsonify({"success": False, "error": "Компетенция не найдена"}), 404
    except Exception as e:
        db.session.rollback()
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
        indicator = create_indicator(data, db.session)
        if not indicator:
            db.session.rollback()
            return jsonify({"error": "Не удалось создать индикатор. Проверьте данные или возможно, она уже существует/родительская компетенция не найдена."}), 400
        db.session.commit()
        return jsonify(indicator.to_dict(rules=['-matrix_entries'], include_competency=True)), 201
    except ValueError as e:
        db.session.rollback()
        logger.error(f"Validation error creating indicator: {e}")
        return jsonify({"error": str(e)}), 400
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Integrity error creating indicator: {e.orig}", exc_info=True)
        return jsonify({"error": "Индикатор с таким кодом уже существует для этой компетенции."}), 409
    except Exception as e:
        db.session.rollback()
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
        updated_ind = logic_update_indicator(ind_id, data, db.session)
 
        if updated_ind:
            db.session.commit()
            return jsonify(updated_ind.to_dict(rules=['-matrix_entries'], include_competency=True)), 200
        else:
            db.session.rollback()
            return jsonify({"error": "Индикатор не найден"}), 404
    except ValueError as ve:
        db.session.rollback()
        logger.warning(f"Update indicator route: Validation error for indicator {ind_id}: {ve}")
        return jsonify({"error": str(ve)}), 400
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Integrity error updating indicator {ind_id}: {e.orig}", exc_info=True)
        return jsonify({"error": "Индикатор с таким кодом уже существует для этой компетенции."}), 409
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating indicator {ind_id}: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось обновить индикатор: {e}"}), 500


@competencies_matrix_bp.route('/indicators/<int:ind_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_indicator_route(ind_id):
    """Delete an indicator by ID."""
    try:
        deleted = logic_delete_indicator(ind_id, db.session)
 
        if deleted:
            db.session.commit()
            return jsonify({"success": True, "message": "Индикатор успешно удалена"}), 200
        else:
            db.session.rollback()
            return jsonify({"success": False, "error": "Индикатор не найден"}), 404
    except Exception as e:
        db.session.rollback()
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
        saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=options.get('force_update', False))
        
        if saved_fgos is None:
             db.session.rollback()
             abort(500, description="Ошибка при сохранении данных ФГОС в базу данных.")
        
        db.session.commit()
        return jsonify({
            "success": True,
            "fgos_id": saved_fgos.id,
            "message": "Данные ФГОС успешно сохранены."
        }), 201
 
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Integrity error saving FGOS: {e.orig}", exc_info=True)
        return jsonify({"error": "ФГОС с такими метаданными (направление, номер, дата) уже существует."}), 409
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving FGOS data from file {filename}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при сохранении: {e}")


@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_fgos_route(fgos_id):
    """Удаляет ФГОС и связанные с ним данные."""
    try:
        with db.session.begin():
            deleted = logic_delete_fgos(fgos_id, db.session)
        
        if deleted:
            # db.session.commit() # commit is handled by begin()
            logger.info(f"FGOS with id {fgos_id} deleted successfully.")
            return jsonify({"message": f"ФГОС с ID {fgos_id} успешно удален."}), 200
        else:
            # db.session.rollback() # rollback is handled by begin()
            logger.warning(f"Attempted to delete non-existent FGOS with id {fgos_id}.")
            return jsonify({"error": "ФГОС не найден."}), 404
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting FGOS {fgos_id}: {e}", exc_info=True)
        return jsonify({"error": "Внутренняя ошибка сервера при удалении ФГОС."}), 500

# Professional Standards Endpoints
@competencies_matrix_bp.route('/prof-standards/upload', methods=['POST'])
@login_required
@approved_required
@admin_only
def upload_prof_standard():
    """Upload a Professional Standard file (XML) for parsing."""
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
            logger.error(f"Parse PS upload: Failed processing file {file.filename}. Error: {parse_result.get('error')}. Type: {parse_result.get('error_type')}")
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
                existing_ps_record = get_prof_standard_details(existing_ps.id)
        
        response_data = {
            "status": "success",
            "message": "Файл успешно распознан. Проверьте данные перед сохранением.",
            "parsed_data": parsed_data,
            "filename": file.filename,
            "existing_ps_record": existing_ps_record
        }
        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"Parse PS upload: Unexpected error in /prof-standards/upload for {file.filename}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при обработке файла: {e}")

@competencies_matrix_bp.route('/prof-standards/save', methods=['POST'])
@login_required
@approved_required
@admin_only
def save_prof_standard():
    """Save parsed Professional Standard data to the DB after user confirmation."""
    data = request.get_json()
    parsed_data = data.get('parsed_data')
    filename = data.get('filename')
    options = data.get('options', {})
    
    if not parsed_data or not filename or not parsed_data.get('code'):
        abort(400, description="Некорректные данные для сохранения (отсутствуют parsed_data, filename или код ПС)")

    try:
        saved_ps = save_prof_standard_data(parsed_data, filename, db.session, force_update=options.get('force_update', False))
        
        if saved_ps is None:
             db.session.rollback()
             abort(500, description="Ошибка при сохранении данных профессионального стандарта.")
        
        db.session.commit()
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
        db.session.rollback() 
        logger.error(f"Integrity error saving PS: {e.orig}", exc_info=True)
        return jsonify({"error": "Профессиональный стандарт с таким кодом уже существует."}), 409
    except Exception as e:
        db.session.rollback() 
        logger.error(f"Error saving PS data from file {filename}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при сохранении: {e}")


@competencies_matrix_bp.route('/prof-standards', methods=['GET'])
@login_required
@approved_required
def get_all_profstandards():
    """Get list of all saved Professional Standards."""
    try:
        prof_standards = get_prof_standards_list()
        return jsonify(prof_standards), 200
    except Exception as e:
        logger.error(f"Error in GET /prof-standards: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось получить список профстандартов: {e}"}), 500


@competencies_matrix_bp.route('/prof-standards/<int:ps_id>', methods=['GET'])
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
        logger.error(f"Error in GET /prof-standards/<id>: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось получить профстандарт: {e}"}), 500


@competencies_matrix_bp.route('/prof-standards/<int:ps_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_profstandard(ps_id):
    """Delete a Professional Standard by ID."""
    try:
        deleted = logic_delete_profstandard(ps_id, db.session)
 
        if deleted:
            db.session.commit()
            return jsonify({"success": True, "message": "Профессиональный стандарт успешно удален"}), 200
        else:
            db.session.rollback()
            return jsonify({"success": False, "error": "Профессиональный стандарт не найден"}), 404
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting professional standard {ps_id}: {e}", exc_info=True)
        abort(500, description=f"Не удалось удалить профессиональный стандарт: {e}")

@competencies_matrix_bp.route('/prof-standards/search', methods=['GET'])
@login_required
@approved_required
def search_profstandards_route():
    """
    Searches within professional standards for the given query.
    Filters by specific PS IDs if provided.
    Returns a paginated list of PS details with matching elements highlighted.
    """
    search_query = request.args.get('query', '').strip()
    ps_ids_str = request.args.get('ps_ids') 
    offset_str = request.args.get('offset', '0')
    limit_str = request.args.get('limit', '50') 

    ps_ids = []
    if ps_ids_str:
        try:
            ps_ids = [int(id_val) for id_val in ps_ids_str.split(',') if id_val.isdigit()]
        except ValueError:
            return jsonify({"error": "Неверный формат ps_ids. Ожидается список целых чисел через запятую."}), 400

    qualification_levels_str: Optional[List[str]] = request.args.getlist('qualification_levels')
    qualification_levels: Optional[List[int]] = None
    if qualification_levels_str:
        try:
            qualification_levels = [int(level) for level in qualification_levels_str if level.isdigit()]
            if not qualification_levels: qualification_levels = None 
        except ValueError:
            return jsonify({"error": "Неверный формат qualification_levels. Ожидается список целых чисел."}), 400

    try:
        offset = int(offset_str)
        limit = int(limit_str)
    except ValueError:
        return jsonify({"error": "Неверный формат offset или limit. Ожидаются целые числа."}), 400
    
    if (not search_query or len(search_query) < 2) and not qualification_levels and (ps_ids is None or len(ps_ids) == 0):
        return jsonify({"error": "Поисковый запрос должен содержать минимум 2 символа, либо должны быть выбраны уровни квалификации, либо выбран как минимум один профстандарт."}), 400
    
    if search_query and len(search_query) < 2:
        return jsonify({"error": "Поисковый запрос должен содержать минимум 2 символа."}), 400


    try:
        search_results = logic_search_prof_standards(search_query, ps_ids, offset, limit, qualification_levels)
        return jsonify(search_results), 200
    except ValueError as e:
        logger.warning(f"Search PS route: Validation error: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error in GET /prof-standards/search: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось выполнить поиск по профстандартам: {e}"}), 500


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

@competencies_matrix_bp.route('/prof-standards/export-selected', methods=['POST'])
@login_required
@approved_required
def export_selected_profstandards():
    """
    Exports selected TFs to an Excel file.
    Expects 'opop_id' and 'profStandards' in the JSON body.
    """
    data = request.get_json()
    opop_id = data.get('opopId') 

    if not data or not data.get('profStandards'):
        abort(400, description="Нет данных о выбранных профстандартах для экспорта.")
    
    try:
        excel_bytes = generate_prof_standard_excel_export_logic(data, opop_id)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Перечень_ТФ_{timestamp}.xlsx"
        
        return send_file(
            io.BytesIO(excel_bytes),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        abort(500, description=f"Не удалось выполнить экспорт в Excel: {e}")

@competencies_matrix_bp.route('/pk-generation/correct-name', methods=['POST'])
@login_required
@approved_required
def pk_name_correction_route():
    """Corrects a raw phrase to a proper PK name using NLP."""
    data = request.get_json()
    raw_phrase = data.get('raw_phrase')
    if not raw_phrase:
        abort(400, description="Отсутствует 'raw_phrase' для коррекции.")
    
    try:
        result = handle_pk_name_correction(raw_phrase)
        return jsonify(result), 200
    except ValueError as e:
        logger.error(f"Validation error for PK name correction: {e}")
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e: 
        logger.error(f"NLP error for PK name correction: {e}")
        return jsonify({"error": f"Ошибка NLP: {e}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error in PK name correction route: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при коррекции названия ПК: {e}")

@competencies_matrix_bp.route('/pk-generation/generate-pk-ipk', methods=['POST'])
@login_required
@approved_required
def generate_pk_ipk_route():
    """Generates PK name and IPK formulations using NLP based on selected TF and ZUNs."""
    data = request.get_json()
    selected_tfs_data = data.get('selected_tfs_data')
    selected_zun_elements = data.get('selected_zun_elements')

    if not selected_tfs_data and not selected_zun_elements:
        abort(400, description="Отсутствуют данные для генерации. Необходимо выбрать ТФ или ЗУН-элементы.")
    
    try:
        generated_data = handle_pk_ipk_generation(selected_tfs_data, selected_zun_elements)
        return jsonify(generated_data), 200
    except ValueError as e:
        logger.error(f"Validation error for PK/IPK generation: {e}")
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e: 
        logger.error(f"NLP error for PK/IPK generation: {e}")
        return jsonify({"error": f"Ошибка NLP: {e}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error in PK/IPK generation route: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при генерации ПК/ИПК: {e}")

@competencies_matrix_bp.route('/competencies/batch-create-from-tf', methods=['POST'])
@login_required
@approved_required
@admin_only
def batch_create_competencies_from_tf():
    """
    Пакетное создание ПК и их ИПК на основе массива данных из фронтенда.
    """
    data = request.get_json()
    data_list = data.get('items', []) 
    if not isinstance(data_list, list):
        abort(400, description="Ожидается массив объектов в поле 'items' для создания.")

    try:
        results = batch_create_pk_and_ipk(data_list, db.session)
        db.session.commit()
        return jsonify(results), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error during batch creation: {e}", exc_info=True)
        return jsonify({"error": f"Ошибка пакетного создания: {e}"}), 500

@competencies_matrix_bp.route('/programs/<int:program_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only
def delete_program_route(program_id: int):
    """Удаляет образовательную программу и, опционально, связанные с ней локальные АУПы."""
    delete_cloned_aups = request.args.get('delete_cloned_aups', 'false').lower() == 'true'
    
    try:
        deleted = delete_educational_program(program_id, delete_cloned_aups, db.session)
        if deleted:
            db.session.commit()
            return jsonify({"success": True, "message": "Образовательная программа успешно удалена"}), 200
        else:
            db.session.rollback()
            return jsonify({"success": False, "error": "Образовательная программа не найдена"}), 404
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting program {program_id}: {e}", exc_info=True)
        abort(500, description=f"Не удалось удалить образовательную программу: {e}")