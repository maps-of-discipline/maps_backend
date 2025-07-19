# filepath: competencies_matrix/routes/competencies_indicators_routes.py
from flask import request, jsonify, abort
from .. import competencies_matrix_bp
from typing import Optional, List

from ..logic import (
    create_competency, create_indicator,
    get_all_competencies as logic_get_all_competencies,
    get_all_indicators as logic_get_all_indicators,
    update_competency as logic_update_competency,
    delete_competency as logic_delete_competency,
    update_indicator as logic_update_indicator,
    delete_indicator as logic_delete_indicator,
)

from auth.logic import login_required, approved_required, admin_only
import logging
from ..models import db, Competency, Indicator, CompetencyType
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

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