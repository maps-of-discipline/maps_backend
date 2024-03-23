import pandas as pd

from maps.logic.global_variables import addGlobalVariable, getGroupId, getModuleId
from maps.logic.tools import check_skiplist, prepare_shifr
from maps.models import AupData, AupInfo, Groups, db, D_Blocks, D_Part, D_TypeRecord, D_Period, D_ControlType, \
    D_EdIzmereniya

blocks = {}
blocks_r = {}
period = {}
period_r = {}
control_type = {}
control_type_r = {}
ed_izmereniya = {}
ed_izmereniya_r = {}
chast = {}
chast_r = {}
type_record = {}
type_record_r = {}

allow_control_types_block1 = [1, 2, 3, 4, 5, 6, 7, 9, 17]
allow_control_types_block2 = [10, 11, 13, 16, 19, 20, 21]
allow_control_types_block3 = [12, 14, 15]


def getType(id):
    l = [1, 5, 9]
    if id in l:
        return "control"
    return "load"


def create_json(aup):
    aupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aupInfo:
        return None

    aupData = AupData.query.filter_by(id_aup=aupInfo.id_aup).order_by(AupData.shifr, AupData.discipline,
                                                                      AupData.id_period).all()

    json = dict()
    json['header'] = [aupInfo.name_op.okco.program_code + '.' + aupInfo.name_op.num_profile,
                      aupInfo.name_op.okco.name_okco, aupInfo.name_op.name_spec, aupInfo.faculty.name_faculty]
    json['year'] = aupInfo.year_beg
    json['data'] = list()
    flag = ""
    session = list()
    value = list()

    # if check_skiplist(item.zet, item.discipline, item.type_record.title, item.block.title) == False:
    #     continue
    for i, item in enumerate(aupData):
        # if 'Выполнение и защита выпускной квалификационной работы' in item.discipline:
        #     pass
        if flag != item.discipline + str(item.id_period):
            if i != 0 and 'd' in locals():
                d['type']['session'] = session
                d['type']['value'] = value
                session = list()
                value = list()
                json['data'].append(d)
            flag = item.discipline + str(item.id_period)
            d = dict()
            d["discipline"] = item.discipline
            d["id_group"] = item.id_group
            d["id_block"] = item.id_block
            # TODO удалить после того, как фронт подстроится под shifr_new
            d["shifr"] = item.shifr
            d["shifr_new"] = get_shifr(item.shifr)
            d["allow_control_types"] = get_allow_control_types(item.shifr)
            d["id_part"] = item.id_part
            d["id_module"] = item.id_module
            d["num_col"] = item.id_period - 1
            d["num_row"] = item.num_row
            d["type"] = dict()
            d["id"] = str(item.id)
            if check_skiplist(item.zet, item.discipline, item.type_record.title, item.block.title) == False:
                d["is_skip"] = True
            else:
                d["is_skip"] = False
            zet = dict()
            zet["amount"] = item.amount / 100
            zet["amount_type"] = 'hour' if item.ed_izmereniya.id == 1 else 'week'
            zet["id"] = item.id
            zet["control_type_id"] = item.id_type_control
            zet["type"] = getType(item.id_type_control)
            if item.id_type_control == control_type['Экзамен'] or item.id_type_control == control_type[
                'Зачет'] or item.id_type_control == control_type['Дифференцированный зачет']:
                session.append(zet)
            else:
                value.append(zet)
            if i + 1 == len(aupData):
                d['type']['session'] = session
                d['type']['value'] = value
                json['data'].append(d)
        else:
            d["id"] += str(item.id)
            zet = dict()
            zet["amount"] = item.amount / 100
            zet["amount_type"] = 'hour' if item.ed_izmereniya.id == 1 else 'week'
            zet["id"] = item.id
            zet["control_type_id"] = item.id_type_control
            zet["type"] = getType(item.id_type_control)
            if item.id_type_control == control_type['Экзамен'] or item.id_type_control == control_type[
                'Зачет'] or item.id_type_control == control_type['Дифференцированный зачет']:
                session.append(zet)
            else:
                value.append(zet)
            if i + 1 == len(aupData):
                d['type']['session'] = session
                d['type']['value'] = value
                json['data'].append(d)

    for num in range(len(json["data"]) - 1, -1, -1):
        if json["data"][num]["is_skip"] == True:
            del json["data"][num]
    return json


def get_shifr(shifr):
    shifr = prepare_shifr(shifr)
    shifr_array = str.split(shifr, ".")
    if len(shifr_array) == 4:
        return {
            "shifr": shifr,
            "block": shifr_array[0].replace("Б", ""),
            "part": shifr_array[1],
            "module": shifr_array[2],
            "discipline": shifr_array[3]
        }
    elif len(shifr_array) == 3:
        return {
            "shifr": shifr,
            "block": shifr_array[0].replace("Б", ""),
            "part": shifr_array[1],
            "module": None,
            "discipline": shifr_array[2]
        }
    elif len(shifr_array) == 2:
        return {
            "shifr": shifr,
            "block": shifr_array[0].replace("Б", ""),
            "part": None,
            "module": None,
            "discipline": shifr_array[1]
        }
    else:
        return {
            "shifr": shifr,
            "block": None,
            "part": None,
            "module": None,
            "discipline": None
        }


def get_allow_control_types(shifr):
    shifr_array = str.split(shifr, ".")
    try:
        part = shifr_array[0][1]
        if part == '1':
            return allow_control_types_block1
        if part == '2':
            return allow_control_types_block2
        if part == '3':
            return allow_control_types_block3
    except:
        return None


def create_json_test(aupInfo, aupData, max_column, max_row):
    json = dict()
    json['header'] = [aupInfo.name_op.okco.program_code + '.' + aupInfo.name_op.num_profile,
                      aupInfo.name_op.okco.name_okco, aupInfo.name_op.name_spec, aupInfo.faculty.name_faculty]
    json['year'] = aupInfo.year_beg
    json['data'] = list()
    for i in range(1, max_column + 1):
        for j in range(max_row + 1):
            print(i, j)
            disc = aupData.filter_by(num_row=j, id_period=i).all()
            if disc == []: continue
            if check_skiplist(disc[0].zet, disc[0].discipline, disc[0].type_record.title, disc[0].block.title) == False:
                continue
            d = dict()
            d["discipline"] = disc[0].discipline
            d["id_group"] = disc[0].id_group
            d["num_col"] = disc[0].id_period
            d["num_row"] = disc[0].num_row
            d["type"] = list()
            d["id"] = ""
            for item in disc:
                zet = dict()
                zet["control"] = control_type_r[item.id_type_control]
                zet["zet"] = item.zet / 100
                zet["id"] = item.id
                d["type"].append(zet)
                d["id"] += str(item.id)
            json['data'].append(d)
    return json


def create_json_print(aupData):
    json = dict()
    json['data'] = list()
    flag = ""
    for i, item in enumerate(aupData):
        # if 'Дизайн-проектирование природоподобных объектов для новой мобильности' in item.discipline:
        #     pass
        # if check_skiplist(item.zet, item.discipline, item.type_record.title, item.block.title) == False:
        #     continue
        if flag != item.discipline + str(item.id_period):
            if i != 0 and 'd' in locals():
                json['data'].append(d)
            flag = item.discipline + str(item.id_period)
            d = dict()
            d["discipline"] = item.discipline
            group = Groups.query.filter(Groups.id_group == item.id_group).first()
            d["color"] = group.color
            d["id_group"] = group.id_group
            d["num_col"] = item.id_period
            d["num_row"] = item.num_row
            if check_skiplist(item.zet, item.discipline, item.type_record.title, item.block.title) == False:
                d["is_skip"] = True
            else:
                d["is_skip"] = False
            if item.id_edizm == 2:
                d["zet"] = item.amount / 100 * 54
            else:
                d["zet"] = item.amount / 100
            if i + 1 == len(aupData):
                json['data'].append(d)
        else:
            if item.id_edizm == 2:
                d["zet"] = item.amount / 100 * 54
            else:
                d["zet"] += item.amount / 100
            if i + 1 == len(aupData):
                json['data'].append(d)
    # for disc in json['data']:
    #     disc['zet'] /= 36

    for num in range(len(json["data"]) - 1, -1, -1):
        if json["data"][num]["is_skip"] == True:
            del json["data"][num]
        else:
            json["data"][num]['zet'] /= 36

    return json


def getAupData(file):
    weight = {
        'Проектная деятельность': 10,
        'Введение в проектную деятельность': 10,
        'Управление проектами': 10,
        'Иностранный язык': 1
    }

    data = pd.read_excel(file, sheet_name="Лист2")
    #             Наименование
    # 0                   Блок.
    # 1                   Шифр.
    # 2                  Часть.
    # 3                 Модуль.
    # 4             Тип записи.
    # 5             Дисциплина.
    # 6        Период контроля.
    # 7               Нагрузка----
    # 8             Количество----
    # 9               Ед. изм.----
    # 10                   ЗЕТ----
    # 11              групп ID.
    # 12    Позиция в семестре.
    # 13                   Вес.

    allRow = []
    modules = {}
    groups = {}
    for i in range(len(data)):
        row = []
        for column in data.columns:
            row.append(data[column][i])

        # if row[5]is None:
        # print(i, row[5])

        row[1] = prepare_shifr(row[1])

        val = row[0]
        row[0] = blocks.get(val)
        if row[0] == None:
            id = addGlobalVariable(db, D_Blocks, val)
            blocks[val] = id
            blocks_r[id] = val
            row[0] = id

        val = row[2]
        row[2] = chast.get(val)
        if row[2] == None:
            id = addGlobalVariable(db, D_Part, val)
            chast[val] = id
            chast_r[id] = val
            row[2] = id

        if pd.isna(row[3]):
            row[3] = "Без названия"
        val = row[3]
        row[3] = modules.get(val)
        if row[3] == None:
            id = getModuleId(db, val)
            modules[val] = id
            row[3] = id

        if 'Модуль' in val:
            val = val.strip()
            val = val[8:-1].strip()
        row.append(groups.get(val))
        if row[11] == None:
            id = getGroupId(db, val)
            groups[val] = id
            row[11] = id

        val = row[4]
        row[4] = type_record.get(val)
        if row[4] == None:
            id = addGlobalVariable(db, D_TypeRecord, val)
            type_record[val] = id
            type_record_r[id] = val
            row[4] = id

        val = row[6]
        row[6] = period.get(val)
        if row[6] == None:
            id = addGlobalVariable(db, D_Period, val)
            period[val] = id
            period_r[id] = val
            row[6] = id

        val = row[7]
        row[7] = control_type.get(val)
        if row[7] == None:
            id = addGlobalVariable(db, D_ControlType, val)
            control_type[val] = id
            control_type_r[id] = val
            row[7] = id

        val = row[9]
        row[9] = ed_izmereniya.get(val)
        if row[9] == None:
            id = addGlobalVariable(db, D_EdIzmereniya, val)
            ed_izmereniya[val] = id
            ed_izmereniya_r[id] = val
            row[9] = id

        if pd.isna(row[8]):
            row[8] = 0
        else:
            try:
                row[8] = int(float(row[8].replace(',', '.')) * 100)
            except:
                row[8] = int(float(row[8]) * 100)

        if pd.isna(row[10]):
            row[10] = 0
        else:
            try:
                row[10] = int(float(row[10].replace(',', '.')) * 100)
            except:
                row[10] = int(float(row[10]) * 100)

        row.append("позиция")
        row.append(weight.get(row[5], 5))

        allRow.append(row)

    allRow.sort(key=lambda x: (x[6], x[13], x[5]))

    counter = 0
    semestr = allRow[0][6]
    disc = allRow[0][5]
    for i in range(len(allRow)):
        if allRow[i][6] != semestr:
            semestr = allRow[i][6]
            counter = -1
        if allRow[i][5] != disc:
            disc = allRow[i][5]
            counter += 1

        allRow[i][12] = counter

    return allRow
