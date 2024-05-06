import pandas as pd

from maps.logic.global_variables import addGlobalVariable, getGroupId, getModuleId
from maps.logic.tools import check_skiplist, prepare_shifr, timeit, get_grouped_disciplines
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


def create_json(aup: str) -> dict | None:
    """
        Функция для преобразования данных из БД для формирования веб-версии карты дисциплин
    """

    aup_info: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aup_info:
        return None

    result = {
        "header": [aup_info.name_op.okco.program_code + '.' + aup_info.name_op.num_profile,
                   aup_info.name_op.okco.name_okco, aup_info.name_op.name_spec, aup_info.faculty.name_faculty],
        "year": aup_info.year_beg,
    }

    data = []
    for (discipline, id_period), loads in get_grouped_disciplines(aup_info.aup_data).items():
        el: AupData = loads[0]
        data_element = {
            "discipline": discipline,
            "id_group": el.id_group,
            "id_block": el.id_block,
            "shifr": el.shifr,
            "shifr_new": get_shifr(el.shifr),
            "allow_control_types": get_allow_control_types(el.shifr),
            "id_part": el.id_part,
            "id_module": el.id_module,
            "num_col": id_period - 1,
            "num_row": el.num_row,
            "id": el.id,
            "is_skip": not check_skiplist(el.zet, el.discipline, el.type_record.title, el.block.title),
            'type': {
                'session': [],
                'value': [],
            }
        }

        if data_element['is_skip']:
            continue

        for load in loads:
            load = {
                "amount": load.amount / 100,
                "amount_type": 'hour' if load.ed_izmereniya.id == 1 else 'week',
                "id": load.id,
                "control_type_id": load.id_type_control,
                "type": "control" if load.id_type_control in [1, 5, 9] else 'load'
            }

            if load['type'] == 'control':
                data_element['type']['session'].append(load)
            else:
                data_element['type']['value'].append(load)

        data.append(data_element)
    result['data'] = data
    return result


def get_shifr(shifr: str) -> dict:
    """
        Функция для разложения шифра на составляющие
    """
    shifr = prepare_shifr(shifr)
    match shifr.split("."):
        case block, part, module, discipline:
            ...
        case block, part, discipline:
            module = None
        case block, discipline:
            part = module = None
        case _:
            block = part = module = discipline = None

    return {
        "shifr": shifr,
        "block": block.replace("Б", "") if block else block,
        "part": part,
        "module": module,
        "discipline": discipline
    }


def get_allow_control_types(shifr):
    """
        Функция для получения возможных типов контроля для Части (составляющая шифра)
    """
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


def create_json_print(aup_data):
    """
        Функция для преобразования данных из БД для дальнейшего формирования печатной карты дисциплин
    """
    group_id_to_color = {el.id_group: el.color for el in Groups.query.all()}

    data = []
    for (discipline, id_period), loads in get_grouped_disciplines(aup_data).items():
        el: AupData = loads[0]
        zet = 0
        for load in loads:
            zet += load.amount / 100 * (54 if load.id_edizm == 2 else 1)

        data_element = {
            "discipline": discipline,
            "color": group_id_to_color[el.id_group],
            "id_group": el.id_group,
            "num_col": id_period,
            "num_row": el.num_row,
            "is_skip": not check_skiplist(el.zet, el.discipline, el.type_record.title, el.block.title),
            "zet": zet / 36
        }

        if data_element['is_skip']:
            continue

        data.append(data_element)

    return {"data": data}


@timeit
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

    print(allRow)
    return allRow


def elective_disciplines(aup_info: AupInfo) -> dict:
    """
        Функция для получения факультативных дисциплин учебного плана с суммарным объемам по всем видам нагрузок
    """
    ELECTIVE_TYPE_ID = [13, 15, 16]

    elective_disciplines = {}
    for el in aup_info.aup_data:
        if el.id_type_record in ELECTIVE_TYPE_ID:
            try:
                elective_disciplines[el.discipline] += el.amount // 100
            except:
                elective_disciplines[el.discipline] = el.amount // 100

    return elective_disciplines