# filepath: competencies_matrix/routes/educational_programs_routes.py
from flask import request, jsonify, abort
from .. import competencies_matrix_bp
from typing import Optional, List

from ..logic import (
    get_educational_programs_list, get_program_details,
    create_educational_program,
    update_educational_program as logic_update_educational_program,
    delete_educational_program,
    import_aup_from_external_db,
    check_aup_version
)

from auth.logic import login_required, approved_required, admin_only
import logging
from ..models import db
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
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Integrity error creating program: {e.orig}", exc_info=True)
        return jsonify({"error": "Образовательная программа с такими параметрами (код, профиль, год, форма) уже существует."}), 409
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error creating program: {e}", exc_info=True)
        return jsonify({"error": f"Неожиданная ошибка сервера при создании образовательной программы."}), 500

@competencies_matrix_bp.route('/programs/<int:program_id>', methods=['PATCH'])
@login_required
@approved_required
@admin_only
def update_program_route(program_id: int):
    """Обновляет существующую образовательную программу по ID."""
    data = request.get_json()
    if not data:
        abort(400, description="Отсутствуют данные для обновления.")

    try:
        updated_program_dict = logic_update_educational_program(program_id, data, db.session)
        
        if updated_program_dict:
            db.session.commit()
            return jsonify(updated_program_dict), 200
        else:
            db.session.rollback()
            return jsonify({"error": "Образовательная программа не найдена."}), 404
            
    except ValueError as e:
        db.session.rollback()
        logger.error(f"Validation error updating program {program_id}: {e}")
        return jsonify({"error": str(e)}), 400
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Integrity error updating program {program_id}: {e.orig}", exc_info=True)
        return jsonify({"error": "Образовательная программа с такими параметрами уже существует."}), 409
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error updating program {program_id}: {e}", exc_info=True)
        return jsonify({"error": f"Неожиданная ошибка сервера при обновлении образовательной программы."}), 500


@competencies_matrix_bp.route('/programs/<int:program_id>', methods=['GET'])
@login_required
@approved_required
def get_program(program_id):
    details = get_program_details(program_id)
    if not details:
        return jsonify({"error": "Образовательная программа не найдена"}), 404
    return jsonify(details)

@competencies_matrix_bp.route('/programs/<int:program_id>/check-aup-version', methods=['GET'])
@login_required
@approved_required
def check_aup_version_route(program_id: int):
    """
    Проверяет актуальность основного АУП для ОПОП.
    """
    try:
        result = check_aup_version(program_id, db.session)
        return jsonify(result), 200
    except RuntimeError as e:
        logger.error(f"Ошибка выполнения при проверке версии АУП: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Ошибка при проверке версии АУП: {e}"}), 500
    except Exception as e:
        logger.error(f"Неожиданная ошибка в роуте проверки версии АУП: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Внутренняя ошибка сервера при проверке версии АУП."}), 500


@competencies_matrix_bp.route('/programs/<int:program_id>/import-aup/<string:aup_num>', methods=['POST'])
@login_required
@approved_required
@admin_only
def import_aup_to_program(program_id: int, aup_num: str):
    """
    Импортирует АУП из внешней БД и привязывает его к указанной образовательной программе.
    """
    try:
        result = import_aup_from_external_db(aup_num, program_id, db.session)
        
        if result.get("success"):
            return jsonify(result), 201
        else:
            return jsonify({"error": result.get("message", "Неизвестная ошибка импорта")}), 500
    except FileNotFoundError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Неожиданная ошибка в роуте импорта АУП: {e}", exc_info=True)
        return jsonify({"error": "Внутренняя ошибка сервера при импорте АУП."}), 500

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