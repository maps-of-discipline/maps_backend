import os
from random import randint

import openpyxl
import xlsxwriter
from openpyxl.styles import (Alignment, Border, Font, NamedStyle, PatternFill,
                             Side)

from models import AUP, OP, Module, NameOP, SprFormEducation, SprOKCO, Workload

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


def Legend(table):
    def getName(el):

        name = Module.query.filter_by(id_module=el[0]).first().name_module
        return [name, el[1], el[0]]

    legend = []

    for i in range(len(table)):
        # [name, sum_zet, module]

        for el in table[i]:
            res = list(filter(lambda x: x[0] == el['module_color'], legend))

            if res != []:
                index = legend.index(res[0])
                legend[index][1] += el['zet']
            else:
                legend.append([el['module_color'], el['zet']])

    if len(legend) <= 3:
        legend = []
        # [name, sum_zet, module]
        for i in range(len(table)):
            for el in table[i]:
                res = list(filter(lambda x: x[0] == el['block'], legend))

                if res != []:
                    index = legend.index(res[0])
                    legend[index][1] += el['zet']
                else:
                    legend.append([el['block'], el['zet']])
        for i in range(len(legend)):
            legend[i].append(i)

        legend.sort(key=lambda x: x[0])
    else:
        legend = list(map(lambda x: getName(x), legend))

    return legend


# Формируем карту excel и сохраняем ее в папку static/temp
def saveMap(aup, static, **kwargs):

    select_aup = AUP.query.filter_by(num_aup=aup).first()
    id_aup = select_aup.id_aup
    filename_map = select_aup.file

    filename_map_down = f"КД {filename_map}"
    filename_map = os.path.join(static, 'temp', f"КД {filename_map}")

    table, legend, max_zet = Table(aup, **kwargs)
    ws, wk = CreateMap(filename_map, max_zet)

    ws.merge_cells(f'A1:{chr(ord("A") + len(table))}1')
    header = Header(aup)

    header = f'''
        КАРТА ДИСЦИПЛИН УЧЕБНОГО ПЛАНА от {header[4]}
        по направлению подготовки {header[0]}
        Профиль: {header[1]}, {header[2]} год набора, {header[3]}
        АУП: {aup}
    '''
    for i in range(len(table)):
        ws[chr(ord("B")+i)+"2"] = str(i+1) + " семестр"
        ws[chr(ord("B")+i)+"2"].style = 'standart'

    ws['A1'].style = 'standart'
    ws['A1'] = header

    for i in range(len(table)):
        merged = 0
        for el in table[i]:
            column = chr(ord("B") + i)
            cell = f"{column}{3+merged}"

            ws[cell] = el['discipline']
            ws[cell].style = "standart"

            color = el['module_color'].replace('#', '')

            r, g, b = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
            gray = (r + g + b)/3

            if gray < 140:
                ws[cell].font = Font(color="FFFFFF", size=12)
            else:
                ws[cell].font = Font(color="000000", size=12)

            ws[cell].fill = PatternFill(start_color=str(
                color), end_color=str(color), fill_type='solid')

            if el['zet'] < 1:
                el['zet'] = 1.0

            merge_range = f"{cell}:{column}{3+merged + round(el['zet'])-1}"
            ws.merge_cells(merge_range)

            merged += round(el['zet'])

        ws['A40'] = 'З.Е'
        ws['A40'].style = 'standart'
        ws['B40'] = 'МОДУЛИ:'
        ws['B40'].style = 'standart'
        ws.merge_cells('B40:C40')

        # Вывод легенды в КД excel
        sum_zet = 0.0
        for i, el in enumerate(legend):
            cellA = f"A{41+i}"
            cellB = f"B{41+i}"

            sum_zet += el[1]

            ws[cellA].style = ws[cellB].style = 'standart'
            ws[cellA] = el[1]
            ws[cellB] = el[0]
            ws[cellB].alignment = Alignment(
                horizontal='left', vertical='center', wrapText=True)

            color = el[2].replace('#', '')
            r, g, b = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
            gray = (r + g + b)/3

            if gray < 140:
                ws[cellB].font = Font(color="FFFFFF", size=12)
            else:
                ws[cellB].font = Font(color="000000", size=12)

            ws[cellB].fill = PatternFill(start_color=str(
                color), end_color=str(color), fill_type='solid')
            ws.merge_cells(cellB + ':' + cellB.replace('B', 'C'))

    # сумма зет
    cellA = 'A' + str(40+len(legend) + 1)
    ws[cellA].style = 'standart'
    ws[cellA] = f'Итого: {sum_zet}'

    ws['A' + str(40+len(legend) + 5)
       ] = f'Карта составлена из файла: {filename_map_down}'

    wk.save(filename=filename_map)
    return filename_map


# Возвращает данные для шапка карты
def Header(aup):

    id_op = AUP.query.filter_by(num_aup=aup).first().id_op

    select_op = OP.query.filter_by(id_op=id_op).first()
    year_begin = select_op.duration.year_beg
    program_code = select_op.duration.name_op.program_code
    id_spec = select_op.duration.id_spec
    id_form = select_op.duration.id_form

    program = program_code + " " + \
        SprOKCO.query.filter_by(program_code=program_code).first().name_okco

    spec = NameOP.query.filter_by(id_spec=id_spec).first().name_spec

    form = SprFormEducation.query.filter_by(
        id_form=id_form).first().form + " форма обучения"

    date_file = AUP.query.filter_by(num_aup=aup).first().file.split(' ')[-4]

    return [program, spec, year_begin, form, date_file]



# раскраска и сортировка данных в таблице
def colorize(table, legend=None, **kwargs):
    COLOR_SET = 0
    EXPO = 0

    colorsets = [
        [
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
            '#FFCC00',
            '#3B7080',
            '#C97064',
            '#008B8B',
            '#B8860B',
            '#01B235'
        ],
        # Случайные цвета, должен быть последним
        [
            '#%02x%02x%02x' % (randint(0, 255), randint(0, 255), randint(0, 255)) for _ in range(20)
        ]
    ]

    def expo(colorset, value):
        colorset = [[int(x.replace('#', '')[i:i+2], 16)
                     for i in (0, 2, 4)] for x in colorset]

        def f(x):
            r, g, b = x

            r += value
            r = 255 if r > 255 else r

            g += value
            g = 255 if g > 255 else g

            b += value
            b = 255 if b > 255 else b

            return [r, g, b]

        colorset = list(map(lambda x: f(x), colorset))

        for i, el in enumerate(colorset):
            colorset[i] = '#%02x%02x%02x' % (el[0], el[1], el[2])

        return (colorset)

    if 'colorSet' in kwargs.keys():
        if kwargs['colorSet'] < len(colorsets)-1:
            COLOR_SET = kwargs['colorSet']

    if 'expo' in kwargs.keys():
        EXPO = kwargs['expo']

    colorset = expo(colorsets[COLOR_SET], EXPO)
    print(colorset)
    

    # находим количество уникальных модулей
    unique_modules = []
    for index, i in enumerate(table):
        for j in i:
            if not j["module_color"] in unique_modules:
                unique_modules.append(j["module_color"])
    print("[DEBUG] uniquemodules = ", unique_modules)
    # преобразовываем список в список списков, где каждый вложенный список состоит из уникального модуля и количества раз
    # когда он встречается в семестрах

    # добавляем цвета легенде
    unique_modules = list(map(lambda x: [x, 0], unique_modules))

    # проверка наличия модулей в карте (бывают карты без заполненного поля модуль)

    if len(unique_modules) > 3:

        print("[DEBUG] true  = ")
        if legend:
            for i, el in enumerate(legend):
                print(i, el)
                index = unique_modules.index([el[2], 0])
                legend[i][2] = colorset[index]

        # считаем количетсво семестров для каждого модуля, в которых он встречается
        for i in range(len(table)):
            checked = []
            for j in range(len(table[i])):
                if table[i][j]["module_color"] in checked:
                    continue
                checked.append(table[i][j]["module_color"])

                for k in range(len(unique_modules)):
                    if unique_modules[k][0] == table[i][j]["module_color"]:
                        unique_modules[k][1] += 1

        # преобразовываем список списков в словарь для более простого доступа
        t = {}
        for el in unique_modules:
            t.update({str(el[0]): el[1]})
        unique_modules = t

        # добавляем в таблицу каждому элементу поле count для сортировки
        for i in range(len(table)):
            for j in range(len(table[i])):
                count = unique_modules[str(table[i][j]['module_color'])]
                table[i][j].update({"count": count})

        for i in range(len(table)):
            # сортируем по полю count и module
            table[i].sort(key=lambda x: (
                x["count"], x["module_color"]), reverse=True)

            # перемещаем проектную деятельность в конец каждого семестра и раскрашиваем
            j = 0
            swapped = 0
            while j < len(table[i]) - swapped:
                if table[i][j]["module_color"] == 4:
                    table[i][j]["module_color"] = colorset[list(
                        unique_modules.keys()).index(str(table[i][j]["module_color"]))]
                    table[i].append(table[i].pop(j))
                    j -= 1
                    swapped += 1
                else:
                    table[i][j]["module_color"] = colorset[list(
                        unique_modules.keys()).index(str(table[i][j]["module_color"]))]
                j += 1
            table[i].sort(key=lambda x: x['block'])

    else:
        # добавляем цвета легенде
        if legend:
            for i, el in enumerate(legend):
                legend[i][2] = colorset[el[2]]

        # раскрашиваем в соответствии с блоком
        for i in range(len(table)):
            # table[i].sort(key=lambda x: x['block'])

            j = 0
            swapped = 0
            while j < len(table[i]) - swapped:
                if table[i][j]["module_color"] in [4, 21]:

                    el = table[i][j]
                    if "Блок 1" in el['block']:
                        table[i][j]['module_color'] = colorset[0]

                    elif "Блок 2" in el['block']:
                        table[i][j]['module_color'] = colorset[1]

                    else:
                        table[i][j]['module_color'] = colorset[2]

                    table[i].append(table[i].pop(j))
                    j -= 1
                    swapped += 1
                else:
                    el = table[i][j]
                    if "Блок 1" in el['block']:
                        table[i][j]['module_color'] = colorset[0]

                    elif "Блок 2" in el['block']:
                        table[i][j]['module_color'] = colorset[1]

                    else:
                        table[i][j]['module_color'] = colorset[2]

                j += 1

            table[i].sort(key=lambda x: x['block'])

        # # если модулей нет
        # disciplines = []
        # discs_count = []
        # # считаем количество дисциплин
        # for i in table:
        #     for j in i:
        #         if not j['discipline'] in disciplines:
        #             disciplines.append(j['discipline'])
        #             discs_count.append(1)
        #         else:
        #             index = disciplines.index(j['discipline'])
        #             discs_count[index] += 1

        # # удаляем те, у которых количество равно 1
        # popped = 0
        # for i, el in enumerate(discs_count):
        #     if el == 1:
        #         disciplines.pop(i-popped)
        #         popped += 1

        # # раскрашиваем в соответсвии с количеством
        # for i in range(len(table)):
        #     for j in range(len(table[i])):
        #         if table[i][j]['discipline'] in disciplines:
        #             index = disciplines.index(table[i][j]['discipline'])
        #             table[i][j]['module_color'] = colorset[index+1]
        #         else:
        #             table[i][j]['module_color'] = colorset[0]

    return table, legend

sems = ["Первый", "Второй", "Третий", "Четвертый", "Пятый", "Шестой",
            "Седьмой", "Восьмой", "Девятый", "Десятый", "Одиннадцатый", "Двенадцатый", 'Тринадцатый', 'Четырнадцатый']

# возвращает сформированную таблицу с раскрашенными ячейками
def Table(aup, **kwargs):
    """
    Make sql-query by aup and buid discipline map \n
    keyword arguments: \n
    colorSet -- number of color set. Default(0)
    expo -- exposition. Bounds: -255 - only black color, only 255 - white color. Default(0)
    """
    # sems = ["Первый", "Второй", "Третий", "Четвертый", "Пятый", "Шестой",
    #         "Седьмой", "Восьмой", "Девятый", "Десятый", "Одиннадцатый", "Двенадцатый", 'Тринадцатый', 'Четырнадцатый']


    id_aup = AUP.query.filter_by(num_aup=aup).first().id_aup

    if id_aup == None:
        # если в бд нет выгрузки
        print("There is no such aup in data base")
        return None

    workload = Workload.query.filter_by(id_aup=id_aup).order_by(
        Workload.record_type.desc(), Workload.discipline.desc(), Workload.period.desc()).all()
    print('--------------------', workload[0].load)
    
    sumzet = 0.0
    # формируем таблицу
    table = []
    for item in workload:
        # moduleID, record_type, discipline, period, zet, block = item
        moduleID = item.id_module
        record_type = item.record_type
        discipline = item.discipline
        period = item.period
        zet = item.zet
        block = item.block

        # Фильтрация, тут исправлять if
        if (len(list(filter(lambda x: x in discipline, skiplist['discipline']))) > 0 or
                len(list(filter(lambda x: x in record_type, skiplist['record_type']))) > 0):
            continue

        sumzet += zet
        period = period.split()[0]

        # словарь с данными ячейчи
        cell = {
            "module_color": moduleID,
            "block": block,
            "discipline": discipline,
            "term": period,
            "zet": zet
        }

        # добаляем в таблицу недостоющее количество семестров для очередной записи в списке workload
        delta = len(table) - sems.index(period) - 1
        if delta < 0:
            for i in range(-delta):
                table.append([])

        # считаем сумму зет для каждой дисциплины, включая экзамены, лаб.занятия, лекции и т.д.
        for el in table[sems.index(period)]:
            if el['discipline'] == discipline:
                el['zet'] += zet
                break
        else:
            # если такой дисциплины нет, то добавляем в таблицу
            table[sems.index(period)].append(cell)

    leg = Legend(table)
    print('-------------------', sumzet)
    max_zet = find_max_zet(table)
    table, legend = colorize(table, legend=leg, **kwargs) # раскрашиваем и возвращаем
    return table, legend, max_zet


def find_max_zet(table):
    print('!!!!!---------!!!!!!!', table)
    max_zet = 0
    for column in table:
        temp = 0
        for it in column:
            temp += it['zet']
        if temp > max_zet:
            max_zet = temp
    return int(max_zet)


# функция создает карту и задаем все данные кроме предметов в семестрах, на вход требует имя карты
def CreateMap(filename_map, max_zet):
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
    ns.alignment = Alignment(
        horizontal='center', vertical='center', wrapText=True)
    workbook.add_named_style(ns)
    worksheet.row_dimensions[1].height = 50
    worksheet.row_dimensions[2].height = 41
    worksheet["A2"] = "З.Е."
    worksheet['A2'].style = 'standart'
    for col in range(3, max_zet + 3):
        worksheet["A" + str(col)] = col - 2
        worksheet["A" + str(col)].style = 'standart'
    for col in range(ord('B'), ord('C')):
        worksheet[chr(col) + str(2)] = str(col - 65) + " семестр"
        worksheet[chr(col) + str(2)].style = 'standart'
    return worksheet, workbook


# получить все сущестующие карты
def GetAllMaps(param=None):
    res = dict()
    if param != None:
        search = "%{}%".format(param)
        maps = AUP.query.filter(AUP.file.like(search)).all()
    else:
        maps = AUP.query.all()
    for i in range(len(maps)):
        print(maps[i].id_aup)
        res[maps[i].id_aup] = [maps[i].id_op, maps[i].file, maps[i].num_aup, maps[i].op]
    return maps

if __name__ == "__main__":

    pass
