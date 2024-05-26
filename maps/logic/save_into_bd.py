import datetime

import pandas as pd
from sqlalchemy import desc

from maps.logic.tools import timeit
from maps.models import AupData, AupInfo, NameOP, SprDegreeEducation, SprFormEducation, SprFaculty, Department, db

NAMEOP_PARAMS = ['program_code', 'num_profile', 'name_spec']
AUP_PARAMS = ['file', 'num_aup', 'base', 'id_faculty', 'id_rop', 'type_educ',
              'qualification', 'type_standard', 'period_educ',
              'id_degree', 'id_form', 'years', 'months', 'id_spec', 'year_beg', 'year_end', 'is_actual',
              'id_department']


def _params(params_list, _PARAMS):
    temp_dict = {}
    for i in range(len(_PARAMS)):
        temp_dict[_PARAMS[i]] = params_list[i]
    return temp_dict


def delete_from_aupdata(aup):
    AupData.query.filter_by(id_aup=aup.id_aup).delete()
    db.session.commit()


def take_duration_year_month(fso):
    arr_fso = fso.split(' ')
    year = arr_fso[0]
    try:
        month = arr_fso[2]
    except:
        month = None
    return year, month


def set_year_begin_end(duration):
    arr_duration = duration.split(' ')
    y_begin = arr_duration[0]
    y_end = arr_duration[2]
    return y_begin, y_end


def check_actual(year_end):
    year_now = datetime.date.today().year
    if year_now > int(year_end):
        return False
    else:
        return True


def SaveCard(db, aupInfo, aupData):
    # посмотреть есть ли в таблице факультетов такой факультет и если нет, то добавить
    get_faculty = SprFaculty.query.filter_by(name_faculty=aupInfo["name_faculty"]).first()

    if get_faculty is None:
        new_faculty = SprFaculty(
            name_faculty=aupInfo["name_faculty"],
            id_branch=1,
            dean=None)
        db.session.add(new_faculty)

    if pd.isna(aupInfo['department']):
        aupInfo['department'] = None

    get_department = Department.query.filter_by(name_department=aupInfo['department']).first()
    if get_department is None:
        new_department = Department(name_department=aupInfo['department'], )
        db.session.add(new_department)

    db.session.commit()

    group = {

    }

    # Перезапись карты, если есть уже в базе и мы обновляем ее
    get_aup = AupInfo.query.filter_by(num_aup=aupInfo["num"]).first()

    if get_aup:
        for item in get_aup.aup_data:
            item:AupData
            group.update({item.discipline: item.id_group})


        db.session.delete(get_aup)
        db.session.commit()

    get_aup = add_new_aup(aupInfo)


    l = list()
    temp_i = 0
    for i in aupData:
        temp_i += 1
        id_group = i[11]
        if group and i[5] in group:
            id_group = group[i[5]]

        new_row = AupData(id_aup=get_aup.id_aup, id_block=i[0], shifr=i[1], id_part=i[2], id_module=i[3],
                          id_group=id_group, id_type_record=i[4],
                          discipline=i[5], id_period=i[6], id_type_control=i[7], amount=int(i[8]), id_edizm=i[9],
                          zet=int(i[10]), num_row=i[12])
        l.append(new_row)

    if temp_i == len(aupData): print('VALID DATA')
    db.session.bulk_save_objects(l)
    db.session.commit()


def add_new_aup(aupInfo):
    id_faculty = SprFaculty.query.filter_by(
        name_faculty=aupInfo["name_faculty"]).first().id_faculty

    id_degree = SprDegreeEducation.query.filter_by(
        name_deg=aupInfo["degree"]).first().id_degree

    years, months = take_duration_year_month(aupInfo["full_years"])
    year_beg, year_end = set_year_begin_end(aupInfo["period_edication"])
    is_actual = check_actual(year_end)

    # Проверка на наличие кода профиля:
    # Сначала проверяем есть ли уже такая специализация - если есть, то не добавляем ее
    # Если нет - то проверяем существуют ли вообще специализации по этому коду программы
    # name_op_row = NameOP.query.filter_by(name_spec=aupInfo["name_spec"]).first()
    if NameOP.query.filter_by(name_spec=aupInfo["name_spec"]).first() == None:
        take_profiles_from_nameop = NameOP.query.filter_by(
            program_code=aupInfo["program_code"]).order_by(desc(NameOP.num_profile)).first()
        if take_profiles_from_nameop == None:
            take_profiles_from_nameop = '01'
        else:
            take_profiles_from_nameop = str(int(take_profiles_from_nameop.num_profile) + 1)
            take_profiles_from_nameop_len = len(take_profiles_from_nameop)
            if take_profiles_from_nameop_len < 2:  # number 2 is the max length of profile code
                take_profiles_from_nameop = "0" * \
                                            (2 - take_profiles_from_nameop_len) + \
                                            take_profiles_from_nameop

        new_nameop = NameOP(
            **_params([aupInfo["program_code"], take_profiles_from_nameop, aupInfo["name_spec"]], NAMEOP_PARAMS))
        db.session.add(new_nameop)

    id_spec = NameOP.query.filter_by(
        name_spec=aupInfo["name_spec"]).first().id_spec

    id_department = Department.query.filter_by(name_department=aupInfo['department']).first().id_department
    id_form = SprFormEducation.query.filter_by(
        form=aupInfo["form_educ"]).first().id_form

    new_str_tbl_aup = AupInfo(**_params([
        aupInfo["filename"], aupInfo["num"], aupInfo["base"], id_faculty, 1, aupInfo["type_education"],
        aupInfo["qualification"],
        aupInfo["type_standard"], aupInfo["period_edication"], id_degree, id_form, years, months, id_spec, year_beg,
        year_end, is_actual, id_department], AUP_PARAMS))
    db.session.add(new_str_tbl_aup)
    db.session.commit()

    return new_str_tbl_aup
