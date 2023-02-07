import io
import os
from urllib import response
from flask_cors import CORS, cross_origin
from flask import Flask, make_response, redirect, render_template, request, send_file, jsonify
from flask_migrate import Migrate
from sqlalchemy import MetaData

from excel_check import (check_empty_ceils, check_full_zet_in_plan, check_smt,
                         layout_of_disciplines)
from save_into_bd import delete_from_workload, delete_from_workmap, save_into_bd, update_workload
from take_from_bd import GetAllFaculties, GetMaps, Header, Table, saveMap
from tools import FileForm
from models import Module, WorkMap

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

from models import db

metadata = MetaData(naming_convention=convention)
db.init_app(app)
migrate = Migrate(app, db)

from save_into_bd import bp as save_db_bp

app.register_blueprint(save_db_bp)

from models import AUP

ZET_HEIGHT = 90

@app.route('/', methods=["POST", "GET"])
@cross_origin()
def index():
    faculties = GetAllFaculties()
    if request.method == "POST":
        name = request.form.get('name')
        id = request.form.get('id_faculty')
        maps = GetMaps(id=id, name=name)
        print(maps, id, name)
        if maps == []:
            flag = False
        else:
            flag = True
        return render_template('index.html', maps=maps, faculties=faculties, flag=flag)
    return render_template('index.html', faculties=faculties)

@app.route("/map/<string:aup>")
@cross_origin()
def getMap(aup):
    # table, legend, max_zet = Table(aup, colorSet=1)
    q = WorkMap.query.filter_by(id_aup=aup).all()
    d = dict()
    d["id_aup"] = q[0].id_aup
    l = list()
    for i in q:
        a = dict()
        a["id"] = i.id
        a["discipline"] = i.discipline
        a["zet"] = i.zet
        a["id_group"] = i.id_group
        a["num_col"] = i.num_col
        a["num_row"] = i.num_row
        a["disc_color"] = i.disc_color
        l.append(a)
    d["data"] = l

    header = Header(aup)   
    d["header"] = header 
    return jsonify(d)


@app.route('/save/<string:aup>', methods=["POST"])
@cross_origin()
def saveMap1(aup):
    if request.method == "POST":
        request_data = request.get_json()
        for i in range(0, len(request_data)):
            row = WorkMap.query.filter_by(id=request_data[i]['id']).first()
            row.discipline = request_data[i]['discipline']
            row.zet = request_data[i]['zet']
            row.num_col = request_data[i]['num_col']
            row.num_row = request_data[i]['num_row']
            # row.disc_color = request_data[i]['module_color']
            # row.id_group = request_data[i]['id_group']
            db.session.commit()
        return make_response(jsonify(''), 200)

@app.route('/upload', methods=["POST", "GET"])
@cross_origin()
def upload():
    form = FileForm(meta={'csrf':False})
    
    if request.method == "POST":
        if form.validate_on_submit():
            f = form.file.data
            aup = f.filename.split(' - ')[1].strip()
            path = os.path.join(app.static_folder, 'temp', f.filename)
            

            ### ------------------------------------ ###
            ### Проверка на пустые ячейки ###
            f.save(path)
            temp_check, err_arr = check_empty_ceils(path)
            ### ------------------------------------ ###
            if temp_check == False:
                os.remove(path)
                errors = 'АУП: ' + aup + ' В документе не заполнены ячейки:' + ', '.join(err_arr)
                print(errors)
                return error(errors)
            ### ------------------------------------ ###

            # ### Проверка на целочисленность ЗЕТ у каждой дисциплины ###
            err_arr = check_smt(path)
            if err_arr != []:
                os.remove(path)
                errors = 'АУП: ' + aup + ' Ошибка при подсчете ЗЕТ:\n' + '\n'.join(err_arr)
                print(errors)
                return make_response(jsonify(errors), 400)
            # ### ------------------------------------ ###

            ### Компановка элективных курсов ###
            layout_of_disciplines(path)
            ### ---------------------------- ###

            # ### ------------------------------------ ###
            # ### Проверка, чтобы общая сумма ЗЕТ соответствовало норме (30 * кол-во семестров) ###
            check_zet, sum_normal, sum_zet = check_full_zet_in_plan(path)
            print(check_zet, sum_normal, sum_zet)
            if check_zet == False:
                os.remove(path)
                errors = 'АУП: ' + aup + ' В выгрузке общая сумма ЗЕТ не соответствует норме. Норма {} ЗЕТ. В карте {} ЗЕТ.'.format(sum_normal, sum_zet)
                print(errors)
                return make_response(jsonify(errors), 400)
            # ### ------------------------------------ ###

            get_aup = AUP.query.filter_by(num_aup = aup).first()
            if get_aup == None:
                
                aup = save_into_bd(path)
                aup = aup.num_aup
                
            else:
                files = path
                delete_from_workload(get_aup.num_aup)
                delete_from_workmap(get_aup.num_aup)
                if type(files) != list:
                    f = files
                    files = [f, ]

                for file in files:
                    update_workload(file, get_aup.num_aup)

                print(f"[!] such aup already in db. REDIRECT to {get_aup.num_aup}")

            os.remove(path)
            aup = AUP.query.filter_by(num_aup = aup).first()
            table, _,_ = Table(aup.num_aup)

            print(table)

            ### WORKMAP ###

            for i in range(0, len(table)):
                for j in range(0, len(table[i])):
                    new_raw = WorkMap(
                        id_aup = aup.id_aup,
                        discipline = table[i][j]['discipline'],
                        zet = table[i][j]['zet'],
                        num_col = i,
                        num_row = j,
                        disc_color = table[i][j]['module_color']
                    )
                    db.session.add(new_raw)
                    db.session.commit()
            
            return make_response(jsonify(''), 200)
        else:
            return make_response(jsonify('Произошла неизвестная ошибка'), 500)
    else: 
        return render_template("upload.html", form=form)


@app.route("/api/aup/<string:aup>")
@cross_origin()
def aupJSON(aup):
    table, legend, max_zet = Table(aup, colorSet=1)

    data = {
        'table':table,
        'max_zet':max_zet
    }

    return jsonify(data)

@app.route("/getAllMaps")
@cross_origin()
def getAllMaps():
    fac = GetAllFaculties()
    print(fac)
    li = list()
    for i in fac:
        simple_d = dict()
        simple_d["faculty_name"] = i.name_faculty
        maps = GetMaps(id=i.id_faculty)
        l = list()
        for j in maps:
            dd = dict()
            dd["map_id"] = j.num_aup
            name = str(j.file).split(" ")
            dd["map_name"] = " ".join(name[5:len(name)-4])
            l.append(dd)
        simple_d["data"] = l

        print()
        print()
        print(simple_d)
        print()
        print()

        li.append(simple_d)

    return jsonify(li)


# путь для загрузки сформированной КД
@app.route("/save_excel/<string:aup>", methods=["GET", "POST"])
@cross_origin()
def save_excel(aup):
    filename = saveMap(aup, app.static_folder, expo=60) 
    ### Upload xlxs file in memory and delete file from storage -----
    return_data = io.BytesIO()
    with open(filename, 'rb') as fo:
        return_data.write(fo.read())
    # (after writing, cursor will be at last byte, so move it to start)
    return_data.seek(0)

    # path = os.path.join(app.static_folder, 'temp', filename)
    os.remove(filename)
    ### --------------
    return send_file(return_data, 
            download_name=os.path.split(filename)[-1])



@app.route('/error')
def error(errors):
    return render_template('error.html', errors=errors)


# if __name__ == "__main__":
#     app.run(debug=True)
