from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed

class FileForm(FlaskForm):
    file = FileField(validators=[FileRequired(), FileAllowed(["xlsx", "xls"], "xlsx only!")])


def get_maximum_rows(*, sheet_object):  # Взять максимальное значение строк в плане
    rows = 0
    for max_row, row in enumerate(sheet_object, 1):
        if not all(col.value is None for col in row):
            rows += 1
    return rows
