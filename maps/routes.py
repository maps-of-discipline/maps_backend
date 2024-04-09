import io
import json
import os

from flask import Blueprint, make_response, jsonify, request, send_file

from auth.logic import login_required, aup_require
from auth.models import Mode
from maps.logic.excel_check import excel_check
from maps.logic.print_excel import saveMap
from maps.logic.save_into_bd import SaveCard
from maps.logic.take_from_bd import (control_type_r,
                                     create_json, getAupData)
from maps.logic.tools import take_aup_from_excel_file, timeit, getAupInfo, save_loop
from maps.logic.upload_xml import create_xml
from maps.models import *


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
    if request.method == "POST":
        request_data = request.get_json()
        l = list()
        for i in range(0, len(request_data)):
            save_loop(i, 'session', l, request_data)
            save_loop(i, 'value', l, request_data)

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


@maps.route('/upload', methods=["POST", "GET"])
@timeit
@login_required(request)
def upload():
    if request.method == "POST":
        files = request.files.getlist("file")
        result_list = list()
        for f in files:
            options_check = json.loads(request.form['options'])
            print(options_check)

            ### путь к файлу на диске
            path = os.path.join(maps.static_folder, 'temp', f.filename)

            # сохранить временный файл с учебным планом
            f.save(path)

            # Вытащить из файла номер аупа
            aup = take_aup_from_excel_file(path)

            # одна функция, описанная в отдельном файле, которая будет выполнять все проверки
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

            # берём aupInfo["num"] и смотрим, есть ли в БД уже такая карта, если есть, то редиректим на страницу с этой картой ???
            # Можно сделать всплывающее окно: "Хотите перезаписать существующий учебный план?" и ответы "Да" и "Нет".
            # Если нет, то просто редиректим на карту, если да, то просто стираем все по номеру аупа в aupData
            # (в SaveCard уже реализован этот функционал)

            # массив с содержимым 2 листа
            aupData = getAupData(path)
            # json = create_json(aupData, aupInfo)
            # сохранение карты
            SaveCard(db, aupInfo, aupData)
            f.close()
            # удалить временный файл
            os.remove(path)

        return make_response(jsonify(result_list), 200)
    else:
        return make_response(jsonify("Only post method"), 400)


# путь для загрузки сформированной КД
@maps.route("/save_excel/<string:aup>", methods=["GET"])
def save_excel(aup):
    try:
        paper_size = json.loads(request.form['paper_size'])
        orientation = json.loads(request.form['orientation'])
    except:
        paper_size = "3"
        orientation = "land"
    filename = saveMap(aup, maps.static_folder, paper_size, orientation, expo=60)
    # Upload xlxs file in memory and delete file from storage -----
    return_data = io.BytesIO()
    with open(filename, 'rb') as fo:
        return_data.write(fo.read())
    # (after writing, cursor will be at last byte, so move it to start)
    return_data.seek(0)

    # path = os.path.join(app.static_folder, 'temp', filename)
    os.remove(filename)
    # --------------

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
                "title": m.title,
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


@maps.route("/delete-aup/<string:aup>")
@login_required(request)
@aup_require(request)
def delete_aup(aup):
    aup = AupInfo.query.filter_by(num_aup=aup).first()
    if aup:
        db.session.delete(aup)
        db.session.commit()

    return jsonify({'result': "successful"})


@maps.route('/test')
def test():
    print(dict(request.form))
    return jsonify("faculties")


@maps.route("/upload-xml/<string:aup>")
def upload_xml(aup):
    filename = create_xml(aup)

    data = io.BytesIO()
    with open(filename, 'rb') as res:
        data.write(res.read())
    data.seek(0)

    return send_file(data, download_name="sample.txt")
