from flask import Blueprint, make_response, jsonify, request


from auth.logic import admin_only
from datetime import datetime

from maps.models import db, AupInfo, NameOP

aup_info_router = Blueprint(
    "aup_info", __name__, url_prefix="/aup-info", static_folder="../static"
)


@aup_info_router.route("/<string:aup>", methods=["POST"])
def aup_copy(aup: str | None):
    aup_record: AupInfo | None = AupInfo.query.filter_by(num_aup=aup).first()

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


@aup_info_router.route("/<string:aup>", methods=["PATCH"])
def aup_change(aup: str | None):
    aup_record: AupInfo | None = AupInfo.query.filter_by(num_aup=aup).first()
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


@aup_info_router.route("/<string:aup>", methods=["DELETE"])
def aup_delete(aup: str | None):
    aup_record: AupInfo | None = AupInfo.query.filter_by(num_aup=aup).first()
    if not aup_record:
        return jsonify({"status": "not found"}), 404

    db.session.delete(aup_record)
    db.session.commit()
    return jsonify({"status": "ok"})


@aup_info_router.route("/<string:aup>/mark-deleted", methods=["POST"])
def mark_aup_deleted(aup: str):
    """
    Принимает текущий статус is_delete и в зависимстости от него устанавливает новое значение.
    """
    data = request.get_json()
    if not data or "is_delete" not in data:
        return jsonify({"status": "is_delete parameter is required"}), 400
    is_delete = data["is_delete"]

    aup_record: AupInfo | None = AupInfo.query.filter_by(num_aup=str(aup)).first()
    if not aup_record:
        return jsonify({"status": "not found"}), 404

    aup_record.is_delete = not bool(is_delete)
    aup_record.date_delete = datetime.now() if not bool(is_delete) else None
    db.session.add(aup_record)

    try:
        db.session.commit()
    except Exception as ex:
        print(ex)
        db.session.rollback()
        return jsonify({"status": "failed", "aup_num": aup_record.num_aup}), 403

    return (
        jsonify(
            {
                "status": "ok",
                "aup_num": aup_record.num_aup,
                "is_delete": bool(aup_record.is_delete),
            }
        ),
        200,
    )


@aup_info_router.route("/<string:aup>/confirm_deletion", methods=["DELETE"])
@admin_only
def confirm_aup_deletion(aup: str | None):
    aup_record: AupInfo | None = AupInfo.query.filter_by(num_aup=aup).first()

    if not aup_record:
        return jsonify({"status": "not found"}), 404

    if aup_record.is_delete == 1:
        db.session.delete(aup_record)
    else:
        return jsonify({"status": "aup not mark_deleted"}), 400

    try:
        db.session.commit()
    except Exception as ex:
        print(ex)
        db.session.rollback()
        return jsonify({"status": "failed", "aup_num": aup_record.num_aup}), 403

    return jsonify({"status": "ok"}), 200


@aup_info_router.route("/all_deleted_aup", methods=["GET"])
def all_deleted_aup():
    aups = (
        db.session.query(
            AupInfo.id_aup,
            AupInfo.num_aup,
            AupInfo.is_delete,
            AupInfo.year_beg,
            AupInfo.date_delete,
            AupInfo.id_faculty,
            NameOP.name_spec,
        )
        .join(NameOP, NameOP.id_spec == AupInfo.id_spec)
        .filter(AupInfo.is_delete == 1)
        .all()
    )
    result = [
        {
            "id_aup": aup.id_aup,
            "num_aup": aup.num_aup,
            "time_delete": aup.date_delete,
            "faculty_id": aup.id_faculty,
            "is_delete": aup.is_delete,
            "year_beg": aup.year_beg,
            "name_spec": aup.name_spec,
        }
        for aup in aups
    ]
    return make_response(jsonify(result), 200)
