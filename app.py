from fileinput import filename
import os
from pickle import NONE
from flask import Flask, flash, redirect, url_for, render_template, request, send_file
from main import Table, get_Table, saveMap 
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed


class FileForm(FlaskForm):
    file = FileField(validators=[FileRequired(), FileAllowed(["xlsx", "xls"], "xlsx only!")])

app = Flask(__name__)
WTF_CSRF_ENABLED = False;

OneZetHeight = 50;
# filename = None

@app.route("/map/<str:aup>")
def main(aup):
    table = Table(aup)    
    return render_template("base.html", table=table, zet=OneZetHeight, aup=aup)

    


# @app.route('/map/<aup>')
# def main():
#     global filename
#     mapname = ''
#     showDownloadBtn = False
#     if filename != None:
#         for directory in os.listdir(app.static_folder+"\\temp"):
#             if "КД" in directory:
#                 os.remove(path=app.static_folder + '\\temp\\' + directory)
#         table = get_Table(filenameMap=filename)
#         mapname = saveMap(filename)
#         os.remove(path=app.static_folder + '\\temp\\' + filename)
#         print(f"map name is {mapname}")
#         print(f"[Map Name] {mapname}")
#         # os.remove(app.static_folder + '\\temp\\' + mapname)
#         showDownloadBtn = True
#         filename = None
#     # elif mapname != "":
#     #     print("in elif")
#     #     table = get_Table(filenameMap=mapname)
#     else: 
#         showDownloadBtn = False
#         table = get_Table()
    
#     return render_template("base.html", table=table, zet=OneZetHeight, showDownloadBtn=showDownloadBtn, mapname=mapname)

@app.route('/upload', methods=["POST", "GET"])
def upload():
    form = FileForm(meta={'csrf':False})
    global filename 
    
    if request.method == "POST":
        if form.validate_on_submit():
            f = form.file.data
            filename = f.filename
            f.save(os.path.join(app.static_folder, 'temp', f.filename))
            return redirect('/')
        else:
            return redirect('/upload')
    
    else: 
        return render_template("upload.html", form=form)


@app.route("/save/<string:aup>")
def save(aup):
    saveMap(aup)
    return send_file(
            path_or_file=app.static_folder + "\\temp\\" + filename, 
            download_name=filename) 


    


if __name__ == "__main__":
    app.run(debug=True)