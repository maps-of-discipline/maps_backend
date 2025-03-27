import io
import json
import os
from collections import defaultdict
from itertools import chain
from pprint import pprint

from flask import Blueprint, make_response, jsonify, request, send_file

from app import cache

from auth.logic import login_required, aup_require, verify_jwt_token, admin_only
from auth.models import Mode, Users
from maps.logic.print_excel import saveMap, get_aup_data_excel
from maps.logic.save_excel_data import save_excel_files
from maps.logic.save_into_bd import update_fields, create_changes_revision
from maps.logic.take_from_bd import control_type_r, create_json
from maps.logic.upload_xml import create_xml
from maps.models import *
from utils.logging import logger
from datetime import datetime

aup_info_router = Blueprint("aup_info_router", __name__, url_prefix="/api", static_folder="static")

@aup_info_router.route("/aup-info/<string:aup>", methods=['POST'])
def aup_copy(aup: str | None):
    aup_record: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aup_record:
        return jsonify({"status": "not found"}), 404
    
    match dict(request.args):
        case {"copy_with_num": new_aup_num}:
            if AupInfo.query.filter_by(num_aup=new_aup_num).first():
                return jsonify({"status": "already exists"}), 400

            aup_record.copy(new_aup_num)
            return jsonify({"status": "ok", "aup_num": new_aup_num})
        case _:
            return jsonify({"result": "failed"}), 400


@aup_info_router.route("/aup-info/<string:aup>", methods=['PATCH'])
def aup_change(aup: str | None):
    aup_record: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aup_record:
        return jsonify({"status": "not found"}), 404
    
    data = request.get_json()

    for field, value in data.items():
        if field in AupInfo.__dict__:
            setattr(aup_record, field, value)

    db.session.add(aup_record)

    try:
        db.session.commit()
    except Exception as ex:
        print(ex)
        db.session.rollback()
        return jsonify({"status": "failed", "aup_num": aup_record.num_aup}), 403

    return jsonify({"status": "ok", "aup_num": aup_record.num_aup}), 200    
    
@aup_info_router.route("/aup-info/<string:aup>", methods=['DELETE'])
def aup_delete(aup: str | None):
    aup_record: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aup_record:
        return jsonify({"status": "not found"}), 404
    
    db.session.delete(aup_record)
    db.session.commit()
    return jsonify({"status": "ok"})
    

@aup_info_router.route('/aup-info/<string:aup>/mark_deleted', methods=['POST'])
# @aup_require(request)
def mark_aup_deleted(aup: str | None):
    aup_record: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aup_record:
        return jsonify({"status": "not found"}), 404

    if aup_record.is_delete == 1:
        return jsonify({"status": "Карта уже в корзине"}), 200
    else:
        aup_record.is_delete = 1
        aup_record.date_delete = datetime.now()

    db.session.add(aup_record)
    try:
        db.session.commit()
    except Exception as ex:
        print(ex)
        db.session.rollback()
        return jsonify({"status": "failed", "aup_num": aup_record.num_aup}), 403

    return jsonify({"status": "ok", "aup_num": aup_record.num_aup}), 200


@aup_info_router.route("/aup-info/<string:aup>/confirm_deletion", methods=['DELETE'])
@admin_only(request)
def confirm_aup_deletion(aup: str | None):
    aup_record: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aup_record:
        return jsonify({"status": "not found"}), 404
    if aup_record.is_delete == 1:
        db.session.delete(aup_record)
    else:
        return jsonify({"status": "aup not mark_deleted"}), 200
    
    try:
        db.session.commit()
    except Exception as ex:
        print(ex)
        db.session.rollback()
        return jsonify({"status": "failed", "aup_num": aup_record.num_aup}), 403

    return jsonify({"status": "ok"}), 200

@aup_info_router.route("/aup-info/all_deleted_aup", methods=["GET"])
def all_deleted_aup():
    aups = db.session.query(AupInfo.id_aup, AupInfo.num_aup, AupInfo.date_delete).filter(AupInfo.is_delete == 1).all()
    
    if aups:
        result = [{"id_aup": aup.id_aup, "num_aup": aup.num_aup, "time_delete": aup.date_delete} for aup in aups]
        return make_response(jsonify(result), 200)
    else:
        return make_response(jsonify({"message": "В корзине нет удаленных АУПов"}), 200)