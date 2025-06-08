import time
from functools import wraps

import pandas as pd
from openpyxl import load_workbook

from maps.models import AupData
import config 

# Условия фильтра, если добавлять категорию, то нужно исправить if
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

# Заменил числовые семестры на строковые идентификаторы
SEMESTERS = {
    "first": "Первый",
    "second": "Второй",
    "third": "Третий",
    "fourth": "Четвертый",
    "fifth": "Пятый",
    "sixth": "Шестой",
    "seventh": "Седьмой",
    "eighth": "Восьмой",
    "ninth": "Девятый",
    "tenth": "Десятый",
    "eleventh": "Одиннадцатый",
    "twelfth": "Двенадцатый",
    "thirteenth": "Тринадцатый",
    "fourteenth": "Четырнадцатый"
}

# Константы для единиц измерения
UNITS = {
    "zet": "ЗЕТ",
    "hours": "часы",
    "contact_hours": "контактные часы",
    "independent_work": "самостоятельная работа"
}

def timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)

        if not config.SHOW_DEBUG_EXECUTION_TIME:
            return result

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


def get_grouped_disciplines(aup_data) -> dict[tuple[str, str], list[AupData]]:
    """
        Функция для группировки aupData по дисциплине и периоду.
        Возвращает словарь:
            key - кортеж (Дисциплина, название периода)
            value - список объектов AupData
    """
    grouped_disciplines = {}

    for el in aup_data:
        el: AupData

        # Используем строковый идентификатор периода вместо id
        period_name = SEMESTERS.get(f"semester_{el.id_period}", f"Unknown_{el.id_period}")
        key = (el.discipline.title, period_name)
        
        if key not in grouped_disciplines:
            grouped_disciplines.update({key: [el]})
        else:
            grouped_disciplines[key].append(el)

    return grouped_disciplines