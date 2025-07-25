from datetime import datetime

import pandas
from pandas import DataFrame

from maps.logic.excel_check import ExcelValidator
from maps.logic.read_excel import read_excel
from maps.logic.tools import timeit
from utils.logging import logger

from maps.models import (
    db,
    D_Blocks,
    D_ControlType,
    D_EdIzmereniya,
    D_Modules,
    D_Part,
    D_Period,
    D_TypeRecord,
    SprDegreeEducation,
    SprDiscipline,
    SprFaculty,
    SprFormEducation,
    SprOKCO,
    AupData,
    AupInfo,
    Groups,
    Department,
    NameOP,
)


@timeit
def save_excel_files(files, options):
    files = files.getlist("file")
    logger.info(f"prcessing {len(files)} files...")
    all_files_check_result = []
    for file in files:
        logger.info(f"processing file: {file.filename}")
        try:
            header, data = read_excel(file)
        except Exception as e:
            res = {
                "aup": "-",
                "filename": file.filename,
                "errors": [{"message": "Некорректная структура выгрузки."}],
            }
            all_files_check_result.append(res)
            logger.warning(f"Structure error in excel file: {res['errors']}")
            continue

        aup = header["Содержание"][0]

        res = {
            "aup": aup if not pandas.isna(aup) else "-",
            "filename": file.filename,
            "errors": ExcelValidator.validate(options, header, data),
        }
        all_files_check_result.append(res)

        if res["errors"]:
            logger.warning(f"Validation errors in file: {res['errors']}")
            continue
        else: 
            logger.info('Excel file is valid')

        save_excel_data(
            file.filename,
            header,
            data,
            use_other_modules=options.get("checkboxFillNullModulesModel", False),
        )
    logger.debug("all aups has been processed")
    return all_files_check_result


@timeit
def save_excel_data(
    filename, header: DataFrame, data: DataFrame, use_other_modules: bool = True
):
    logger.debug("saving excel file: {filename}")
    header = header.set_index("Наименование")["Содержание"].to_dict()
    groups = None
    try:
        if aup_info := AupInfo.query.filter_by(num_aup=header["Номер АУП"]).first():
            groups = {el.discipline.title: el for el in aup_info.aup_data}
            db.session.query(AupData).filter(AupData.id_aup == aup_info.id_aup).delete()
            db.session.delete(aup_info)

        aup_info = save_aup_info(filename, header)
        db.session.add(aup_info)
        db.session.flush()
        aup_data = save_aup_data(
            data, aup_info, saved_groups=groups, use_other_modules=use_other_modules
        )
        db.session.bulk_save_objects(aup_data)
    except Exception as e:
        db.session.rollback()
        logger.error(e)
        raise e

    finally:
        logger.debug("excel file succesfully saved.")
        db.session.commit()


@timeit
def save_aup_info(filename: str, header: DataFrame) -> AupInfo:
    if not (
        faculty := SprFaculty.query.filter_by(name_faculty=header["Факультет"]).first()
    ):
        faculty = SprFaculty(name_faculty=header["Факультет"], id_branch=1)
        db.session.add(faculty)

    if not (
        department := Department.query.filter_by(
            name_department=header["Выпускающая кафедра"]
        ).first()
    ):
        department = Department(name_department=header["Выпускающая кафедра"])
        db.session.add(department)

    if not (
        name_op := NameOP.query.filter_by(
            name_spec=header["Профиль (специализация)"]
        ).first()
    ):
        name_op = create_name_op(header)
        db.session.add(name_op)

    if not (
        id_degree := SprDegreeEducation.query.filter_by(
            name_deg=header["Уровень образования"]
        ).first()
    ):
        id_degree = SprDegreeEducation(name_deg=header["Уровень образования"])
        db.session.add(id_degree)
        db.session.flush()
    id_degree = id_degree.id_degree

    years, months = get_education_duration(header["Фактический срок обучения"])
    begin, end = header["Период обучения"].split(" - ")
    is_actual = datetime.today().year < int(end)
    form = SprFormEducation.query.filter_by(form=header["Форма обучения"]).first()

    aup = AupInfo(
        file=filename,
        num_aup=header["Номер АУП"],
        base=header["На базе"],
        id_faculty=faculty.id_faculty,
        id_rop=1,
        type_educ=header["Вид образования"],
        qualification=header["Квалификация"],
        type_standard=header["Тип стандарта"],
        id_department=department.id_department,
        period_educ=header["Период обучения"],
        id_degree=id_degree,
        id_form=form.id_form,
        years=years,
        months=months,
        id_spec=name_op.id_spec,
        year_beg=begin,
        year_end=end,
        is_actual=is_actual,
    )

    return aup


@timeit
def save_aup_data(
    data: DataFrame,
    aup_info: AupInfo,
    saved_groups: dict | None = None,
    use_other_modules: bool = False,
) -> list[AupData]:
    get_group_from_module = (
        lambda module: module[8:-1].strip() if "Модуль" in module else module
    )

    blocks = fill_spr_from_aup_data_values(data["Блок"], D_Blocks)
    parts = fill_spr_from_aup_data_values(data["Часть"], D_Part)
    record_types = fill_spr_from_aup_data_values(data["Тип записи"], D_TypeRecord)
    disciplines = fill_spr_from_aup_data_values(data["Дисциплина"], SprDiscipline)
    periods = fill_spr_from_aup_data_values(data["Период контроля"], D_Period)
    control_types = fill_spr_from_aup_data_values(data["Нагрузка"], D_ControlType)
    measures = fill_spr_from_aup_data_values(data["Ед. изм."], D_EdIzmereniya)

    modules_mapping = {}
    if use_other_modules:
        modules_mapping = get_discipline_module_mapper()

    modules = fill_spr_from_aup_data_values(data["Модуль"], D_Modules, color="#5f60ec")

    # Extract a string between double quotes in module title
    group_names = [get_group_from_module(el) for el in data["Модуль"]]

    groups = fill_groups_from_aup_data_values(group_names)
    num_rows = get_num_rows(data)

    db.session.flush()
    instances = []
    for _, row in data.iterrows():
        id_discipline = disciplines[row["Дисциплина"]].id

        module = modules[row["Модуль"]]
        if module.title == "Без названия" and use_other_modules:
            row["Модуль"] = modules_mapping.get(id_discipline, row["Модуль"])
            module = modules[row["Модуль"]]

        group_title = get_group_from_module(row["Модуль"])
        group = (
            saved_groups[row["Дисциплина"]]
            if saved_groups and row["Дисциплина"] in saved_groups
            else groups[group_title]
        )

        aup_data = AupData(
            id_aup=aup_info.id_aup,
            id_block=blocks[row["Блок"]].id,
            shifr=row["Шифр"],
            id_part=parts[row["Часть"]].id,
            id_module=module.id,
            id_group=group.id_group,
            id_type_record=record_types[row["Тип записи"]].id,
            id_discipline=id_discipline,
            _discipline=row["Дисциплина"],
            id_period=periods[row["Период контроля"]].id,
            num_row=num_rows[(row["Период контроля"], row["Дисциплина"])],
            id_type_control=control_types[row["Нагрузка"]].id,
            amount=int(row["Количество"] * 100),
            id_edizm=measures[row["Ед. изм."]].id,
            zet=int(row["ЗЕТ"] * 100),
        )
        instances.append(aup_data)

    return instances


def get_education_duration(duration: str) -> tuple:
    match duration.split():
        case years, _:
            months = None
        case years, _, months, _:
            ...
        case _:
            years, months = None, None
    return years, months


def create_name_op(header: DataFrame):
    okso: SprOKCO = SprOKCO.query.filter_by(
        program_code=header["Код специальности"]
    ).first()
    num = len(okso.profiles) + 1
    return NameOP(
        program_code=okso.program_code,
        num_profile=f"{num:02}",
        name_spec=header["Профиль (специализация)"],
    )


@timeit
def fill_spr_from_aup_data_values(values, model, **kwargs):
    # TODO: Change this
    print(model.__name__, end="\t")
    values = list(values)

    instances = model.query.all()
    instances = {el.title: el for el in instances}
    created_instances = []
    for el in values:
        if el not in instances:
            created_instances.append({"title": el, **kwargs})
            instances.update({el: None})

    if len(created_instances) == 0:
        return instances
    db.session.bulk_insert_mappings(model, created_instances)

    return {el.title: el for el in model.query.all()}


@timeit
def fill_groups_from_aup_data_values(values):
    values = list(values)

    instances = Groups.query.all()
    instances = {el.name_group: el for el in instances}
    created_instances = []
    for el in values:
        if el not in instances:
            created_instances.append({"name_group": el, "color": "#5f60ec"})
            instances.update({el: None})

    if len(created_instances) == 0:
        return instances
    db.session.bulk_insert_mappings(Groups, created_instances)

    return {el.name_group: el for el in Groups.query.all()}


@timeit
def get_num_rows(data: DataFrame) -> dict[tuple[str, str], int]:
    default_weight = 5
    weights = {
        "Проектная деятельность": 10,
        "Введение в проектную деятельность": 10,
        "Управление проектами": 10,
        "Иностранный язык": 1,
    }

    periods = {}

    for _, row in data.iterrows():
        period, discipline = row["Период контроля"], row["Дисциплина"]
        weight = weights.get(discipline, default_weight)
        value = (discipline, weight)

        if period not in periods:
            periods.update({period: [value]})
        else:
            periods[period].append(value)
    res = {}
    for period, value in periods.items():
        value.sort(key=lambda x: (x[1], x[0]))
        for i, (discipline, _) in enumerate(value, start=1):
            res.update({(period, discipline): i})

    return res


@timeit
def get_discipline_module_mapper() -> dict[int, int]:
    from collections import defaultdict, Counter

    res = (
        db.session.query(AupData.id_discipline, D_Modules.title)
        .join(D_Modules)
        .filter(D_Modules.title.ilike('%модуль%"%"'))
        .all()
    )

    grouped = defaultdict(list)

    for id1, id2 in res:
        grouped[id1].append(id2)

    result = []

    for id1, id2_list in grouped.items():
        count = Counter(id2_list)
        id2_with_max_count = max(count.items(), key=lambda x: x[1])[0]
        result.append((id1, id2_with_max_count))

    result.sort(key=lambda x: x[0])
    return dict(result)
