from models import db
import io
import os
from flask_cors import CORS, cross_origin
from flask import Flask, make_response, redirect, render_template, request, send_file, jsonify
from flask_migrate import Migrate
from sqlalchemy import MetaData
from openpyxl import load_workbook
import pandas as pd
from models import D_Blocks, D_Part, D_ControlType, D_EdIzmereniya, D_Period, D_TypeRecord, AupData, AupInfo, Groups
import math
from excel_check import excel_check
from global_variables import setGlobalVariables, addGlobalVariable, getModuleId, getGroupId
from save_into_bd import SaveCard
from tools import FileForm, take_aup_from_excel_file, error
# from take_from_bd import GetAllFaculties, GetMaps, Header, Table, saveMap

blocks = {}
blocks_r = {}
period = {}
period_r = {}
control_type = {}
control_type_r = {}
ed_izmereniya = {}
ed_izmereniya_r = {}
chast = {}
chast_r = {}
type_record = {}
type_record_r = {}

app = Flask(__name__)
application = app
cors = CORS(app)
app.config.from_pyfile('config.py')
app.config['CORS_HEADERS'] = 'Content-Type'


convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
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


@app.route("/map/<string:aup>")
@cross_origin()
def getMap(aup):
    # table, legend, max_zet = Table(aup, colorSet=1)
    aup = AupInfo.query.filter_by(num_aup=aup).first()
    data = AupData.query.filter_by(id_aup=aup.id_aup).all()
    json = create_json(aup, data)
    return make_response(jsonify(json), 200)
    # q = WorkMap.query.filter_by(id_aup=aup).all()
    # d = dict()
    # d["id_aup"] = q[0].id_aup
    # l = list()
    # for i in q:
    #     a = dict()
    #     a["id"] = i.id
    #     a["discipline"] = i.discipline
    #     a["zet"] = i.zet
    #     a["id_group"] = i.id_group
    #     a["num_col"] = i.num_col
    #     a["num_row"] = i.num_row
    #     a["disc_color"] = i.disc_color
    #     l.append(a)
    # d["data"] = l
    # header = Header(aup)
    # d["header"] = header
    # return jsonify(d)


# @app.route('/save/<string:aup>', methods=["POST"])
# @cross_origin()
# def saveMap1(aup):
#     if request.method == "POST":
#         request_data = request.get_json()
#         for i in range(0, len(request_data)):
#             row = WorkMap.query.filter_by(id=request_data[i]['id']).first()
#             row.discipline = request_data[i]['discipline']
#             row.zet = request_data[i]['zet']
#             row.num_col = request_data[i]['num_col']
#             row.num_row = request_data[i]['num_row']
#             # row.disc_color = request_data[i]['module_color']
#             # row.id_group = request_data[i]['id_group']
#             db.session.commit()
#         return make_response(jsonify(''), 200)

# @app.route("/")
# @cross_origin()
# def index():
#     return make_response(jsonify(''), 200)

@app.route('/upload', methods=["POST", "GET"])
@cross_origin()
def upload():
    form = FileForm(meta={'csrf': False})

    if request.method == "POST":
        if form.validate_on_submit():
            f = form.file.data
            # aup = f.filename.split(' - ')[1].strip()
            path = os.path.join(app.static_folder, 'temp', f.filename)

            # сохранить временный файл с учебным планом
            f.save(path)

            # Вытащить из файла номер аупа
            aup = take_aup_from_excel_file(path)

            # одна функция, описанная в отдельном файле, которая будет выполнять все проверки
            err_arr = excel_check(path, aup)
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

            return make_response(jsonify(aup), 200)
    else:
        return render_template("upload.html", form=form)


# @app.route("/api/aup/<string:aup>")
# @cross_origin()
# def aupJSON(aup):
#     table, legend, max_zet = Table(aup, colorSet=1)

#     data = {
#         'table':table,
#         'max_zet':max_zet
#     }

#     return jsonify(data)

# @app.route("/getAllMaps")
# @cross_origin()
# def getAllMaps():
#     fac = GetAllFaculties()
#     li = list()
#     for i in fac:
#         simple_d = dict()
#         simple_d["faculty_name"] = i.name_faculty
#         maps = GetMaps(id=i.id_faculty)
#         l = list()
#         for j in maps:
#             dd = dict()
#             dd["map_id"] = j.num_aup
#             name = str(j.file).split(" ")
#             dd["map_name"] = " ".join(name[5:len(name)-4])
#             l.append(dd)
#         simple_d["data"] = l

#         li.append(simple_d)

#     return jsonify(li)


# if __name__ == "__main__":
#     app.run(debug=True)


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
    d = dict()
    data = pd.read_excel(file, sheet_name="Лист2")
    #             Наименование
    # 0                   Блок
    # 1                   Шифр
    # 2                  Часть
    # 3                 Модуль
    # 4             Тип записи
    # 5             Дисциплина
    # 6        Период контроля
    # 7               Нагрузка
    # 8             Количество
    # 9               Ед. изм.
    # 10                   ЗЕТ
    # 11              групп ID
    # 12                    ID
    # 13    Позиция в семестре

    allRow = []
    modules = {}
    groups = {}
    counter = 0
    flag = ""
    flag_val = 0
    for i in range(len(data)):
        row = []
        for column in data.columns:
            row.append(data[column][i])
        row.append('')

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
            row[3] = ""
        val = row[3]
        row[3] = modules.get(val)
        if row[3] == None:
            id = getModuleId(db, val)
            modules[val] = id
            row[3] = id

        row[11] = groups.get(val)
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
        row.append(counter)
        counter += 1

        if flag != row[5] + str(row[6]):
            flag = row[5] + str(row[6])
            pos = d.get(row[6])
            if pos == None:
                d[row[6]] = 0
                row.append(0)
                flag_val = 0
            else:
                row.append(pos + 1)
                d[row[6]] += 1
                flag_val = d[row[6]]
        else:
            row.append(flag_val)

        allRow.append(row)

    return allRow


def create_json(aupInfo, aupData):
    json = dict()
    json['header'] = [aupInfo.name_op.okco.program_code + '.' + aupInfo.name_op.num_profile,
                      aupInfo.name_op.okco.name_okco, aupInfo.name_op.name_spec, aupInfo.faculty.name_faculty]
    json['data'] = list()
    flag = ""
    for i, item in enumerate(aupData):
        if flag != item.discipline + str(item.id_period):
            if i != 0:
                json['data'].append(d)
            flag = item.discipline + str(item.id_period)
            d = dict()
            d["discipline"] = item.discipline
            d["id_group"] = item.id_group
            d["num_col"] = item.id_period
            d["num_row"] = item.num_row
            d["type"] = list()
            zet = dict()
            zet["control"] = control_type_r[item.id_type_control]
            zet["zet"] = item.zet / 100
            # zet["id"] = item.[12]
            d["type"].append(zet)
        else:
            zet = dict()
            zet["control"] = control_type_r[item.id_type_control]
            zet["zet"] = item.zet / 100
            # zet["id"] = item.[12]
            d["type"].append(zet)

    return json


# путь для загрузки сформированной КД
@app.route("/save_excel/<string:aup>", methods=["GET"])
@cross_origin()
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


@app.route("/getColors", methods=["GET"])
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