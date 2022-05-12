import os
from flask import Flask, flash, redirect, url_for, render_template, request, send_file
from main import Table, saveMap, Header
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from sql_db  import MySQL
from start import start


class FileForm(FlaskForm):
    file = FileField(validators=[FileRequired(), FileAllowed(["xlsx", "xls"], "xlsx only!")])

app = Flask(__name__)
app.config.from_pyfile('config.py')

db = MySQL(app)

@app.route('/test/')
def test():
    cursor = db.connection.cursor(buffered=True)
    cursor.execute('SELECT * FROM tbl_aup')
    return str(cursor.fetchall())
    
ZET_HEIGHT = 50;
# filename = None

@app.route("/map/<string:aup>")
def main(aup):
    cursor = db.connection.cursor(buffered=True)
    table = Table(aup, cursor)
    

    if table != None:
        header = Header(aup, db.connection.cursor(buffered=True))    
        return render_template("base.html", table=table, header=header, zet=ZET_HEIGHT, aup=aup)
    else:
        return redirect('/load')


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


@app.route("/save/<string:aup>")
def save(aup):
    filename = saveMap(aup, db.connection.cursor(buffered=True)) 
    return send_file(
            path_or_file=app.static_folder + "\\temp\\" + filename, 
            download_name=filename) 


    


if __name__ == "__main__":
    app.run(debug=True)