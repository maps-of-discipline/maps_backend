import io
import json
import os

import pandas as pd
from flask import Blueprint, make_response, jsonify, request, send_file

from auth.models import Mode
from maps.logic.excel_check import excel_check
from maps.logic.global_variables import addGlobalVariable, getModuleId, getGroupId
from maps.logic.print_excel import saveMap
from maps.logic.save_into_bd import SaveCard
from maps.logic.take_from_bd import (blocks, blocks_r, period, period_r, control_type, control_type_r,
                                     ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r,
                                     create_json)
from maps.logic.tools import prepare_shifr, take_aup_from_excel_file, timeit
from maps.logic.upload_xml import create_xml
from maps.models import *
from auth.logic import login_required, aup_require

maps = Blueprint("maps", __name__, url_prefix='/api', static_folder='static')

if not os.path.exists(maps.static_folder + '/temp'):
    os.makedirs(maps.static_folder + '/temp', exist_ok=True)




@maps.route("/map/<string:aup>")
def getMap(aup):
    # table, legend, max_zet = Table(aup, colorSet=1)
    # aup = AupInfo.query.filter_by(num_aup=aup).first()

    # # Второй способ доставать постоянными запросами, долго достаточно
    # data = AupData.query.filter_by(id_aup=aup.id_aup)
    # max_column = db.session.query(func.max(AupData.id_period)).first()[0]
    # max_row = db.session.query(func.max(AupData.num_row)).first()[0]
    # json = create_json_test(aup, data, max_column, max_row)

    # data = AupData.query.filter_by(id_aup=aup.id_aup).all()
    json = create_json(aup)
    if not json:
        return make_response(jsonify({'error': "not found"}), 404)

    # if check_sum_zet_in_type(json['data']) == False:
    #     return make_response(jsonify('ERROR sum_zet=0'), 400)
    return make_response(jsonify(json), 200)



def check_sum_zet_in_type(data):
    for item in data:
        sum_zet_type = 0
        for i in item['type']:
            sum_zet_type += i['zet']
        if sum_zet_type == 0: return False


def check_sum_zet_in_type(data):
    for item in data:
        sum_zet_type = 0
        for i in item['type']:
            sum_zet_type += i['zet']
        if sum_zet_type == 0:
            return False


@maps.route('/save/<string:aup>', methods=["POST"])
@login_required(request)
@aup_require(request)
def saveMap1(aup):
    if request.method == "POST":
        request_data = request.get_json()
        l = list()
        row = any
        for i in range(0, len(request_data)):
            save_loop(i, 'session', l, request_data)
            save_loop(i, 'value', l, request_data)

        db.session.bulk_save_objects(l)
        db.session.commit()
        json = create_json(aup)
        return make_response(jsonify(json), 200)


def save_loop(i, in_type, l, request_data):
    for j in range(0, len(request_data[i]['type'][in_type])):
        try:
            row = AupData.query.filter_by(
                id=request_data[i]['type'][in_type][j]['id']).first()
            row.discipline = request_data[i]['discipline']
            row.amount = request_data[i]['type'][in_type][j]['amount'] * 100
            row.id_edizm = 1 if request_data[i]['type'][in_type][j]['amount_type'] == 'hour' else 2
            row.control_type_id = request_data[i]['type'][in_type][j]['control_type_id']
            row.id_period = request_data[i]['num_col'] + 1
            row.num_row = request_data[i]['num_row']
            row.id_group = request_data[i]['id_group']
            row.id_block = request_data[i]['id_block']
            row.id_module = request_data[i]['id_module']
            row.id_part = request_data[i]['id_part']
            row.shifr = prepare_shifr(request_data[i]['shifr'])
            l.append(row)
        except:
            return make_response('Save error', 400)


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


def getAupInfo(file, filename):
    data = pd.read_excel(file, sheet_name='Лист1')
    aupInfo = dict()
    data = data['Содержание']
    #                     Наименование
    # 0                     Номер АУП
    # 1               Вид образования
    # 2           Уровень образования
    # 3   Направление (специальность)
    # 4             Код специальности
    # 5                  Квалификация
    # 6       Профиль (специализация)
    # 7                 Тип стандарта
    # 8                     Факультет
    # 9           Выпускающая кафедра
    # 10               Форма обучения
    # 11                   Год набора
    # 12              Период обучения
    # 13                      На базе
    # 14    Фактический срок обучения
    aupInfo["num"] = data[0]
    aupInfo["type_education"] = data[1]
    aupInfo["degree"] = data[2]
    aupInfo["direction"] = data[3]
    aupInfo["program_code"] = data[4]
    aupInfo["qualification"] = data[5]
    aupInfo["name_spec"] = data[6]
    aupInfo["type_standard"] = data[7]
    aupInfo["name_faculty"] = data[8]
    aupInfo["department"] = data[9]
    aupInfo["form_educ"] = data[10]
    aupInfo["years_begin"] = data[11]
    aupInfo["period_edication"] = data[12]
    aupInfo["base"] = data[13]
    aupInfo["full_years"] = data[14]
    aupInfo["filename"] = filename
    return aupInfo


weight = {
    'Проектная деятельность': 10,
    'Введение в проектную деятельность': 10,
    'Управление проектами': 10,
    'Иностранный язык': 1
}


def getAupData(file):
    data = pd.read_excel(file, sheet_name="Лист2")
    #             Наименование
    # 0                   Блок.
    # 1                   Шифр.
    # 2                  Часть.
    # 3                 Модуль.
    # 4             Тип записи.
    # 5             Дисциплина.
    # 6        Период контроля.
    # 7               Нагрузка----
    # 8             Количество----
    # 9               Ед. изм.----
    # 10                   ЗЕТ----
    # 11              групп ID.
    # 12    Позиция в семестре.
    # 13                   Вес.

    allRow = []
    modules = {}
    groups = {}
    for i in range(len(data)):
        row = []
        for column in data.columns:
            row.append(data[column][i])

        # if row[5]is None:
        # print(i, row[5])

        row[1] = prepare_shifr(row[1])

        val = row[0]
        row[0] = blocks.get(val)
        if row[0] == None:
            id = addGlobalVariable(db, D_Blocks, val)
            blocks[val] = id
            blocks_r[id] = val
            row[0] = id

        val = row[2]
        row[2] = chast.get(val)
        if row[2] == None:
            id = addGlobalVariable(db, D_Part, val)
            chast[val] = id
            chast_r[id] = val
            row[2] = id

        if pd.isna(row[3]):
            row[3] = "Без названия"
        val = row[3]
        row[3] = modules.get(val)
        if row[3] == None:
            id = getModuleId(db, val)
            modules[val] = id
            row[3] = id

        if 'Модуль' in val:
            val = val.strip()
            val = val[8:-1].strip()
        row.append(groups.get(val))
        if row[11] == None:
            id = getGroupId(db, val)
            groups[val] = id
            row[11] = id

        val = row[4]
        row[4] = type_record.get(val)
        if row[4] == None:
            id = addGlobalVariable(db, D_TypeRecord, val)
            type_record[val] = id
            type_record_r[id] = val
            row[4] = id

        val = row[6]
        row[6] = period.get(val)
        if row[6] == None:
            id = addGlobalVariable(db, D_Period, val)
            period[val] = id
            period_r[id] = val
            row[6] = id

        val = row[7]
        row[7] = control_type.get(val)
        if row[7] == None:
            id = addGlobalVariable(db, D_ControlType, val)
            control_type[val] = id
            control_type_r[id] = val
            row[7] = id

        val = row[9]
        row[9] = ed_izmereniya.get(val)
        if row[9] == None:
            id = addGlobalVariable(db, D_EdIzmereniya, val)
            ed_izmereniya[val] = id
            ed_izmereniya_r[id] = val
            row[9] = id

        if pd.isna(row[8]):
            row[8] = 0
        else:
            try:
                row[8] = int(float(row[8].replace(',', '.')) * 100)
            except:
                row[8] = int(float(row[8]) * 100)

        if pd.isna(row[10]):
            row[10] = 0
        else:
            try:
                row[10] = int(float(row[10].replace(',', '.')) * 100)
            except:
                row[10] = int(float(row[10]) * 100)

        row.append("позиция")
        row.append(weight.get(row[5], 5))

        allRow.append(row)

    allRow.sort(key=lambda x: (x[6], x[13], x[5]))

    counter = 0
    semestr = allRow[0][6]
    disc = allRow[0][5]
    for i in range(len(allRow)):
        if allRow[i][6] != semestr:
            semestr = allRow[i][6]
            counter = -1
        if allRow[i][5] != disc:
            disc = allRow[i][5]
            counter += 1

        allRow[i][12] = counter

    return allRow


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
    aupId = AupInfo.query.filter_by(num_aup=aup).first()
    a = aupId.id_aup
    aupData = AupData.query.filter_by(id_aup=a).all()
    groups = set()
    for elem in aupData:
        groups.add(elem.id_group)
    l = list()
    for elem in groups:
        d = dict()
        g = Groups.query.filter_by(id_group=elem).first()
        d["id"] = g.id_group
        d["name"] = g.name_group
        d["color"] = g.color
        l.append(d)
    return make_response(jsonify(l), 200)


@maps.route('/get-modules-by-aup/<string:aup>', methods=["GET"])
def GetModulesByAup(aup):
    aupId = AupInfo.query.filter_by(num_aup=aup).first()
    a = aupId.id_aup
    aupData = AupData.query.filter_by(id_aup=a).all()
    modules = set()
    for elem in aupData:
        modules.add(elem.id_module)
    l = list()
    for elem in modules:
        m = D_Modules.query.filter_by(id=elem).first()
        if m.title == 'Без названия':
            continue
        d = dict()
        d["id"] = m.id
        d["title"] = m.title
        l.append(d)
    return make_response(jsonify(l), 200)


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
    control_type_arr = []
    for k, v in control_type_r.items():
        if v == 'Экзамен' or v == 'Зачет' or v == 'Дифференцированный зачет':
            is_control = True
        else:
            is_control = False
        control_type_arr.append({"name": v, "id": k, "is_control": is_control})
    return make_response(jsonify(control_type_arr), 200)


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
    db.session.query(SprFaculty).all()
    return jsonify("faculties")


@maps.route("/upload-xml/<string:aup>")
def upload_xml(aup):
    filename = create_xml(aup)

    data = io.BytesIO()
    with open(filename, 'rb') as res:
        data.write(res.read())
    data.seek(0)

    return send_file(data, download_name="sample.txt")
