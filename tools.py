from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from flask import make_response, jsonify
from openpyxl import load_workbook

# # Условия фильтра, если добавлять категорию, то нужно исправить if
skiplist = {
    "discipline": [
        'Элективные дисциплины по физической культуре и спорту',
        'Элективные курсы по физической культуре и спорту', 
        'Элективная физическая культура',
        'Общая физическая подготовка',
        'Игровые виды спорта',
        'Неолимпийские виды спорта'
    ],

    "record_type": [
        "Факультативная",
        "Факультативные"
    ]
}

sems = ["Первый", "Второй", "Третий", "Четвертый", "Пятый", "Шестой",
            "Седьмой", "Восьмой", "Девятый", "Десятый", "Одиннадцатый", "Двенадцатый", 'Тринадцатый', 'Четырнадцатый']

class FileForm(FlaskForm):
    file = FileField(validators=[FileRequired(), FileAllowed(["xlsx", "xls"], "xlsx only!")])


def get_maximum_rows(*, sheet_object):  # Взять максимальное значение строк в плане
    rows = 0
    for max_row, row in enumerate(sheet_object, 1):
        if not all(col.value is None for col in row):
            rows += 1
    return rows


def take_aup_from_excel_file(file):
    wb = load_workbook(file)
    # ws = wb['Лист1']
    return wb['Лист1']['B2'].value


def error(errors):
    return make_response(jsonify(errors), 400)


def check_skiplist(zet_or_hours, value_discipline, value_record_type, value_block):
    if (zet_or_hours is not None and (
            len(list(filter(lambda x: x in value_discipline, skiplist['discipline']))) == 0 and
            len(list(filter(lambda x: x in value_record_type, skiplist['record_type']))) == 0 and
            len(list(filter(lambda x: x in value_block, skiplist['record_type']))) == 0)):
        return True
    else:
        return False
