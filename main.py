from shutil import ExecError
import xlsxwriter
import openpyxl
from openpyxl.styles import PatternFill, Border, Side, Alignment, Font, NamedStyle
import sys, os, datetime
from start import *


FULLNAME_DB = 'C:\\Users\\Dezzy\\Documents\\GitHub\\PD_EP_spring2022(1)\\db.accdb'




def saveMap(aup, cursor):
    # fullname_db = 'C:\\Users\\Dezzy\\Documents\\GitHub\\PD_EP_spring2022(1)\\db.accdb'
    # cur, conn = connect_to_DateBase(fullname_db)
    
    cur = cursor

    id_aup, filename_map = cur.execute(f"SELECT id_aup, file FROM tbl_aup WHERE num_aup LIKE {aup}").fetchall()[0]
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

    cursor.execute(f'SELECT id_op FROM tbl_aup WHERE num_aup LIKE {aup}')
    id_op = cursor.fetchall()[0][0]

    cursor.execute(f'SELECT year_begin, program_code, id_spec, id_form FROM tbl_op WHERE id_op LIKE {id_op}')
    (year_begin, program_code, id_spec, id_form) = cursor.fetchall()[0]
    
    cursor.execute(f'SELECT name_okco FROM spr_okco WHERE program_code LIKE {program_code}')
    program = program_code + " " + cursor.fetchall()[0][0]
    
    cursor.execute(f'SELECT name_spec FROM spr_specializationialization WHERE id_spec LIKE {id_spec}')
    spec = cursor.fetchall()[0][0]

    cursor.execute(f'SELECT form FROM spr_form_education WHERE id_form LIKE {id_form}')
    form = cursor.fetchall()[0][0] + " форма обучения"

    cursor.close()
    del cursor

    return [program, spec, year_begin, form]


def Table(aup, Cursor):
    sems = ["Первый", "Второй", "Третий", "Четвертый", "Пятый", "Шестой", "Седьмой", "Восьмой", ]
    # print(aup)
    # cursor, connection = connect_to_DateBase(FULLNAME_DB)

    cursor = Cursor

    
    print("[DEBUG] aup = ", aup)
    cursor.execute('SELECT id_aup FROM tbl_aup WHERE num_aup LIKE %s', (aup,))
    id_aup = cursor.fetchall()
    
    if id_aup == []:
        print("There is no such aup in data base", e)
        return None
    else:
        id_aup = id_aup[0][0]
    
    print("[DEBUG] id_aup = ", id_aup)
    
    data = select_to_DataBase(cursor, id_aup)
    cell_list = []

    for el in data:
        c = { 
        "module_color": "#" + select_color(cursor, el[0].split(" ")[-1]), 
        "discipline": ' '.join(el[1].split()), 
        "term": el[2], 
        "zet": el[3]
        }
        if c['zet'] == 0:
            continue
        cell_list.append(c)

    table = []
    for i in range(0,8):
        temp_list = []

        for el in cell_list:
            if el["term"] == sems[i] + ' семестр':
                temp_list.append(el)
        table.append(temp_list)

    cursor.close()
    del cursor
    return table
    



# def get_Table(filenameMap=None):

#     fullname_db = resource_path('db.accdb')
    
#     sem = ["Первый", "Второй", "Третий", "Четвертый", "Пятый", "Шестой", "Седьмой", "Восьмой", ]
#     cursor, conn = connect_to_DateBase(fullname_db=fullname_db)
    

#     if filenameMap == None:
#         data = select_to_DataBase(cursor, 20)
#     else:
#         filenameMap = filenameMap.split('.xl')[0]
#         cursor.execute('SELECT id_op FROM tbl_op WHERE Name_OP LIKE ?', [filenameMap]) #TODO fix name_op 
#         id_op = cursor.fetchall()[0][0]
#         data = select_to_DataBase(cursor, id_op)
        

#     cell_list = []

#     for el in data:
#         modul_id = el[0].split(" ")[1]
#         c = { 
#         "module_color": "#" + select_color(cursor, modul_id), 
#         "discipline": el[1], 
#         "term": el[2], 
#         "zet": el[3]
#         }
#         if c['zet'] == 0:
#             continue
#         cell_list.append(c)

#     table = []
#     for i in range(0,8):
#         temp_list = []

#         for el in cell_list:
#             if el["term"] == sem[i] + ' семестр':
#                 temp_list.append(el)

#         table.append(temp_list)

#     return table




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

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# основная функция-связующая все части и вводит основные параметры всего
# def main():
#     try:
#         file = "29.03.03_2022_Технологии упаковочного производства.xlsx"
#         filepath  = "static\\temp\\" + file
#         fullname_db = resource_path('db.mdb')
#         print("[check filepath]" + filepath)
#         start(file=filepath, fullname_db=fullname_db)
#         day_time = datetime.datetime.now()
#         day_time = " от " + str(day_time)[:16].replace("-", ".").replace(":", "-")
#         filename_map = "static\\temp\\" + 'КД ' + file[0:-5] + day_time + '.xlsx'
#         filling_map(fullname_db, filename_map, file[0:-5])
#         print('Программа успешно завершила свою работу!')
#         # main()
#     except Exception as ex:
#         print(ex)
#         input()


if __name__ == "__main__":
    # main()
    # print(Table('000016957'))
    Header('000016957')
    # cur, conn = connect_to_DateBase('C:\\Users\\Dezzy\\Documents\\GitHub\\PD_EP_spring2022(1)\\db.accdb')
    # print(select_to_DataBase(cur, 3))
    # saveMap('000016957')
    # file = '29.03.03_2022_Технологии упаковочного производства.xlsx'
    # saveMap(file)
    # get_Table()
