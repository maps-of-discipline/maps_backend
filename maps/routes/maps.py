import io
import json
import os
from collections import defaultdict
from itertools import chain
from pprint import pprint

from flask import Blueprint, make_response, jsonify, request, send_file

from app import cache

from auth.logic import login_required, aup_require, verify_jwt_token
from auth.models import Mode
from maps.logic.print_excel import saveMap, get_aup_data_excel
from maps.logic.save_excel_data import save_excel_files
from maps.logic.save_into_bd import update_fields, create_changes_revision
from maps.logic.take_from_bd import control_type_r, create_json
from maps.logic.upload_xml import create_xml
from maps.models import *
from utils.logging import logger

maps = Blueprint("maps", __name__, static_folder="../static")

if not os.path.exists(maps.static_folder + "/temp"):
    os.makedirs(maps.static_folder + "/temp", exist_ok=True)


@maps.route("/map/<string:aup>")
def getMap(aup):
    json = create_json(aup)
    if not json:
        return make_response(jsonify({"error": "not found"}), 404)

    return make_response(jsonify(json), 200)


@maps.route("/save/<string:aup>", methods=["POST"])
@login_required(request)
@aup_require(request)
def save_map(aup):
    data = request.get_json()

    aup_info: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    aup_data_id_map = {el.id: el for el in aup_info.aup_data}

    disciplines = {el.title: el.id for el in SprDiscipline.query.all()}

    changes = []
    for discipline in data:
        for load in chain(*discipline["type"].values()):
            if "id" not in load:
                aup_data = AupData()
                aup_data.id_discipline = disciplines[discipline["discipline"]]
                aup_info.aup_data.append(aup_data)
            else:
                aup_data = aup_data_id_map.pop(load["id"])

            changes.extend(update_fields(aup_data, discipline, load))

            if changes:
                db.session.add(aup_data)

    if changes:
        payload, verify_result = verify_jwt_token(request.headers["Authorization"])
        create_changes_revision(payload["user_id"], aup_info.id_aup, changes)

    if aup_data_id_map.keys():
        for el in AupData.query.filter(AupData.id.in_(aup_data_id_map.keys())):
            db.session.delete(el)

    db.session.commit()
    return make_response(jsonify(create_json(aup)), 200)


@maps.route("/meta-info", methods=["GET"])
def get_id_edizm():
    measure_coefs = [
        {"id_edizm": 1, "kratn": 2, "value": "Часы", "coef": 0.0625},
        {
            "id_edizm": 2,
            "kratn": 1,
            "value": "Недели",
            "coef": 1.5,
        },
    ]

    modes = []
    for mode in Mode.query.all():
        mode: Mode
        roles = [
            {
                "id": role.id_role,
                "title": role.name_role,
            }
            for role in mode.roles
        ]

        modes.append(
            {"id": mode.id, "title": mode.title, "action": mode.action, "roles": roles}
        )

    return make_response(
        jsonify(
            {
                "measure_coefs": measure_coefs,
                "modes": modes,
            }
        ),
        200,
    )


@maps.route("/upload", methods=["POST"])
# @timeit
# @login_required(request)
def upload():
    logger.info("/upload - processing files uploading")
    options = dict(json.loads(request.form["options"]))
    logger.debug(f"/upload - options: {options}")
    res = save_excel_files(request.files, options)
    return jsonify(res), 200


@maps.route("/save_excel/<string:aup>", methods=["GET"])
def save_excel(aup):
    try:
        paper_size = json.loads(request.form["paper_size"])
        orientation = json.loads(request.form["orientation"])
        load = False
        control = False
    except:
        paper_size = "3"
        orientation = "land"
        load = False
        control = False
    filename = saveMap(aup, maps.static_folder, paper_size, orientation, control, load)

    # Upload xlxs file in memory and delete file from storage
    return_data = io.BytesIO()
    with open(filename, "rb") as fo:
        return_data.write(fo.read())

    # after writing, cursor will be at last byte, so move it to start
    return_data.seek(0)

    os.remove(filename)

    response = make_response(send_file(return_data, download_name=filename))
    response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
    return response


@maps.route("/getGroups", methods=["GET"])
def get_colors():
    q = Groups.query.all()
    l = list()
    for row in q:
        d = dict()
        d["id"] = row.id_group
        d["name"] = row.name_group
        d["color"] = row.color
        l.append(d)
    return l


@maps.route("/get-modules", methods=["GET"])
def get_modules():
    modules = D_Modules.query.all()
    res = []
    for module in modules:
        module_as_dict: dict = module.as_dict()
        module_as_dict["name"] = module_as_dict["title"]
        module_as_dict.pop("title")
        res.append(module_as_dict)
    return jsonify(res)


@maps.route("/add-module", methods=["POST"])
@login_required(request)
@aup_require(request)
def add_module():
    module = request.get_json()
    if not module["name"]:
        return (
            jsonify(
                {"result": "error", "message": 'поле "name" не должно быть пустым'}
            ),
            400,
        )

    new_module = D_Modules()
    new_module.title = module["name"]
    new_module.color = module["color"]

    db.session.add(new_module)
    db.session.commit()

    return (
        jsonify(
            {"id": new_module.id, "name": new_module.title, "color": new_module.color}
        ),
        200,
    )


@maps.route("/modules/<int:id>", methods=["PUT", "DELETE"])
@login_required(request)
@aup_require(request)
def edit_or_delete_module(id: int):
    module = D_Modules.query.get(id)
    if not module:
        return jsonify({"result": "error", "message": "not found"}), 404

    if request.method == "DELETE":
        for el in AupData.query.filter_by(id_module=module.id).all():
            el.id_module = 19
            db.session.add(el)

        db.session.delete(module)
        db.session.commit()
        return jsonify({"result": "ok"}), 200

    elif request.method == "PUT":
        data = request.get_json()
        module.title = data["name"]
        module.color = data["color"]

        db.session.add(module)
        db.session.commit()

        return jsonify(module.as_dict()), 200


@maps.route("/getAllMaps")
def getAllMaps():
    specialization_names = {}
    for el in NameOP.query.all():
        el: NameOP
        specialization_names[el.id_spec] = {
            "name_spec": el.name_spec,
            "okco_code": el.okco.program_code,
            "okco_name": el.okco.name_okco,
        }

    faculties = SprFaculty.query.all()
    li = []

    # NameOP - spr_name_op
    # SprOKCO - sspr_okco
    #

    for fac in faculties:
        fac: SprFaculty
        maps = []
        for row in fac.aup_infos:
            row: AupInfo
            specialization = specialization_names[row.id_spec]
            maps.append(
                {
                    "name": specialization["name_spec"],
                    "okco_code": specialization["okco_code"],
                    "okco_name": specialization["okco_name"],
                    "code": row.num_aup,
                    "year": row.year_beg,
                    "form_educ": row.id_form,
                    "is_delete": bool(row.is_delete)
                    if row.is_delete is not None
                    else False,
                }
            )

        li.append(
            {
                "faculty_id": fac.id_faculty,
                "faculty_name": fac.name_faculty,
                "admin_only": fac.admin_only == 1,
                "directions": maps,
            }
        )
    return jsonify(li)


@maps.route("/add-group", methods=["POST"])
@login_required(request)
@aup_require(request)
def AddNewGroup():
    request_data = request.get_json()
    if request_data["name"] == "":
        return make_response(jsonify("Введите название группировки"), 400)
    data = Groups(name_group=request_data["name"], color=request_data["color"])
    db.session.add(data)
    db.session.commit()
    d = dict()
    d["id"] = data.id_group
    d["name"] = data.name_group
    d["name"] = data.name_group
    d["color"] = data.color
    return make_response(jsonify(d), 200)


@maps.route("/delete-group", methods=["POST"])
@login_required(request)
@aup_require(request)
def DeleteGroup():
    request_data = request.get_json()
    d = AupData.query.filter_by(id_group=request_data["id"]).all()
    for row in d:
        row.id_group = 1
        db.session.add(row)
    db.session.commit()
    Groups.query.filter_by(id_group=request_data["id"]).delete()
    db.session.commit()
    return make_response(jsonify("OK"), 200)


@maps.route("/get-group-by-aup/<string:aup>", methods=["GET"])
def GetGroupByAup(aup):
    aupId = AupInfo.query.filter_by(num_aup=aup).first().id_aup
    aupData = AupData.query.filter_by(id_aup=aupId).all()

    groups_id = set()
    for elem in aupData:
        groups_id.add(elem.id_group)

    groups = []
    for g in Groups.query.filter(Groups.id_group.in_(groups_id)).all():
        groups.append(
            {
                "id": g.id_group,
                "name": g.name_group,
                "color": g.color,
            }
        )
    return make_response(jsonify(groups), 200)


@maps.route("/get-modules-by-aup/<string:aup>", methods=["GET"])
def GetModulesByAup(aup):
    aup_info: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()

    modules_set = set()
    for elem in aup_info.aup_data:
        modules_set.add(elem.module)

    modules = []
    for m in modules_set:
        if m.title != "Без названия":
            modules.append(
                {
                    "id": m.id,
                    "name": m.title,
                    "color": m.color,
                }
            )
    return make_response(jsonify(modules), 200)


@maps.route("/update-group", methods=["POST"])
@login_required(request)
@aup_require(request)
def UpdateGroup():
    request_data = request.get_json()
    gr = Groups.query.filter_by(id_group=request_data["id"]).first()
    gr.name_group = request_data["name"]
    gr.color = request_data["color"]
    db.session.add(gr)
    db.session.commit()
    return make_response(jsonify("OK"), 200)


@maps.route("/getControlTypes")
def getControlTypes():
    control_types = []
    for k, v in control_type_r.items():
        is_control = v == "Экзамен" or v == "Зачет" or v == "Дифференцированный зачет"
        is_course = v == "Курсовой проект" or v == "Курсовая работа"
        control_types.append(
            {"id": k, "name": v, "is_control": is_control, "is_course": is_course}
        )

    return make_response(jsonify(control_types), 200)


@maps.route("/test")
def test():
    return jsonify(), 200


@maps.route("/upload-xml/<string:aup>")
def upload_xml(aup):
    filename = create_xml(aup)

    data = io.BytesIO()
    with open(filename, "rb") as res:
        data.write(res.read())
    data.seek(0)

    return send_file(data, download_name="sample.txt")


@maps.route("/exprort-aup/<string:aup>", methods=["GET"])
def export_aup_excel(aup: str):
    file, filename = get_aup_data_excel(aup)
    file.seek(0)

    return send_file(
        file,
        download_name=f"{filename}.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@maps.route("/weeks/<string:aup>/save", methods=["POST"])
@login_required(request)
@aup_require(request)
def save_weeks(aup: str):
    data: dict = dict(request.get_json())
    data = {int(k): int(v) for k, v in data.items()}

    aup_info = AupInfo.query.filter_by(num_aup=aup).first()
    for week in aup_info.weeks:
        if week.period_id in data:
            amount = data.pop(week.period_id)
            if amount != week.amount:
                week.amount = amount
                db.session.add(week)

    for period_id, week_amount in data.items():
        week = Weeks(period_id=period_id, aup_id=aup_info.id_aup, amount=week_amount)
        db.session.add(week)

    db.session.commit()
    return {"status": "ok"}


@maps.route("/weeks/<string:aup>")
def get_weeks(aup: str):
    aup_info = AupInfo.query.filter_by(num_aup=aup).first()
    return {el.period_id: el.amount for el in aup_info.weeks}


@maps.route("/revisions/<string:num_aup>", methods=["GET"])
def get_revisions_by_aup(num_aup):
    aup = db.session.query(AupInfo).filter_by(num_aup=num_aup).first()

    if not aup:
        return jsonify({"error": "Учебный план с таким num_aup не найден"}), 404

    revisions = Revision.query.filter_by(aup_id=aup.id_aup).all()

    revisions_data = []
    for revision in revisions:
        revision_data = {
            "id": revision.id,
            "title": revision.title,
            "date": revision.date,
            "isActual": revision.isActual,
            "user_id": revision.user_id,
            "aup_id": revision.aup_id,
        }
        revisions_data.append(revision_data)

    return jsonify(revisions_data)


@maps.route("/revisions/revert/<int:id_revision>", methods=["POST"])
def revert_revision(id_revision):
    current_revision = db.session.query(Revision).filter_by(id=id_revision).first()

    if not current_revision:
        return jsonify({"error": "Ревизия не найдена"}), 404

    subsequent_revisions = (
        db.session.query(Revision)
        .filter(Revision.id >= id_revision, Revision.aup_id == current_revision.aup_id)
        .order_by(Revision.id.desc())
        .all()
    )

    # получаем сразу всю AupData чтобы не делать лишних запросов
    aup_data_mapper = {
        el.id: el
        for el in AupData.query.filter(AupData.id_aup == current_revision.aup_id).all()
    }

    to_delete = []

    for revision in subsequent_revisions:
        for change in revision.logs:
            change: ChangeLog

            aup_data_row = aup_data_mapper[change.row_id]
            setattr(aup_data_row, change.field, change.old)
            db.session.add(aup_data_row)

        to_delete.append(revision.id)

    current_revision = (
        db.session.query(Revision)
        .filter(
            Revision.id < current_revision.id,
            Revision.aup_id == current_revision.aup_id,
        )
        .order_by(Revision.id.desc())
        .first()
    )

    if current_revision:
        current_revision.isActual = True
        db.session.add(current_revision)

    db.session.query(Revision).filter(Revision.id.in_(to_delete)).delete()
    db.session.commit()
    return jsonify({"result": "ok"}), 200


@maps.get("/faculties")
def get_faculties():
    faculties: list[SprFaculty] = SprFaculty.query.all()
    res = [el.as_dict() for el in faculties]
    return jsonify(res), 200


@maps.get("/departments")
def get_departments():
    departments: list[Department] = Department.query.all()
    res = [el.as_dict() for el in departments]
    return jsonify(res), 200


@maps.get("/degree-educations")
def get_degree_educations():
    degree_educations: list[SprDegreeEducation] = SprDegreeEducation.query.all()
    res = [el.as_dict() for el in degree_educations]
    return jsonify(res), 200


@maps.get("/op-names")
def get_op_names():
    names: list[NameOP] = NameOP.query.all()
    res = [el.as_dict() for el in names]
    return jsonify(res), 200


@maps.route("/reports/save-choosen-displines", methods=["POST"])
@login_required(request)
@aup_require(request)
def save_choosen_displines():
    data: dict = dict(request.get_json())
    data["aup_id"] = int(data["aup_id"])
    data["disciplines"] = [int(i) for i in data["disciplines"]]
    data["control_types"] = [int(i) for i in data["control_types"]]

    query = (
        db.session.query(AupData)
        .filter(
            AupData.id == data["aup_id"],
            AupData.id_discipline.in_(data["disciplines"]),
            AupData.id_type_control.in_(data["control_types"]),
        )
        .first()
    )
    if query:
        query.used_for_report = True
    db.session.commit()
    return jsonify(data), 200


@maps.route("/practical_training_report", methods=["GET"])
@login_required(request)
@cache.cached(timeout=0)
def data_monitoring_of_practical_training():
    query = (
        db.session.query(
            AupInfo.id_aup,
            AupInfo.num_aup,
            AupInfo.year_beg,
            AupInfo.id_faculty,
            SprFaculty.name_faculty,
            SprOKCO.program_code,
            SprOKCO.name_okco,
            NameOP.name_spec,
            AupInfo.id_form,
        )
        .join(NameOP, NameOP.id_spec == AupInfo.id_spec)
        .join(SprOKCO, SprOKCO.program_code == NameOP.program_code)
        .join(SprFaculty, SprFaculty.id_faculty == AupInfo.id_faculty)
        .group_by(AupInfo.id_aup)
        .order_by(AupInfo.id_aup)
        .all()
    )

    aup_data = AupData.query.filter(AupData.id_type_control.in_([6, 7, 11, 12, 13]))
    aup_data_dict = {
        el.id: [
            el.id_aup,
            (
                int(el.amount / 3600) if el.id_edizm == 1 else int(el.amount * 0.015)
            ),  # Вычичисляю ЗЕТ для всех AupData
            el.id_type_control in [11, 12, 13],
        ]  # Проверка на Практику
        for el in aup_data
    }

    data = [
        {
            "id_aup": el.id_aup,
            "num_aup": el.num_aup,
            "year_beg": el.year_beg,
            "faculty": el.name_faculty,
            "program_code": el.program_code,
            "name_okco": el.name_okco,
            "name_spec": el.name_spec,
            "load_with_practice": 0,
            "load_without": 0,
            "form": (
                "Очная"
                if el.id_form == 1
                else (
                    "Очно-заочная"
                    if el.id_form == 2
                    else "Заочная"
                    if el.id_form == 3
                    else None
                )
            ),
        }
        for el in query
    ]

    for el in data:
        for i in aup_data_dict:
            if aup_data_dict[i][0] == el["id_aup"]:
                el["load_with_practice"] += aup_data_dict[i][1]
                if not aup_data_dict[i][2]:
                    el["load_without"] += aup_data_dict[i][1]

    return jsonify(data)


@maps.route("/short-control-types", methods=["GET"])
@login_required(request)
def get_short_control_types():
    payload, _ = verify_jwt_token(request.headers["Authorization"])
    user_id = payload["user_id"]

    # сокращённые формы, созданные пользователем
    user_shortnames = {
        item.control_type_id: {
            "control_type_id": item.control_type_id,
            "shortname": item.shortname,
        }
        for item in db.session.query(ControlTypeShortName)
        .filter_by(user_id=user_id)
        .all()
    }

    # добавляем дефолтные формы, которых нет у пользователя
    combined_result = [
        user_shortnames.get(
            # мы берем айти записи которую сейчас сраниваем и передаем ее как ключ в user_shortnames если этот ключ есть get выдаст значение
            item.id,
            # если нет get выдаст значение из дефолтных сокр форм
            {"control_type_id": item.id, "shortname": item.default_shortname},
        )
        for item in db.session.query(D_ControlType).all()
    ]

    return jsonify(combined_result)


@maps.route("/short-control-types", methods=["POST"])
@login_required(request)
def update_short_control_types():
    payload, _ = verify_jwt_token(request.headers["Authorization"])
    user_id = payload["user_id"]

    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "no data"}), 400

    for new_short_form in data:
        control_type_id = new_short_form.get("id")
        title = new_short_form.get("title")

        if control_type_id is None or title is None:
            continue

        # существует ли запись c текущими данными
        current_user_short_form = (
            db.session.query(ControlTypeShortName)
            .filter(
                ControlTypeShortName.control_type_id == control_type_id,
                ControlTypeShortName.user_id == user_id,
            )
            .first()
        )

        if current_user_short_form:
            # запись существует, обновляем поле `shortname`
            current_user_short_form.shortname = title
        else:
            # запись не существует, создаем новую
            new_form = ControlTypeShortName(
                user_id=user_id, control_type_id=control_type_id, shortname=title
            )
            db.session.add(new_form)

    db.session.commit()

    return jsonify({"status": "ok"}), 200
