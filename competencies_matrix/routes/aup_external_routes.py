# filepath: competencies_matrix/routes/aup_external_routes.py
from flask import request, jsonify, abort
from .. import competencies_matrix_bp
from typing import Optional, List

from ..logic import (
    get_external_aups_list, get_external_aup_disciplines,
)

from auth.logic import login_required, approved_required
import logging
from ..models import db
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

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