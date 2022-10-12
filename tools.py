from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed

class FileForm(FlaskForm):
    file = FileField(validators=[FileRequired(), FileAllowed(["xlsx", "xls"], "xlsx only!")])