import json
from numpy import unpackbits
import xlsxwriter
import openpyxl
from openpyxl.styles import PatternFill, Border, Side, Alignment, Font, NamedStyle
import sys, os, datetime
from start import *
from pprint import pprint


def saveMap(aup, cursor):
    
    cur = cursor

    cur.execute("SELECT id_aup, file FROM tbl_aup WHERE num_aup LIKE %s", (aup,))
    id_aup, filename_map = cursor.fetchall()[0]
    filename_map = 'static/temp/' + "КД " + filename_map

    date = select_to_DataBase(cur, id_aup)
    ws, wk = CreateMap(filename_map)
    adr_cell = "B"
    buf = "Первый семестр"
    row = 3
    i = -1
    modul = set()
    max_row = 0
    sum_row = 0
    while i < len(date) - 1:
        i += 1
        date_dist = date[i]
        if date_dist[2] == buf and date_dist[3] != 0:
            ws["A" + str(row)] = row - 2
            ws["A" + str(row)].style = 'standart'
            modul.add(str(date_dist[0])[2:])
            dip = adr_cell + str(row) + ':' + adr_cell + str(row + date_dist[3] - 1)
            ws[adr_cell + str(row)].style = 'standart'
            ws[adr_cell + str(row)] = date_dist[1]
            cell = ws[adr_cell + str(row)]
            splitted = str(date_dist[0]).split()
            color = select_color(cur, splitted[-1])
            cell.fill = openpyxl.styles.PatternFill(start_color=str(color), end_color=str(color), fill_type='solid')
            ws.merge_cells(dip)
            row += date_dist[3] - 1
            buf = date_dist[2]
            row += 1
            max_row = max(max_row, row)
        elif date_dist[3] != 0:
            adr_cell = chr(ord(adr_cell) + 1)
            ws[adr_cell + str(2)] = str(ord(adr_cell) - 65) + " семестр"
            ws[adr_cell + str(2)].style = 'standart'
            buf = date_dist[2]
            sum_row += row -3
            row = 3
            i -= 1
    print(sum_row + row)
    ws.merge_cells('A1:' + adr_cell + '1')
    ws['A1'] = 'КАРТА ДИСЦИПЛИН'
    ws['A1'].style = 'standart'
    ws['A1'].font = Font(bold=True, size=12)
    for col in range(3, max_row):
        ws["A" + str(col)] = col - 2
        ws["A" + str(col)].style = 'standart'
        ws.row_dimensions[col].height = 25


    # TODO fix if need  
    # create_directory_of_modul(ws, modul, cur)
    wk.save(filename=filename_map)

    cur.close()
    del cur
    print("Отключение от базы данных")
    filename_map = filename_map.split('/')[-1]
    return filename_map 


def Header(aup, Cursor):
    # cursor, connection = connect_to_DateBase(FULLNAME_DB)

    cursor = Cursor

    cursor.execute('SELECT id_op FROM tbl_aup WHERE num_aup LIKE %s', (aup,))
    id_op = cursor.fetchall()[0][0]

    cursor.execute('SELECT year_begin, program_code, id_spec, id_form FROM tbl_op WHERE id_op LIKE %s', (id_op,))
    (year_begin, program_code, id_spec, id_form) = cursor.fetchall()[0]
    
    cursor.execute('SELECT name_okco FROM spr_okco WHERE program_code LIKE %s', (program_code,))
    program = program_code + " " + cursor.fetchall()[0][0]
    
    cursor.execute('SELECT name_spec FROM spr_specialization WHERE id_spec LIKE %s', (id_spec,))
    spec = cursor.fetchall()[0][0]

    cursor.execute('SELECT form FROM spr_form_education WHERE id_form LIKE %s', (id_form,))
    form = cursor.fetchall()[0][0] + " форма обучения"

    cursor.close()
    del cursor

    return [program, spec, year_begin, form]


def colorize(table):
    colorset = [
        '#19535F',
        '#0B7A75',
        '#7B2D26',
        '#2AB7CA',
        '#FE4A49',
        '#84596B',
        '#574D68',
        '#A38560',
        '#7EA172',
        '#E7A977',
        '#80475E',
        '#CC5A71',
        '#F0F757',
        '#3B7080',
        '#C97064',
    ]

    unique_modules = []
    for i in table:
        for j in i:
            if not j["module_color"] in unique_modules:
                unique_modules.append(j["module_color"])
    
    unique_modules = list(map(lambda x: [x,0], unique_modules))
    
    if len(unique_modules) > 1:
        
        for i in range(len(table)):
            checked = []
            for j in range(len(table[i])):
                if table[i][j]["module_color"] in checked:
                    continue
                checked.append(table[i][j]["module_color"])
                
                for k in range(len(unique_modules)):
                    if unique_modules[k][0] == table[i][j]["module_color"]:
                        unique_modules[k][1] += 1
                
        t = {}
        for el in unique_modules:
            t.update({str(el[0]) : el[1]})
        unique_modules = t

        for i in range(len(table)):
            for j in range(len(table[i])):
                table[i][j].update({"count": unique_modules[str(table[i][j]['module_color'])]})  

        
        for i in range(len(table)):
            table[i].sort(key=lambda x: (x["count"], x["module_color"]), reverse=True)
            j = 0
            swapped = 0
            while j < len(table[i]) - swapped:
                if table[i][j]["module_color"] == 4:
                    table[i][j]["module_color"] = colorset[list(unique_modules.keys()).index(str(table[i][j]["module_color"]))]
                    table[i].append(table[i].pop(j))
                    j -= 1 
                    swapped += 1
                else:
                    table[i][j]["module_color"] = colorset[list(unique_modules.keys()).index(str(table[i][j]["module_color"]))]
                j += 1
                                    
    pprint(table[1])
    return table

        
def Table(aup, Cursor):
    sems = ["Первый", "Второй", "Третий", "Четвертый", "Пятый", "Шестой", "Седьмой", "Восьмой", "Девятый", "Десятый", "Одиннадцатый", "Двенадцатый"]
    
    # Условия фильтра, если добавлять категорию, то нужно исправить if 
    skiplist = {
        "discipline": [
            'Физическая культура и спорт', 
            'Элективные дисциплины по физической культуре и спорту', 
            'Элективные курсы по физической культуре и спорту', 
        ],
        "record_type": []
    }

    cursor = Cursor

    cursor.execute('SELECT id_aup FROM tbl_aup WHERE num_aup LIKE %s', (aup,))
    id_aup = cursor.fetchall()
    
    if id_aup == []:
        print("There is no such aup in data base")
        return None
    else:
        id_aup = id_aup[0][0]

    cursor.execute("SELECT id_module, record_type, discipline, period, zet FROM workload WHERE id_aup LIKE %s ORDER BY record_type, discipline, period", (id_aup,))
    workload = cursor.fetchall()

    previous = None
    zet = 0.0
    sumzet = 0.0
    table = []
    for item in workload:
        moduleID, record_type, discipline, period, zet = item
        
        # Фильтрация, тут исправлять if
        if discipline in skiplist["discipline"] or record_type in skiplist['record_type']:
            continue
        

        sumzet += zet 
        period = period.split()[0]
        
        cell = {
            "module_color": moduleID,
            "discipline": discipline, 
            "term": period, 
            "zet": zet   
        }

        
        delta = len(table) - sems.index(period) - 1
        if delta < 0:
            for i in range(-delta):
                table.append([])
        
        for el in table[sems.index(period)]: 
            if el['discipline'] == discipline:
                el["zet"] += zet
                break
        else:
            table[sems.index(period)].append(cell)
    print("[DEBUG] sumzet = ", sumzet)
    # return json.dumps(colorize(table), ensure_ascii=False)
    return colorize(table)


def sort_modul(date):
    buf = "Первый семестр"
    full_data = []
    for i in range(len(date)):
        date_dist = date[i]
        if date_dist[2] != buf:
            full_data += sorted(date[len(full_data):i])
            buf = date_dist[2]
    full_data += sorted(date[len(full_data):i + 1])
    return full_data


# функция делает запрос в базу данных и выводит нужные значения для дальнейшего вывода в карту
# (мудуль, дисциплина, семестр, зеты(складывая все за одну дисц)), на выходу лист из листов в каждом из которых находятся данные
def select_to_DataBase(cur, id_aup):
    set = []
    sem = ["Первый", "Второй", "Третий", "Четвертый", "Пятый", "Шестой", "Седьмой", "Восьмой", "Девятый", "Десятый", "Одиннадцатый", "Двенадцатый" ]
    data = []
    buf = ""
    zet = 0.0
    j = -1
    sum_zet = 0
    print(F"id_aup = {id_aup}")
    for i in range(len(sem)):
        cur.execute('SELECT `id_module`, `discipline`, `period`, `zet`, `block`, `record_type` FROM workload WHERE `period` LIKE %s AND id_aup = %s', (sem[i] + " семестр", id_aup,))
        rows = cur.fetchall()
        # print(rows)
        for row in rows:
            if buf != row[1]:
                buf = row[1]
                data.append(str(row[4]) + " " + str(row[0]))
                data.append(row[1])
                data.append(row[2])
                set.append(data.copy())
                data_rev = set[j]

                if data_rev[1] == "Элективные курсы по физической культуре и спорту" or data_rev[1] == "Элективные дисциплины по физической культуре и спорту":
                    zet = 0
                if len(data_rev) == 3:
                    data_rev.append(round(zet))
                    set[j] = data_rev.copy()
                else:
                    data_rev[3] = int(zet)
                    set[j] = data_rev.copy()
                sum_zet += zet
                zet = 0.0
                j += 1
            if row[3] != None and row[5] != "Факультативная":
                zet += float(row[3])
            data.clear()
    # print(set)
    data_rev = set[-1]
    # print("[DEBUG]", zet, round(zet))
    data_rev.append(round(zet))
    set[-1] = data_rev.copy()
    set = sort_modul(set)
    print(sum_zet)
    return set


def select_color(cur, modul):
    cur.execute('SELECT Color FROM tbl_module WHERE ID_module LIKE %s', (modul,))
    return cur.fetchall()[0][0]
    

def create_directory_of_modul(ws, modul, cur):
    adr_cell = "B"
    row = 50
    modul = list(modul)
    for i in range(len(modul)):
        dip = adr_cell + str(row) + ':' + adr_cell + str(row + 1)
        cur.execute(
            f'SELECT Name_module  FROM tbl_module WHERE ID_module LIKE {modul[i]}')
        modul_buf = ''
        for r in cur.fetchall():
            modul_buf = (r[0])
        ws[adr_cell + str(row)] = modul_buf
        ws[adr_cell + str(row)].style = 'standart'
        cell = ws[adr_cell + str(row)]
        color = select_color(cur, modul[i])
        cell.fill = openpyxl.styles.PatternFill(start_color=str(color), end_color=str(color), fill_type='solid')
        ws.merge_cells(dip)
        row +=2


# функция создает карту и задаем все данные кроме предметов в семестрах, на вход требует имя карты
def CreateMap(filename_map):
    wk = xlsxwriter.Workbook(filename_map)
    ws = wk.add_worksheet()
    ws.set_column(1, 40, 40)
    wk.close()
    workbook = openpyxl.load_workbook(filename_map)
    worksheet = workbook.active
    ns = NamedStyle(name='standart')
    ns.font = Font(bold=False, size=12)
    border = Side(style='medium', color='000000')
    ns.border = Border(left=border, top=border, right=border, bottom=border)
    ns.alignment = Alignment(horizontal='center', vertical='center', wrapText=True)
    workbook.add_named_style(ns)
    worksheet.row_dimensions[1].height = 50
    worksheet.row_dimensions[2].height = 20
    worksheet["A2"] = "З.Е."
    worksheet['A2'].style = 'standart'
    for col in range(3, 34):
        worksheet["A" + str(col)] = col - 2
        worksheet["A" + str(col)].style = 'standart'
    for col in range(ord('B'), ord('C')):
        worksheet[chr(col) + str(2)] = str(col - 65) + " семестр"
        worksheet[chr(col) + str(2)].style = 'standart'
    return worksheet, workbook


# заполняем данные, размер и цвет  в ячейках карты,
# Так же мы красим предметы в соответствии с модулем
# def filling_map(fullname_db, filename_map, name_map):
#     # cur, conn = connect_to_DateBase(fullname_db)
#     cur = Connect()
#     cur.execute(f'SELECT ID_OP FROM OP WHERE Name_OP LIKE {name_map}') 
#     id_op = cur.fetchall()[0][0]
#     date = select_to_DataBase(cur, id_op)
#     ws, wk = CreateMap(filename_map)
#     adr_cell = "B"
#     buf = "Первый семестр"
#     row = 3
#     i = -1
#     modul = set()
#     max_row = 0
#     sum_row = 0
#     while i < len(date) - 1:
#         i += 1
#         date_dist = date[i]
#         if date_dist[2] == buf and date_dist[3] != 0:
#             ws["A" + str(row)] = row - 2
#             ws["A" + str(row)].style = 'standart'
#             modul.add(str(date_dist[0])[2:])
#             dip = adr_cell + str(row) + ':' + adr_cell + str(row + date_dist[3] - 1)
#             ws[adr_cell + str(row)].style = 'standart'
#             ws[adr_cell + str(row)] = date_dist[1]
#             cell = ws[adr_cell + str(row)]
#             color = select_color(cur, str(date_dist[0])[2:])
#             cell.fill = openpyxl.styles.PatternFill(start_color=str(color), end_color=str(color), fill_type='solid')
#             ws.merge_cells(dip)
#             row += date_dist[3] - 1
#             buf = date_dist[2]
#             row += 1
#             max_row = max(max_row, row)
#         elif date_dist[3] != 0:
#             adr_cell = chr(ord(adr_cell) + 1)
#             ws[adr_cell + str(2)] = str(ord(adr_cell) - 65) + " семестр"
#             ws[adr_cell + str(2)].style = 'standart'
#             buf = date_dist[2]
#             sum_row += row -3
#             row = 3
#             i -= 1
#     print(sum_row + row)
#     ws.merge_cells('A1:' + adr_cell +'1')
#     ws['A1'] = 'КАРТА ДИСЦИПЛИН'
#     ws['A1'].style = 'standart'
#     ws['A1'].font = Font(bold=True, size=12)
#     for col in range(3, max_row):
#         ws["A" + str(col)] = col - 2
#         ws["A" + str(col)].style = 'standart'
#         ws.row_dimensions[col].height = 25
#     create_directory_of_modul(ws, modul, cur)
#     wk.save(filename=filename_map)

#     cur.close()
#     del cur
#     # conn.close()
#     print("Отключение от базы данных")



if __name__ == "__main__":
    # main()
    # print(Table('000016957'))
    # Header('000016957')
    # cur, conn = connect_to_DateBase('C:\\Users\\Dezzy\\Documents\\GitHub\\PD_EP_spring2022(1)\\db.accdb')
    # print(select_to_DataBase(cur, 3))
    # saveMap('000016957')
    # file = '29.03.03_2022_Технологии упаковочного производства.xlsx'
    # saveMap(file)
    # get_Table()
    pass
