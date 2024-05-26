import io
import json
import os

import werkzeug.exceptions
from flask import Blueprint, make_response, jsonify, request, send_file

from auth.logic import login_required, aup_require, verify_jwt_token
from auth.models import Mode
from maps.logic.excel_check import excel_check
from maps.logic.print_excel import saveMap
from maps.logic.save_into_bd import SaveCard
from maps.logic.take_from_bd import (control_type_r,
                                     create_json, getAupData)
from maps.logic.tools import take_aup_from_excel_file, timeit, getAupInfo, save_loop, prepare_shifr
from maps.logic.upload_xml import create_xml
from maps.models import *
from datetime import datetime


maps = Blueprint("maps", __name__, url_prefix='/api', static_folder='static')

if not os.path.exists(maps.static_folder + '/temp'):
    os.makedirs(maps.static_folder + '/temp', exist_ok=True)


@maps.route("/map/<string:aup>")
def getMap(aup):
    json = create_json(aup)
    if not json:
        return make_response(jsonify({'error': "not found"}), 404)

    return make_response(jsonify(json), 200)


@maps.route('/save/<string:aup>', methods=["POST"])
@login_required(request)
@aup_require(request)
def saveMap1(aup):
    changes = []
    if request.method == "POST":
        request_data = request.get_json()
        l = list()
        for i in range(0, len(request_data)):
            changes.extend(save_loop(i, 'session', l, request_data))
            changes.extend(save_loop(i, 'value', l, request_data))

        if changes:
            payload, verify_result = verify_jwt_token(request.headers["Authorization"])
            aup_info = AupInfo.query.filter_by(num_aup=aup).first()
            revision = Revision(
                title="",
                date=datetime.now(),
                isActual=True,
                user_id=payload['user_id'],
                aup_id=aup_info.id_aup,
            )
            revision.logs = changes
            db.session.add(revision)

        db.session.bulk_save_objects(l)
        db.session.commit()
        json = create_json(aup)
        return make_response(jsonify(json), 200)

@maps.route('/meta-info', methods=["GET"])
def get_id_edizm():
    measure_coefs = [
        {
            "id_edizm": 1,
            "kratn": 2,
            "value": 'Часы',
            "coef": 0.0625
        },
        {
            'id_edizm': 2,
            'kratn': 1,
            'value': 'Недели',
            'coef': 1.5,
        }
    ]

    modes = []
    for mode in Mode.query.all():
        mode: Mode
        roles = [{
            "id": role.id_role,
            "title": role.name_role,
        } for role in mode.roles]

        modes.append({
            "id": mode.id,
            "title": mode.title,
            "action": mode.action,
            "roles": roles
        })

    return make_response(jsonify({
        "measure_coefs": measure_coefs,
        "modes": modes,
    }), 200)


@maps.route('/upload', methods=["POST"])
@timeit
#@login_required(request)
def upload():
    files = request.files.getlist("file")
    result_list = list()
    for f in files:
        options_check = json.loads(request.form['options'])
        print(options_check)

        path = os.path.join(maps.static_folder, 'temp', f.filename)
        f.save(path)
        aup = take_aup_from_excel_file(path)

        result = {
            'aup': aup,
            'filename': f.filename,
            'errors': excel_check(path, aup, options_check)
        }

        result_list.append(result)

        if result['errors']:
            os.remove(path)
            continue

        # словарь с содержимым 1 листа
        aupInfo = getAupInfo(path, f.filename)

        # массив с содержимым 2 листа
        aupData = getAupData(path)

        SaveCard(db, aupInfo, aupData)
        f.close()

        os.remove(path)

    return make_response(jsonify(result_list), 200)


@maps.route("/save_excel/<string:aup>", methods=["GET"])
def save_excel(aup):
    try:
        paper_size = json.loads(request.form['paper_size'])
        orientation = json.loads(request.form['orientation'])
    except:
        paper_size = "3"
        orientation = "land"
    filename = saveMap(aup, maps.static_folder, paper_size, orientation, expo=60)

    # Upload xlxs file in memory and delete file from storage
    return_data = io.BytesIO()
    with open(filename, 'rb') as fo:
        return_data.write(fo.read())

    # after writing, cursor will be at last byte, so move it to start
    return_data.seek(0)

    os.remove(filename)

    response = make_response(send_file(return_data, download_name=filename))
    response.headers['Access-Control-Expose-Headers'] = "Content-Disposition"
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


@maps.route('/get-modules', methods=['GET'])
def get_modules():
    modules = D_Modules.query.all()
    res = []
    for module in modules:
        module_as_dict: dict = module.as_dict()
        module_as_dict['name'] = module_as_dict['title']
        module_as_dict.pop('title')
        res.append(module_as_dict)
    return jsonify(res)

@maps.route('/add-module', methods=['POST'])
# @login_required(request)
# @aup_require(request)
def add_module():
    module = request.get_json()
    if not module['name']:
        return jsonify({'result': 'error', 'message': 'поле "name" не должно быть пустым'}), 400
    
    new_module = D_Modules()
    new_module.title = module['name']
    new_module.color = module['color']

    db.session.add(new_module)
    db.session.commit()

    return jsonify({
        'id': new_module.id,
        'name': new_module.title,
        'color': new_module.color
    }), 200


@maps.route('/modules/<int:id>', methods=['PUT', 'DELETE'])
# @login_required(request)
# @aup_require(request)
def edit_or_delete_module(id: int):
    module = D_Modules.query.get(id)
    if not module:
        return jsonify({'result': 'error', 'message': 'not found'}), 404
        
    if request.method == "DELETE":
        for el in AupData.query.filter_by(id_module=module.id).all():
            el.id_module = 1
            db.session.add(el)

        db.session.delete(module)
        db.session.commit()
        return jsonify({'result': 'ok'}), 200

    elif request.method == "PUT":
        data = request.get_json()
        module.title = data['name']
        module.color = data['color']

        db.session.add(module)
        db.session.commit()

        return jsonify(module.as_dict()), 200


    

@maps.route("/getAllMaps")
def getAllMaps():
    specialization_names = {}
    for el in NameOP.query.all():
        el: NameOP
        specialization_names.update({el.id_spec: el.name_spec})

    faculties = SprFaculty.query.all()
    li = []

    for fac in faculties:
        fac: SprFaculty
        maps = []
        for row in fac.aup_infos:
            row: AupInfo
            maps.append({
                "name": specialization_names[row.id_spec],
                "code": row.num_aup,
                "year": row.year_beg,
                "form_educ": row.id_form,
            })

        li.append({
            "faculty_id": fac.id_faculty,
            "faculty_name": fac.name_faculty,
            "admin_only": fac.admin_only == 1,
            "directions": maps,
        })
    return jsonify(li)


@maps.route('/add-group', methods=["POST"])
@login_required(request)
@aup_require(request)
def AddNewGroup():
    request_data = request.get_json()
    if request_data['name'] == '':
        return make_response(jsonify('Введите название группировки'), 400)
    data = Groups(name_group=request_data['name'], color=request_data['color'])
    db.session.add(data)
    db.session.commit()
    d = dict()
    d["id"] = data.id_group
    d["name"] = data.name_group
    d["name"] = data.name_group
    d["color"] = data.color
    return make_response(jsonify(d), 200)


@maps.route('/delete-group', methods=["POST"])
@login_required(request)
@aup_require(request)
def DeleteGroup():
    request_data = request.get_json()
    d = AupData.query.filter_by(id_group=request_data['id']).all()
    for row in d:
        row.id_group = 1
        db.session.add(row)
    db.session.commit()
    Groups.query.filter_by(id_group=request_data['id']).delete()
    db.session.commit()
    return make_response(jsonify('OK'), 200)


@maps.route('/get-group-by-aup/<string:aup>', methods=["GET"])
def GetGroupByAup(aup):
    aupId = AupInfo.query.filter_by(num_aup=aup).first().id_aup
    aupData = AupData.query.filter_by(id_aup=aupId).all()

    groups_id = set()
    for elem in aupData:
        groups_id.add(elem.id_group)

    groups = []
    for g in Groups.query.filter(Groups.id_group.in_(groups_id)).all():
        groups.append({
            "id": g.id_group,
            "name": g.name_group,
            "color": g.color,
        })
    return make_response(jsonify(groups), 200)


@maps.route('/get-modules-by-aup/<string:aup>', methods=["GET"])
def GetModulesByAup(aup):
    aup_info: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()

    modules_set = set()
    for elem in aup_info.aup_data:
        modules_set.add(elem.module)

    modules = []
    for m in modules_set:
        if m.title != 'Без названия':
            modules.append({
                "id": m.id,
                "name": m.title,
                'color': m.color,
            })
    return make_response(jsonify(modules), 200)


@maps.route('/update-group', methods=["POST"])
@login_required(request)
@aup_require(request)
def UpdateGroup():
    request_data = request.get_json()
    gr = Groups.query.filter_by(id_group=request_data['id']).first()
    gr.name_group = request_data['name']
    gr.color = request_data['color']
    db.session.add(gr)
    db.session.commit()
    return make_response(jsonify('OK'), 200)


@maps.route("/getControlTypes")
def getControlTypes():
    control_types = []
    for k, v in control_type_r.items():
        is_control = v == 'Экзамен' or v == 'Зачет' or v == 'Дифференцированный зачет'
        control_types.append({"id": k, "name": v, "is_control": is_control})

    return make_response(jsonify(control_types), 200)


@maps.route("/test")
def test():

    return jsonify(), 200


@maps.route("/upload-xml/<string:aup>")
def upload_xml(aup):
    filename = create_xml(aup)

    data = io.BytesIO()
    with open(filename, 'rb') as res:
        data.write(res.read())
    data.seek(0)

    return send_file(data, download_name="sample.txt")


@maps.route('/aup-info/<int:aup>', methods=['GET', 'POST', 'PATCH', 'DELETE'])
@login_required(request)
@aup_require(request)
def aup_crud(aup: str | None):
    aup: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aup:
        return jsonify({'status': 'not found'}), 404

    if request.method == "GET":
        return jsonify(aup.as_dict()), 200

    if request.method == "DELETE":
        db.session.delete(aup)
        db.session.commit()
        return jsonify({'status': 'ok'})

    if request.method == "POST":
        match dict(request.args):
            case {'copy_with_num': new_aup_num}:
                if AupInfo.query.filter_by(num_aup=new_aup_num).first():
                    return jsonify({'status': 'already exists'}), 400

                aup.copy(new_aup_num)
                return jsonify({'status': 'ok', 'aup_num': new_aup_num})
            case _:
                return jsonify({"result": "failed"}), 400

    if request.method == "PATCH":
        data = request.get_json()

        for field, value in data.items():
            if field in AupInfo.__dict__:
                aup.__setattr__(field, value)

        db.session.add(aup)

        try:
            db.session.commit()
        except Exception as ex:
            print(ex)
            db.session.rollback()
            return jsonify({'status': 'failed', 'aup_num': aup.num_aup}), 403

        return jsonify({'status': 'ok', 'aup_num': aup.num_aup}), 200




