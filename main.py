from pyexpat import model
import random

import xlsxwriter
import openpyxl
from openpyxl.styles import PatternFill, Border, Side, Alignment, Protection, Font, NamedStyle

import pyodbc


# функция подключения к базе данных, на вход требует путь к базе данных возвращает курсор, который указывает на БД

def connect_to_DateBase(fullname_db):
    try:
        conn_string = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + fullname_db
        conn = pyodbc.connect(conn_string)
        cursor = conn.cursor()
        print("Connected To Database")
        return cursor
    except pyodbc.Error as e:
        print("Error in Connection", e)


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
def select_to_DataBase(cur):
    set = []
    sem = ["Первый", "Второй", "Третий", "Четвертый", "Пятый", "Шестой", "Седьмой", "Восьмой", ]
    data = []
    buf = ""
    zet = 0.0
    j = -1
    for i in range(len(sem)):
        cur.execute(
            'SELECT ID_of_module, Discipline, Control_period, ZET  FROM Disciplines_and_practices WHERE Control_period LIKE ? AND ID_of_the_educational_program = 2',
            (sem[i] + " семестр"))
        for row in cur.fetchall():
            if buf != row[1]:
                buf = row[1]
                data.append(row[0])
                data.append(row[1])
                data.append(row[2])
                set.append(data.copy())
                data_rev = set[j]
                if len(data_rev) == 3:
                    data_rev.append(int(zet))
                    set[j] = data_rev.copy()
                else:
                    data_rev[3] = int(zet)
                    set[j] = data_rev.copy()
                zet = 0.0
                j += 1
            if row[3] != None:
                zet += round(float(row[3]), 1)

            data.clear()
    data_rev = set[-1]
    data_rev.append(int(zet))
    set[-1] = data_rev.copy()

    set = sort_modul(set)
    print(set)
    return set


def select_color(cur, modul):
    cur.execute(
        'SELECT Color  FROM Module_reference WHERE ID_of_module LIKE ?', (modul))
    for row in cur.fetchall():
        return (row[0])


# функция создает карту и задаем все данные кроме предметов в семестрах, на вход требует имя карты
def CreateMap(filename_map):
    wk = xlsxwriter.Workbook(filename_map)
    ws = wk.add_worksheet()
    ws.set_column(1, 29, 29)
    wk.close()
    workbook = openpyxl.load_workbook(filename_map)
    worksheet = workbook.active
    ns = NamedStyle(name='standart')
    ns.font = Font(bold=False, size=12)
    border = Side(style='thick', color='000000')
    ns.border = Border(left=border, top=border, right=border, bottom=border)
    ns.alignment = Alignment(horizontal='center', vertical='center', wrapText=True)
    workbook.add_named_style(ns)
    worksheet.column_dimensions['A'].height = 50
    worksheet.row_dimensions[1].height = 50
    worksheet.merge_cells('A1:I1')
    worksheet['A1'] = 'КАРТА ДИСЦИПЛИН'
    worksheet['A1'].style = 'standart'
    worksheet['A1'].font = Font(bold=True, size=12)
    worksheet["A2"] = "З.Е."
    worksheet['A2'].style = 'standart'
    for col in range(3, 33):
        worksheet["A" + str(col)] = col - 2
        worksheet["A" + str(col)].style = 'standart'
    for col in range(ord('B'), ord('J')):
        worksheet[chr(col) + str(2)] = str(col - 65) + " семестр"
        worksheet[chr(col) + str(2)].style = 'standart'
    return worksheet, workbook


# заполняем данные, размер и цвет  в ячейках карты,
# Так же мы красим предметы в соответствии с модулем
def filling_map(fullname_db, filename_map):
    cur = connect_to_DateBase(fullname_db)
    date = select_to_DataBase(cur)
    ws, wk = CreateMap(filename_map)
    adr_cell = "B"
    buf = "Первый семестр"
    row = 3
    i = -1
    while adr_cell != "J" and i < len(date) - 1:
        i += 1
        date_dist = date[i]
        if date_dist[2] == buf and date_dist[3] != 0:
            dip = adr_cell + str(row) + ':' + adr_cell + str(row + date_dist[3] - 1)
            ws[adr_cell + str(row)].style = 'standart'
            ws[adr_cell + str(row)] = date_dist[1]
            cell = ws[adr_cell + str(row)]
            color = select_color(cur, date_dist[0])
            cell.fill = openpyxl.styles.PatternFill(start_color=str(color), end_color=str(color), fill_type='solid')
            ws.merge_cells(dip)
            row += date_dist[3] - 1
            buf = date_dist[2]
            row += 1
        elif date_dist[3] != 0:
            adr_cell = chr(ord(adr_cell) + 1)
            buf = date_dist[2]
            row = 3
            i -= 1
    wk.save(filename=filename_map)


# основная функция-связующая все части и вводит основные параметры всего
def main():
    filename_map = 'map.xlsx'
    fullname_db = '.\db.accdb;'
    filling_map(fullname_db, filename_map)


if __name__ == "__main__":
    main()
