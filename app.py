import io
import os

from flask import Flask, redirect, render_template, request, send_file, jsonify
from flask_migrate import Migrate
from sqlalchemy import MetaData

from excel_check import (check_empty_ceils, check_full_zet_in_plan, check_smt,
                         layout_of_disciplines)
from models import Module
from save_into_bd import delete_from_workload, save_into_bd, update_workload
from take_from_bd import GetAllFaculties, GetMaps, Header, Table, saveMap
from tools import FileForm

app = Flask(__name__)
application = app

app.config.from_pyfile('config.py')

convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

from models import WorkMap, db

metadata = MetaData(naming_convention=convention)
db.init_app(app)
migrate = Migrate(app, db)

from save_into_bd import bp as save_db_bp

app.register_blueprint(save_db_bp)

from models import AUP

ZET_HEIGHT = 90

@app.route('/', methods=["POST", "GET"])
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
def main(aup):
    table, legend, max_zet = Table(aup, colorSet=1)

    if table != None:
        header = Header(aup)    
        return render_template("base.html", table=table, header=header, zet=ZET_HEIGHT, aup=aup, max_zet=max_zet)
    else:
        return redirect('/load')

@app.route('/upload', methods=["POST", "GET"])
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
                return error(errors)
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
                return error(errors)
            # ### ------------------------------------ ###

            get_aup = AUP.query.filter_by(num_aup = aup).first()
            if get_aup == None:
                
                aup = save_into_bd(path)
                
            else:
                files = path
                delete_from_workload(aup)
                if type(files) != list:
                    f = files
                    files = [f, ]

                for file in files:
                    update_workload(file, aup)

                print(f"[!] such aup already in db. REDIRECT to {aup}")

            os.remove(path)

            table, _, _ = Table(aup)

            moduls = Module.query.all()
            d = dict()
            for i in moduls:
                d[i.id_module] = i.color
            print(d)
            
            print(table)

            for i in range(0, len(table)):
                for j in range(0, len(table[i])):
                    new_row = WorkMap(id_aup=aup, 
                                        id_group=None,
                                        id_module=table[i][j]['module_color'],
                                        discipline=table[i][j]['discipline'],
                                        zet=table[i][j]['zet'],
                                        num_col=i,
                                        num_row=j,
                                        disc_color=d[table[i][j]['module_color']])
                    print(new_row)
                    print()
                print()
                print()
                print()
            print()
            print()
            print()
            print(table)
            print()
            print()
            print()
            
            return redirect(f'/map/{aup}')
        else:
            return redirect('/load')
    else: 
        return render_template("upload.html", form=form)


@app.route("/api/aup/<string:aup>")
def aupJSON(aup):
    table, legend, max_zet = Table(aup, colorSet=1)

    data = {
        'table':table,
        'max_zet':max_zet
    }

    return jsonify(data)


# путь для загрузки сформированной КД
@app.route("/save/<string:aup>")
def save(aup):
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
