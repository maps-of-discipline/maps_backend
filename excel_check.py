from collections import defaultdict

from openpyxl import load_workbook

from models import SprStandard, SprVolumeDegreeZET
from take_from_bd import skiplist


def check_smt(file):
    wb = load_workbook(file)
    ws = wb['Лист2']
    max_row = get_maximum_rows(sheet_object=ws)
    d = defaultdict(list)
    for i in range(2, max_row):
        sem = ws['G'+str(i)].value
        proj = ws['F'+str(i)].value
        zet = ws['K'+str(i)].value
        if zet:
            d[sem].append([proj, zet])
    for key, value in d.items():
        print()
        print("{0}: {1}".format(key,value))
    
    for key, value in d.items():
        ddd = dict()
        for i in range(0, len(value)):
            if ddd.get(value[i][0]):
                ddd[value[i][0]] += float(value[i][1].replace(",", "."))
            else:
                ddd[value[i][0]] = float(value[i][1].replace(",", "."))
        for key1, value1 in ddd.items():
            if not value1.is_integer() and key1 not in skiplist['discipline']:
                # print("Ошибка при подсчёте ZET. {0}: {1} {2}".format(key,key1, value1))
                return "Ошибка при подсчёте ZET. {0}: {1} {2}".format(key,key1, value1)
    return None



def get_maximum_rows(*, sheet_object):  # Взять максимальное значение строк в плане
    rows = 0
    for max_row, row in enumerate(sheet_object, 1):
        if not all(col.value is None for col in row):
            rows += 1
    return rows


def check_empty_ceils(file):  # Проверка на пустые обязательные ячейки
    wb = load_workbook(file)
    ws = wb['Лист2']
    max_row = get_maximum_rows(sheet_object=ws)
    err_arr = []
    for letter in 'ABCEFGH':
        for num in range(1, max_row + 1):
            if ws[letter+str(num)].value == None:
                err_arr.append(letter+str(num))
    if err_arr == []:
        return True, err_arr
    else:
        return False, err_arr


def layout_of_disciplines(file):  # Компоновка элективных дисциплин по семестрам
    wb = load_workbook(file)
    ws = wb['Лист2']
    max_row = get_maximum_rows(sheet_object=ws)
    for num in range(1, max_row + 1):
        if 'Элективные дисциплины' in ws['E'+str(num)].value:
            temp_num = ws['E'+str(num)].value
            temp_value = ws['F'+str(num)].value
            count = 0
            for i in range(num, max_row + 1):
                count += 1
                if ws['E'+str(i)].value == temp_num and ws['F'+str(i)].value != temp_value:
                    for j in range(1, count):
                        ws['F'+str(i-j)] = temp_value + ' / ' + \
                            ws['F'+str(i+(j-1))].value
                        ws['F'+str(i+(j-1))] = 'None'
                        ws['E'+str(i+(j-1))] = 'None'
    for num in range(1, max_row + 1):
        if ws['E'+str(num)].value == 'None':
            ws.delete_rows(num)
    for num in range(1, max_row + 1):
        if ws['E'+str(num)].value == 'None':
            ws.delete_rows(num)
    wb.save(file)


# Проверка, чтобы общая сумма ЗЕТ соответствовало норме (30 * кол-во семестров)
def check_full_zet_in_plan(file):
    wb = load_workbook(file)
    ws = wb['Лист2']
    column_semester = ws['G']
    column_zet = ws['K']
    column_record_type = ws['E']
    column_discipline = ws['F']
    temp_list = []
    for i in range(1, len(column_semester)):
        if column_semester[i].value not in temp_list:
            temp_list.append(column_semester[i].value)

    ws = wb['Лист1']
    program_code = ws['B6'].value
    standard = format_standard(ws['B9'].value)
    id_standard = SprStandard.query.filter_by(type_standard = standard).first().id_standard

    
    select = SprVolumeDegreeZET.query.filter_by(program_code=program_code, id_standard=id_standard).first()
    sum_normal = select.zet


    sum_zet = 0
    for i in range(1, len(column_zet)):
        if (column_zet[i].value is not None and (
                len(list(filter(lambda x: x in column_discipline[i].value, skiplist['discipline']))) == 0 and
                len(list(filter(lambda x: x in column_record_type[i].value, skiplist['record_type']))) == 0)):
            
            sum_zet += float(column_zet[i].value.replace(',', '.'))
    
    print(sum_normal == sum_zet, 'normal:', sum_normal, '\nzet:', sum_zet)
    if sum_normal == sum_zet:
        return True, None, None
    else:
        return False, sum_normal, sum_zet


def format_standard(standard):
    if standard == 'ФГОС3++' or standard == 'ФГОС ВО (3++)':
        standard = 'ФГОС ВО 3++'
    return standard