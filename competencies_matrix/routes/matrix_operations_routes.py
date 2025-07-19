# filepath: competencies_matrix/routes/matrix_operations_routes.py
from flask import request, jsonify, abort
from .. import competencies_matrix_bp
from typing import Optional, List

from ..logic import (
    get_matrix_for_aup, update_matrix_link
)

from auth.logic import login_required, approved_required
import logging
from ..models import db
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

# Competency Matrix Endpoints
@competencies_matrix_bp.route('/matrix/<string:aup_num>', methods=['GET'])
@login_required
@approved_required
def get_matrix(aup_num: str):
    """
    (ИЗМЕНЕНО) Получает данные для матрицы компетенций.
    Обрабатывает статус 'not_imported', если АУП не найден локально.
    """
    logger.info(f"Received GET request for matrix for AUP num: {aup_num}")
    
    try:
        matrix_data = get_matrix_for_aup(aup_num)

        if matrix_data.get("status") == "not_imported":
            logger.warning(f"АУП '{aup_num}' не импортирован. Отправка ответа 404.")
            return jsonify({"error": matrix_data["error"]}), 404
            
        if matrix_data.get("status") == "error":
            logger.error(f"Ошибка при получении матрицы для АУП '{aup_num}': {matrix_data['error']}")
            return jsonify({"error": matrix_data["error"]}), 500

        return jsonify(matrix_data), 200
        
    except Exception as e:
        logger.error(f"Error in GET /matrix/{aup_num}: {e}", exc_info=True)
        return jsonify({"error": "Внутренняя ошибка сервера при получении матрицы."}), 500


@competencies_matrix_bp.route('/matrix/link', methods=['POST', 'DELETE'])
@login_required
@approved_required
def manage_matrix_link():
    """(ИСПРАВЛЕНО) Создает или удаляет связь 'Дисциплина-Индикатор'."""
    data = request.get_json()
    if not data or 'aup_data_id' not in data or 'indicator_id' not in data:
        return jsonify({"error": "Отсутствуют обязательные поля: aup_data_id, indicator_id"}), 400

    aup_data_id = data['aup_data_id']
    indicator_id = data['indicator_id']
    is_creating = (request.method == 'POST')
 
    try:
        result = update_matrix_link(aup_data_id, indicator_id, create=is_creating)
        
        status_code = 201 if result['status'] == 'created' else 200
        return jsonify(result), status_code

    except (ValueError, IntegrityError) as e:
        logger.error(f"Ошибка целостности данных при обновлении матрицы: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        logger.error(f"Ошибка сервера при обновлении матрицы: {e}", exc_info=True)
        return jsonify({"error": "Внутренняя ошибка сервера."}), 500