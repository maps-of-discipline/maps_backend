import os
from pprint import pprint
from flask import Flask, flash, redirect, url_for, render_template, request, send_file
from main import  Table, saveMap, Header, saveMap
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from sql_db  import MySQL
from start import start


# форма для загрузки файла 
class FileForm(FlaskForm):
    file = FileField(validators=[FileRequired(), FileAllowed(["xlsx", "xls"], "xlsx only!")])


ZET_HEIGHT = 50;


app = Flask(__name__)
application = app
app.config.from_pyfile('config.py')
db = MySQL(app)


@app.route('/test/')
def test():
    cursor = db.connection.cursor(buffered=True)
    return "json.dumps(Table('000018048', cursor))"
    

# доменный путь к карте 
@app.route("/map/<string:aup>")
def main(aup):
    cursor = db.connection.cursor(buffered=True)
    table, legend = Table(aup, cursor, colorSet=1)

    if table != None:
        header = Header(aup, db.connection.cursor(buffered=True))    
        return render_template("base.html", table=table, header=header, zet=ZET_HEIGHT, aup=aup)
    else:
        return redirect('/load')


# доменный путь к форме загрузки 
@app.route('/load', methods=["POST", "GET"])
def upload():
    form = FileForm(meta={'csrf':False})
    
    if request.method == "POST":
        if form.validate_on_submit():
            f = form.file.data
            aup = f.filename.split(' - ')[1].strip()
            path = os.path.join(app.static_folder, 'temp', f.filename)
            
            cursor = db.connection.cursor()
            cursor.execute('SELECT id_aup FROM tbl_aup WHERE num_aup LIKE %s', (aup,))

            if cursor.fetchall() == []:
                f.save(path)
                start(path, db.connection.cursor(buffered=True))
                db.connection.commit()
                os.remove(path)
            else:
                print(f"[!] such aup already in db. REDIRECT to {aup}")

            return redirect(f'/map/{aup}')
        else:
            return redirect('/load')
    else: 
        return render_template("upload.html", form=form)


# путь для загрузки сформированной КД
@app.route("/save/<string:aup>")
def save(aup):
    filename = saveMap(aup, db.connection.cursor(buffered=True), app.static_folder, expo=60) 
    return send_file(
            path_or_file=filename, 
            download_name=os.path.split(filename)[-1]) 


    


if __name__ == "__main__":
    app.run(debug=True)