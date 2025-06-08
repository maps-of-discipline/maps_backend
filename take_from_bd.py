import pandas as pd

from maps.logic.global_variables import addGlobalVariable, getGroupId, getModuleId
from maps.logic.tools import (
    check_skiplist,
    prepare_shifr,
    timeit,
    get_grouped_disciplines,
)
from maps.models import (
    AupData,
    AupInfo,
    Groups,
    db,
    D_Blocks,
    D_Part,
    D_TypeRecord,
    D_Period,
    D_ControlType,
    D_EdIzmereniya,
    ControlTypeShortName,
)

# Initialize dictionaries for mapping between names and IDs
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

# Define allowed control types by block names instead of IDs
allow_control_types_block1 = ["Лекции", "Практические занятия", "Лабораторные работы", 
                             "Самостоятельная работа", "Консультации", "Экзамен", "Зачет"]
allow_control_types_block2 = ["Курсовая работа", "Дифференцированный зачет", 
                             "Проектная деятельность", "Практика", "НИР"]
allow_control_types_block3 = ["Факультативные занятия", "Государственная аттестация"]


def create_json(aup: str) -> dict | None:
    """
    Функция для преобразования данных из БД для формирования веб-версии карты дисциплин
    """
    # Get measurement units from database
    hour_unit = D_EdIzmereniya.query.filter_by(title="час").first()
    week_unit = D_EdIzmereniya.query.filter_by(title="неделя").first()

    aup_info: AupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aup_info:
        return None

    result = {
        "header": [
            aup_info.spec.okco.program_code + "." + aup_info.spec.num_profile,
            aup_info.spec.okco.name_okco,
            aup_info.spec.name_spec,
            aup_info.faculty.name_faculty,
        ],
        "year": aup_info.year_beg,
        "info": aup_info.as_dict(),
    }

    data = []
    for (discipline, id_period), loads in get_grouped_disciplines(
        aup_info.aup_data
    ).items():
        el: AupData = loads[0]
        data_element = {
            "id": el.id,
            "id_discipline": el.id_discipline,
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
            "id_type_record": el.id_type_record,
            "is_skip": not check_skiplist(
                el.zet, el.discipline.title, el.type_record.title, el.block.title
            ),
            "type": {
                "session": [],
                "value": [],
            },
        }

        if data_element["is_skip"]:
            continue

        control_types = [
            "Зачет",
            "Экзамен",
            "Дифференцированный зачет",
            "Курсовой проект",
            "Курсовая работа",
        ]

        for load in loads:
            load_type = "load"

            if load.type_control.title in control_types:
                load_type = "control"

            load_data = {
                "amount": load.amount / 100,
                "amount_type": "hour" if load.ed_izmereniya.id == hour_unit.id else "week",
                "id": load.id,
                "control_type_id": load.id_type_control,
                "type": load_type,
            }

            if load_data["type"] in ["control", "course"]:
                data_element["type"]["session"].append(load_data)
            else:
                data_element["type"]["value"].append(load_data)

        data.append(data_element)
    result["data"] = data
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
        "discipline": discipline,
    }


def get_allow_control_types(shifr):
    """
    Функция для получения возможных типов контроля для Части (составляющая шифра)
    Теперь использует названия типов контроля вместо ID
    """
    shifr_array = str.split(shifr, ".")
    try:
        part = shifr_array[0][1]
        if part == "1":
            return [ct for ct in D_ControlType.query.filter(
                D_ControlType.title.in_(allow_control_types_block1)
            ).all()]
        if part == "2":
            return [ct for ct in D_ControlType.query.filter(
                D_ControlType.title.in_(allow_control_types_block2)
            ).all()]
        if part == "3":
            return [ct for ct in D_ControlType.query.filter(
                D_ControlType.title.in_(allow_control_types_block3)
            ).all()]
    except:
        return None


def create_json_print(aup_data):
    """
    Функция для преобразования данных из БД для дальнейшего формирования печатной карты дисциплин
    """
    # Get measurement units from database
    hour_unit = D_EdIzmereniya.query.filter_by(title="час").first()
    week_unit = D_EdIzmereniya.query.filter_by(title="неделя").first()
    
    group_id_to_color = {el.id_group: el.color for el in Groups.query.all()}

    data = []
    for (discipline, id_period), loads in get_grouped_disciplines(aup_data).items():
        el: AupData = loads[0]
        zet = 0
        for load in loads:
            zet += load.amount / 100 * (54 if load.id_edizm == week_unit.id else 1)

        data_element = {
            "discipline": discipline,
            "color": group_id_to_color[el.id_group],
            "id_group": el.id_group,
            "num_col": id_period,
            "num_row": el.num_row,
            "is_skip": not check_skiplist(
                el.zet, el.discipline.title, el.type_record.title, el.block.title
            ),
            "zet": zet / 36,
            "type": {
                "session": [],
                "value": [],
            },
        }

        if data_element["is_skip"]:
            continue

        # Нагрузка
        for load in loads:
            load_data = {
                "amount": load.amount / 100,
                "amount_type": "ч." if load.ed_izmereniya.id == hour_unit.id else "нед.",
                "id": load.id,
                "control_type_id": load.id_type_control,
                "type": "control" if load.type_control.title in ["Экзамен", "Зачет", "Дифференцированный зачет"] else "load",
                "control_type_title": load.type_control.title,
            }

            if load_data["type"] == "control":
                data_element["type"]["session"].append(load_data)
            else:
                data_element["type"]["value"].append(load_data)
        data.append(data_element)

    return {"data": data}


def elective_disciplines(aup_info: AupInfo) -> dict:
    """
    Функция для получения факультативных дисциплин учебного плана с суммарным объемам по всем видам нагрузок
    Теперь использует названия типов записей вместо ID
    """
    ELECTIVE_TYPE_NAMES = ["Факультатив", "Дисциплина по выбору", "Элективная дисциплина"]

    elective_types = [t.id for t in D_TypeRecord.query.filter(
        D_TypeRecord.title.in_(ELECTIVE_TYPE_NAMES)
    ).all()]

    elective_disciplines = {}
    for el in aup_info.aup_data:
        if el.id_type_record in elective_types:
            try:
                elective_disciplines[el.discipline.title] += el.amount // 100
            except:
                elective_disciplines[el.discipline.title] = el.amount // 100

    return elective_disciplines


def get_default_shortcuts():
    """
    Функция для получения сокращений нагрузки по умолчанию
    """
    data = D_ControlType.query.all()

    if data:
        shortcuts = {el.id: el.default_shortname for el in data}
        return shortcuts

    return None


def get_user_shortcuts(user_id: int):
    """
    Функция для получения пользовательских сокращений нагрузки
    """
    shortcuts = get_default_shortcuts()

    data = {
        el.control_type_id: el.shortname
        for el in ControlTypeShortName.query.filter_by(user_id=user_id).all()
    }

    if data:
        for control_type_id, shortname in data.items():
            shortcuts[control_type_id] = shortname

    return shortcuts