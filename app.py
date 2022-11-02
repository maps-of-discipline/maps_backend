import io
import os

from flask import Flask, redirect, render_template, request, send_file, after_this_request
from flask_migrate import Migrate
from sqlalchemy import MetaData
from excel_check import (check_empty_ceils, check_full_zet_in_plan,
                         layout_of_disciplines)
from save_into_bd import save_into_bd, delete_from_workload, update_workload
from take_from_bd import Header, Table, saveMap
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

from models import db

metadata = MetaData(naming_convention=convention)
db.init_app(app)
migrate = Migrate(app, db)

from save_into_bd import bp as save_db_bp

app.register_blueprint(save_db_bp)

from models import AUP

ZET_HEIGHT = 90

@app.route('/')
def index():
    return render_template('index.html')

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
                errors = 'В документе не заполнены ячейки:' + ', '.join(err_arr)
                return error(errors)
            ### ------------------------------------ ###
            ### Компановка элективных курсов ###
            layout_of_disciplines(path)
            ### ---------------------------- ###

            # ### ------------------------------------ ###
            # ### Проверка, чтобы общая сумма ЗЕТ соответствовало норме (30 * кол-во семестров) ###
            check_zet, sum_normal, sum_zet = check_full_zet_in_plan(path)
            print(check_zet, sum_normal, sum_zet)
            if check_zet == False:
                os.remove(path)
                errors = 'В выгрузке общая сумма ЗЕТ не соответствует норме. Норма {} ЗЕТ. В карте {} ЗЕТ.'.format(sum_normal, sum_zet)
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
            
            return redirect(f'/map/{aup}')
        else:
            return redirect('/load')
    else: 
        return render_template("upload.html", form=form)


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
