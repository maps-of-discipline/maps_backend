import time
from functools import wraps

import pandas as pd
from flask import make_response
from openpyxl import load_workbook

# from maps.logic.take_from_bd import (blocks, blocks_r, period, period_r, control_type, control_type_r,
#                                      ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r)
from maps.models import AupData

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
        print(f'\033[94m[TIME]\033[0m Function \033[96m{func.__name__: <32}()\033[0m Took {total_time:.4f} seconds')
        return result

    return timeit_wrapper


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


def check_skiplist(zet_or_hours, value_discipline, value_record_type, value_block):
    return zet_or_hours is not None and (
            len(list(filter(lambda x: x in value_discipline, skiplist['discipline']))) == 0 and
            len(list(filter(lambda x: x in value_record_type, skiplist['record_type']))) == 0 and
            len(list(filter(lambda x: x in value_block, skiplist['record_type']))) == 0)


def prepare_shifr(shifr):
    if len(shifr) > 2 and shifr[1] == '.':
        # Если второй символ - точка, удалить её
        return shifr[:1] + shifr[2:]
    else:
        # В противном случае вернуть оригинальную строку
        return shifr


def check_sum_zet_in_type(data):
    for item in data:
        sum_zet_type = 0
        for i in item['type']:
            sum_zet_type += i['zet']
        if sum_zet_type == 0: return False

@timeit
def getAupInfo(file, filename):
    data = pd.read_excel(file, sheet_name='Лист1')
    aupInfo = dict()
    data = data['Содержание']
    #                     Наименование
    # 0                     Номер АУП
    # 1               Вид образования
    # 2           Уровень образования
    # 3   Направление (специальность)
    # 4             Код специальности
    # 5                  Квалификация
    # 6       Профиль (специализация)
    # 7                 Тип стандарта
    # 8                     Факультет
    # 9           Выпускающая кафедра
    # 10               Форма обучения
    # 11                   Год набора
    # 12              Период обучения
    # 13                      На базе
    # 14    Фактический срок обучения
    aupInfo["num"] = data[0]
    aupInfo["type_education"] = data[1]
    aupInfo["degree"] = data[2]
    aupInfo["direction"] = data[3]
    aupInfo["program_code"] = data[4]
    aupInfo["qualification"] = data[5]
    aupInfo["name_spec"] = data[6]
    aupInfo["type_standard"] = data[7]
    aupInfo["name_faculty"] = data[8]
    aupInfo["department"] = data[9]
    aupInfo["form_educ"] = data[10]
    aupInfo["years_begin"] = data[11]
    aupInfo["period_edication"] = data[12]
    aupInfo["base"] = data[13]
    aupInfo["full_years"] = data[14]
    aupInfo["filename"] = filename
    return aupInfo


def save_loop(i, in_type, l, request_data):
    for j in range(0, len(request_data[i]['type'][in_type])):
        try:
            row = AupData.query.filter_by(
                id=request_data[i]['type'][in_type][j]['id']).first()

            row.discipline = request_data[i]['discipline']
            row.amount = request_data[i]['type'][in_type][j]['amount'] * 100
            row.id_edizm = 1 if request_data[i]['type'][in_type][j]['amount_type'] == 'hour' else 2
            row.control_type_id = request_data[i]['type'][in_type][j]['control_type_id']
            row.id_period = request_data[i]['num_col'] + 1
            row.num_row = request_data[i]['num_row']
            row.id_group = request_data[i]['id_group']
            row.id_block = request_data[i]['id_block']
            row.id_module = request_data[i]['id_module']
            row.id_part = request_data[i]['id_part']
            row.shifr = prepare_shifr(request_data[i]['shifr'])
            l.append(row)
        except:
            return make_response('Save error', 400)


def get_grouped_disciplines(aup_data) -> dict[tuple[str, int], list[AupData]]:
    """
        Функция для группировки aupData по дисциплине и периоду.
        Возвращает словарь:
            key - кортеж (Дисциплина, ID периода)
            value - список объектов AupData
    """

    grouped_disciplines = {}

    for el in aup_data:
        el: AupData

        key = (el.discipline, el.id_period)
        if key not in grouped_disciplines:
            grouped_disciplines.update({key: [el]})
        else:
            grouped_disciplines[key].append(el)

    return grouped_disciplines
