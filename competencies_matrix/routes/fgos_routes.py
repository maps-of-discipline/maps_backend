# filepath: competencies_matrix/routes/fgos_routes.py
from flask import request, jsonify, abort
from .. import competencies_matrix_bp
from typing import Optional, List

from ..logic import (
    parse_fgos_file, save_fgos_data, get_fgos_list, get_fgos_details, delete_fgos,
    process_uk_indicators_disposition_file,
    save_uk_indicators_from_disposition,
)

from auth.logic import login_required, approved_required, admin_only
import logging
from ..models import db
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

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
        return jsonify({"error": "Файл не найден в запросе"}), 400
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Файл не выбран или неверный формат (требуется PDF)"}), 400
    
    try:
        file_bytes = file.read()
        parsed_data = parse_fgos_file(file_bytes, file.filename)
        
        if not parsed_data or not parsed_data.get('metadata'):
             logger.error(f"Upload FGOS: Parsing succeeded but essential metadata missing for {file.filename}.")
             return jsonify({"error": "Не удалось извлечь основные метаданные из файла ФГОС."}), 400

        return jsonify(parsed_data), 200
    except ValueError as e:
        logger.error(f"Upload FGOS: Parsing Error for {file.filename}: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Upload FGOS: Unexpected error processing FGOS upload for {file.filename}: {e}")
        return jsonify({"error": f"Неожиданная ошибка сервера при обработке файла: {e}"}), 500


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
    """Delete a FGOS VO by ID."""
    delete_related_competencies = request.args.get('delete_related_competencies', 'false').lower() == 'true'
 
    try:
        deleted = delete_fgos(fgos_id, db.session, delete_related_competencies=delete_related_competencies)

        if deleted:
            db.session.commit()
            return jsonify({"success": True, "message": "ФГОС успешно удален"}), 200
        else:
            db.session.rollback()
            return jsonify({"success": False, "error": "ФГОС не найден"}), 404
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting FGOS {fgos_id}: {e}", exc_info=True)
        abort(500, description=f"Не удалось удалить ФГОС: {e}")

# --- НОВЫЕ ЭНДПОИНТЫ ДЛЯ РАСПОРЯЖЕНИЙ ---
@competencies_matrix_bp.route('/fgos/uk-indicators/upload', methods=['POST'])
@login_required
@approved_required
@admin_only
def upload_uk_indicators_disposition():
    """Upload and parse a PDF file containing UK indicators disposition."""
    if 'file' not in request.files:
        abort(400, description="Файл не найден в запросе.")
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        abort(400, description="Файл не выбран или неверный формат (требуется PDF).")
    
    education_level = request.args.get('education_level')
    if not education_level:
        abort(400, description="Не указан уровень образования (education_level) для распоряжения.")

    try:
        file_bytes = file.read()
        parsed_data = process_uk_indicators_disposition_file(file_bytes, file.filename, education_level)
        
        if not parsed_data or not parsed_data.get('disposition_metadata'):
            logger.error(f"Upload UK Disposition: Parsing succeeded but essential metadata missing for {file.filename}.")
            abort(400, description="Не удалось извлечь основные метаданные из файла распоряжения.")

        return jsonify(parsed_data), 200
    except ValueError as e:
        logger.error(f"Upload UK Disposition: Parsing Error for {file.filename}: {e}", exc_info=True)
        abort(400, description=f"Ошибка парсинга файла распоряжения: {e}")
    except Exception as e:
        logger.error(f"Upload UK Disposition: Unexpected error processing file {file.filename}: {e}", exc_info=True)
        abort(500, description=f"Неожиданная ошибка сервера при обработке файла распоряжения: {e}")

@competencies_matrix_bp.route('/fgos/uk-indicators/save', methods=['POST'])
@login_required
@approved_required
@admin_only
def save_uk_indicators_disposition():
    """Save parsed UK indicators from disposition data to the DB."""
    data = request.get_json()
    parsed_disposition_data = data.get('parsed_data')
    filename = data.get('filename')
    fgos_ids = data.get('fgos_ids') 
    options = data.get('options', {})

    if not all([parsed_disposition_data, filename, fgos_ids]):
        abort(400, description="Некорректные данные для сохранения (отсутствуют parsed_data, filename или fgos_ids).")
    
    if not isinstance(fgos_ids, list) or not fgos_ids:
        abort(400, description="fgos_ids должен быть непустым списком.")

    try:
        save_result = save_uk_indicators_from_disposition(
            parsed_disposition_data=parsed_disposition_data,
            filename=filename,
            session=db.session,
            fgos_ids=fgos_ids,
            force_update_uk=options.get('force_update_uk', False),
            resolutions=options.get('resolutions')
        )
        db.session.commit()
        return jsonify({"success": True, "message": "Индикаторы УК успешно сохранены/обновлены.", "summary": save_result.get('summary')}), 201
    except ValueError as e:
        db.session.rollback()
        logger.error(f"Validation error saving UK indicators from disposition: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Integrity error saving UK indicators from disposition: {e.orig}", exc_info=True)
        return jsonify({"error": "Ошибка целостности данных при сохранении индикаторов УК. Возможно, дублирующийся код."}), 409
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error saving UK indicators from disposition: {e}", exc_info=True)
        return jsonify({"error": f"Неожиданная ошибка сервера при сохранении индикаторов УК: {e}"}), 500