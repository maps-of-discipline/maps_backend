import json
import time
from functools import wraps

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

def timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        # first item in the args, ie `args[0]` is `self`
        print(f'[TIME]Function {func.__name__}() Took {total_time:.4f} seconds')
        return result
    return timeit_wrapper


# class FileForm(FlaskForm):
#     file = FileField(validators=[FileRequired(), FileAllowed(["xlsx", "xls"], "xlsx only!")])


def get_maximum_rows(*, sheet_object):  # Взять максимальное значение строк в плане
    rows = 0
    for max_row, row in enumerate(sheet_object, 1):
        if not all(col.value is None for col in row):
            rows += 1
    return rows


def take_aup_from_excel_file(file):
    wb = load_workbook(file)
    # ws = wb['Лист1']
    value = wb['Лист1']['B2'].value
    wb.save(file)
    return str(value)

def error(errors):
    return make_response(json.dumps(errors, ensure_ascii=False), 400)


def check_skiplist(zet_or_hours, value_discipline, value_record_type, value_block):
    if (zet_or_hours is not None and (
            len(list(filter(lambda x: x in value_discipline, skiplist['discipline']))) == 0 and
            len(list(filter(lambda x: x in value_record_type, skiplist['record_type']))) == 0 and
            len(list(filter(lambda x: x in value_block, skiplist['record_type']))) == 0)):
        return True
    else:
        return False


