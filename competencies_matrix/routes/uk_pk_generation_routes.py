# filepath: competencies_matrix/routes/uk_pk_generation_routes.py
from flask import request, jsonify, abort
from .. import competencies_matrix_bp
from typing import Optional, List

from ..logic import (
    handle_pk_name_correction,
    handle_pk_ipk_generation,
    batch_create_pk_and_ipk,
)

from auth.logic import login_required, approved_required, admin_only
import logging
from ..models import db
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

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
    """
    Генерирует ПК и ИПК с использованием NLP на основе списка ТФ и их ЗУН.
    Ожидает в теле запроса JSON-объект с ключом 'items', который является списком.
    """
    data = request.get_json()
    batch_tfs_for_generation = data.get('items')

    if not batch_tfs_for_generation or not isinstance(batch_tfs_for_generation, list):
        abort(400, description="Некорректные данные для генерации. Ожидается JSON-объект с полем 'items' (список ТФ).")
    
    try:
        generated_data = handle_pk_ipk_generation(batch_tfs_for_generation)
        return jsonify(generated_data), 200
    except ValueError as e:
        logger.error(f"Validation error for PK/IPK generation: {e}")
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        logger.error(f"NLP error for PK/IPK generation: {e}")
        return jsonify({"error": f"Ошибка NLP: {e}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error in PK/IPK generation route: {e}", exc_info=True)
        return jsonify({"error": f"Неожиданная ошибка сервера при генерации ПК/ИПК: {e}"}), 500

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