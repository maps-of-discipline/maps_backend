# filepath: competencies_matrix/routes/prof_standards_routes.py
from flask import request, jsonify, abort, send_file
from .. import competencies_matrix_bp
from typing import Optional, List

from ..logic import (
    handle_prof_standard_upload_parsing,
    save_prof_standard_data, 
    get_prof_standards_list, get_prof_standard_details,
    delete_prof_standard as logic_delete_profstandard,
    search_prof_standards as logic_search_prof_standards,
    generate_prof_standard_excel_export_logic,
)

from auth.logic import login_required, approved_required, admin_only
import logging, datetime, io
from ..models import db, ProfStandard 
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

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


@competencies_matrix_bp.route('/profstandards', methods=['GET'])
@login_required
@approved_required
def get_all_profstandards():
    """Get list of all saved Professional Standards."""
    try:
        prof_standards = get_prof_standards_list()
        return jsonify(prof_standards), 200
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

@competencies_matrix_bp.route('/profstandards/search', methods=['GET'])
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
        logger.error(f"Error in GET /profstandards/search: {e}", exc_info=True)
        return jsonify({"error": f"Не удалось выполнить поиск по профстандартам: {e}"}), 500