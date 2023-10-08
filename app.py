import io
import json
import os
import warnings

import pandas as pd
from flask import Flask, make_response, render_template, request, send_file, jsonify
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import MetaData

from checker import AupChecker
from checker.aup_data_filter import AupDataFilter
from checker.utils import match_element
from excel_check import excel_check
from global_variables import setGlobalVariables, addGlobalVariable, getModuleId, getGroupId
from models import *
from models import db
from print_excel import saveMap
from save_into_bd import SaveCard
from take_from_bd import (blocks, blocks_r, period, period_r, control_type, control_type_r,
                          ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r, create_json)
from tools import FileForm, take_aup_from_excel_file, error
from admin import init_admin

warnings.simplefilter("ignore")

app = Flask(__name__)
application = app
cors = CORS(app, resources={r"*": {"origins": "*"}})

app.config.from_pyfile('config.py')
app.config['CORS_HEADERS'] = 'Content-Type'

convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

weith = {
    'Проектная деятельность': 10,
    'Введение в проектную деятельность': 10,
    'Управление проектами': 10,
    'Иностранный язык': 1
}

metadata = MetaData(naming_convention=convention)
db.init_app(app)
migrate = Migrate(app, db)

# from save_into_bd import bp as save_db_bp

# app.register_blueprint(save_db_bp)

# from models import AUP

ZET_HEIGHT = 90

setGlobalVariables(app, blocks, blocks_r, period, period_r, control_type, control_type_r,
                   ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r)

if os.path.exists(app.static_folder + '/temp') == False:
    os.makedirs(app.static_folder + '/temp', exist_ok=True)


init_admin(app, db.session)


@app.route("/api/map/<string:aup>")
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

    # if check_sum_zet_in_type(json['data']) == False:
    #     return make_response(jsonify('ERROR sum_zet=0'), 400)
    return make_response(jsonify(json), 200)

    # data = AupData.query.filter_by(id_aup=aup.id_aup).all()
    json = create_json(aup)

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


@app.route('/api/save/<string:aup>', methods=["POST"])
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
            row.id_edizm = request_data[i]['type'][in_type][j]['id_edizm']
            row.control_type_id = request_data[i]['type'][in_type][j]['control_type_id']
            row.id_period = request_data[i]['num_col'] + 1
            row.num_row = request_data[i]['num_row']
            row.id_group = request_data[i]['id_group']
            row.id_block = request_data[i]['id_block']
            row.id_module = request_data[i]['id_module']
            row.id_part = request_data[i]['id_part']
            row.shifr = request_data[i]['shifr']
            l.append(row)
        except:
            return make_response('Save error', 400)


@app.route('/api/get_id_edizm', methods=["GET"])
def get_id_edizm():
    l = list()
    d = dict()
    d['id_edizm'] = 1
    d['kratn'] = 2
    d['value'] = 'Часы'
    d['coef'] = 0.0625
    l.append(d)
    d = dict()
    d['id_edizm'] = 2
    d['kratn'] = 1
    d['value'] = 'Недели'
    d['coef'] = 1.5
    l.append(d)
    return make_response(jsonify(l), 200)


@app.route('/api/upload', methods=["POST", "GET"])
def upload():
    form = FileForm(meta={'csrf': False})

    if request.method == "POST":
        if form.validate_on_submit():
            files = request.files.getlist("file")
            res = list()
            for f in files:
                options_check = json.loads(request.form['options'])
                print(options_check)
                # options_check = dict()
                # options_check['enableCheckIntegrality'] = False
                # options_check['enableCheckSumMap'] = False

                # aup = f.filename.split(' - ')[1].strip()
                ### путь к файлу на диске

                path = os.path.join(app.static_folder, 'temp', f.filename)

                # сохранить временный файл с учебным планом
                f.save(path)

                # Вытащить из файла номер аупа
                aup = take_aup_from_excel_file(path)

                # одна функция, описанная в отдельном файле, которая будет выполнять все проверки
                err_arr = excel_check(path, aup, options_check)
                if err_arr != []:
                    os.remove(path)
                    return error('\n'.join(err_arr))

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

                # удалить временный файл
                os.remove(path)
                res.append(aup)

            return make_response(jsonify(res), 200)
    else:
        return render_template("upload.html", form=form)


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
        row.append(weith.get(row[5], 5))

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
@app.route("/api/save_excel/<string:aup>", methods=["GET"])
def save_excel(aup):
    filename = saveMap(aup, app.static_folder, expo=60)
    # Upload xlxs file in memory and delete file from storage -----
    return_data = io.BytesIO()
    with open(filename, 'rb') as fo:
        return_data.write(fo.read())
    # (after writing, cursor will be at last byte, so move it to start)
    return_data.seek(0)

    # path = os.path.join(app.static_folder, 'temp', filename)
    os.remove(filename)
    # --------------
    return send_file(return_data,
                     download_name=os.path.split(filename)[-1])


@app.route("/api/getGroups", methods=["GET"])
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


@app.route("/api/getAllMaps")
def getAllMaps():
    fac = SprFaculty.query.all()
    li = list()
    for i in fac:
        simple_d = dict()
        simple_d["faculty_name"] = i.name_faculty
        simple_d["directions"] = GetMaps(id=i.id_faculty)
        li.append(simple_d)
    return jsonify(li)


def GetMaps(id):
    q = AupInfo.query.filter(AupInfo.id_faculty == id).all()
    l = list()
    for row in q:
        d = dict()
        name = str(row.file).split(" ")
        # d["name"] = " ".join(name[5:len(name)-4])
        # d["code"] = str(row.num_aup).split(" ")[0]
        d["name"] = row.name_op.name_spec
        d["code"] = row.num_aup
        d["year"] = row.year_beg
        d["form_educ"] = row.id_form
        l.append(d)
    return l


@app.route('/api/add-group', methods=["POST"])
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


@app.route('/api/delete-group', methods=["POST"])
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


@app.route('/api/get-group-by-aup/<string:aup>', methods=["GET"])
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


@app.route('/api/get-modules-by-aup/<string:aup>', methods=["GET"])
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


@app.route('/api/update-group', methods=["POST"])
def UpdateGroup():
    request_data = request.get_json()
    gr = Groups.query.filter_by(id_group=request_data['id']).first()
    gr.name_group = request_data['name']
    gr.color = request_data['color']
    db.session.add(gr)
    db.session.commit()
    return make_response(jsonify('OK'), 200)


@app.route("/api/getControlTypes")
def getControlTypes():
    control_type_arr = []
    for k, v in control_type_r.items():
        if v == 'Экзамен' or v == 'Зачет' or v == 'Дифференцированный зачет':
            is_control = True
        else:
            is_control = False
        control_type_arr.append({"name": v, "id": k, "is_control": is_control})
    return make_response(jsonify(control_type_arr), 200)


@app.route("/check/<string:aup>")
def check_aup(aup: str):
    hidetitle = bool(request.args.get('hide_title', default=False))
    hidedetailed = bool(request.args.get('hide_detailed', default=False))
    checker = AupChecker(db_instance=db, hide_title = hidetitle,hide_detailed = hidedetailed)
    return make_response(checker.get_json_report(aup))


@app.route("/check/<string:aup>/save")
def save_report(aup: str):
    hidetitle = bool(request.args.get('hide_title', default=False))
    hidedetailed = bool(request.args.get('hide_detailed', default=False))
    checker = AupChecker(db_instance=db, hide_title = hidetitle,hide_detailed = hidedetailed )
    path = checker.create_excel(aup)
    return make_response(path)


@app.route("/check/okso/<string:okso>")
def check_okso(okso: str):
    hidetitle = bool(request.args.get('hide_title', default=False))
    hidedetailed = bool(request.args.get('hide_detailed', default=False))
    checker = AupChecker(db_instance=db, hide_title = hidetitle,hide_detailed = hidedetailed)
    return checker.get_json_reports_by_okso(okso)


@app.route("/check/okso/<string:okso>/save")
def save_okso(okso: str):
    hidetitle = bool(request.args.get('hide_title', default=False))
    hidedetailed = bool(request.args.get('hide_detailed', default=False))
    checker = AupChecker(db_instance=db, hide_title = hidetitle,hide_detailed = hidedetailed)
    return checker.make_excel_reports_by_okso(okso)


@app.route('/test')
def test():
    from checker.utils import match_element

    filter_ = {
        'accept': {
            'discipline': ['физическая культ']
        },
        'decline': {}

    }

    disciplines = set()

    for el in AupData.query.all():
        if match_element(el, filter_):
            disciplines.add(el.discipline)

    return make_response(json.dumps(list(disciplines), ensure_ascii=False), 200)
