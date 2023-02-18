import os
import pandas as pd
from random import randint
from flask import Blueprint, request
import re
import datetime
from sqlalchemy import desc
from models import AUP, OP, Module, NameOP, SprDegreeEducation, SprFormEducation, SprFaculty, Workload, DurationEducation, WorkMap, db

# from app import static_folder

bp = Blueprint('upload_to_db', __name__, url_prefix='/upload_to_db')

WORKLOAD_PARAMS = ['id_aup', 'block', 'cypher', 'part', 'id_module', 'id_group', 'record_type', 'discipline', 'period', 'load', 'quantity', 'measurement', 'zet']
NAMEOP_PARAMS = ['program_code', 'num_profile', 'name_spec']
DURATION_EDUC_PARAMS = ['id_degree', 'id_form', 'years', 'months', 'id_spec', 'year_beg', 'year_end', 'is_actual']
OP_PARAMS = ['id_duration', 'id_faculty', 'id_rop', 'type_educ', 'qualification', 'type_standard', 'department', 'period_educ']
AUP_PARAMS = ['id_op', 'file', 'num_aup', 'base']
MODULE_PARAMS = ['name_module', 'color']

def _params(params_list, _PARAMS):
    temp_dict = {}
    for i in range(len(_PARAMS)):
        temp_dict[_PARAMS[i]] = params_list[i]
    return temp_dict

def save_into_bd(files):
    """Write to DataBase data from exel files. 
        :param files: path to file
        :type files: str or list

        :param dbfilename: path to DataBase
        :type files: str
    """

    if type(files) != list:
        f = files
        files = [f, ]

    for file in files:
        filename = file.split('/')[-1]
        filename = filename.split('\\')[-1]

        if len(files) > 1:
            print(f'[!] Файл: {filename}')

        # print('----------------------------', files)

        # ЛИСТ 1

        data = pd.read_excel(file, sheet_name='Лист1')

        print(data)

        print("[DEBUG] filename = ", filename)
        aup_num = filename.split(' - ')[1]
        #       ЗДЕСЬ МОГЛА БЫТЬ ПРОВЕРКА НА СУЩЕСТВУЮЩИЙ АУП (ЕСЛИ СУЩЕСТВУЕТ - УДЯЛЕМ ВСЕ ИЗ WORKLOAD И ДОБАВЛЯЕМ СНИЗУ ЗАНОВО)
        data = data['Содержание']

        #                     Наименование
        # 0                     Номер АУП
        # 1               Вид образования
        # 2           Уровень образования
        # 3   Направление (специальность)
        # 4             Код специальности
        # 5                  Квалификация
        # 6       Профиль (специализация)
        # 7                 Тип стандарта
        # 8                     Факультет
        # 9           Выпускающая кафедра
        # 10               Форма обучения
        # 11                   Год набора
        # 12              Период обучения
        # 13                      На базе
        # 14    Фактический срок обучения
        type_education = data[1]
        degree = data[2]
        direction = data[3]
        program_code = data[4]
        qualification = data[5]
        name_spec = data[6]
        type_standard = data[7]
        name_faculty = data[8]
        department = data[9]
        form_educ = data[10]
        years_begin = data[11]
        period_edication = data[12]
        base = data[13]
        fso = data[14]

        id_faculty = SprFaculty.query.filter_by(
            name_faculty=name_faculty).first().id_faculty

        id_degree = SprDegreeEducation.query.filter_by(
            name_deg=degree).first().id_degree
        
        years, months = take_duration_year_month(fso)
        year_beg, year_end = set_year_begin_end(period_edication)
        is_actual = check_actual(year_end)

        # Проверка на наличие кода профиля:
        # Сначала проверяем есть ли уже такая специализация - если есть, то не добавляем ее
        # Если нет - то проверяем существуют ли вообще 
        if NameOP.query.filter_by(name_spec=name_spec).first() == None:
            take_profiles_from_nameop = NameOP.query.filter_by(program_code=program_code).order_by(desc(NameOP.num_profile)).first()
            if take_profiles_from_nameop == None:
                take_profiles_from_nameop = '01'
            else:
                take_profiles_from_nameop = take_profiles_from_nameop.num_profile
                take_profiles_from_nameop = str(int(take_profiles_from_nameop) + 1 )
                take_profiles_from_nameop_len = len(take_profiles_from_nameop)
                if take_profiles_from_nameop_len < 2: # number 2 is the max length of profile code
                    take_profiles_from_nameop = "0" * (2 - take_profiles_from_nameop_len) + take_profiles_from_nameop

            
            new_nameop = NameOP(**_params([program_code, take_profiles_from_nameop, name_spec], NAMEOP_PARAMS))
            db.session.add(new_nameop)

        id_spec = NameOP.query.filter_by(name_spec=name_spec).first().id_spec
        if pd.isna(department):
            department = None
        id_form = SprFormEducation.query.filter_by(
            form=form_educ).first().id_form

        

        new_str_tbl_duration = DurationEducation(**_params([id_degree, id_form, years, months, id_spec, year_beg, year_end, is_actual], DURATION_EDUC_PARAMS))
        db.session.add(new_str_tbl_duration)
        db.session.commit()

        id_duration = new_str_tbl_duration.id_duration

        new_str_tbl_op = OP(**_params([id_duration, id_faculty, 1, type_education, qualification, type_standard, department, period_edication], OP_PARAMS)) # ЗАМЕСТО ВЕРХНЕЙ СТРОЧКИ
        db.session.add(new_str_tbl_op)
        db.session.commit()

        id_op = new_str_tbl_op.id_op
        
        new_str_tbl_aup = AUP(**_params([id_op, filename, aup_num, base], AUP_PARAMS))
        db.session.add(new_str_tbl_aup)
        db.session.commit()

        # добавить модуль в tbl_module и получить id, заменить модуль на id
        # #   Column           Non-Null Count  Dtype
        # ---  ------           --------------  -----
        # 0   Блок             93 non-null     object
        # 1   Шифр             93 non-null     object
        # 2   Часть            93 non-null     object
        # 3   Модуль           0 non-null      float64
        # 4   Тип записи       93 non-null     object
        # 5   Дисциплина       93 non-null     object
        # 6   Период контроля  93 non-null     object
        # 7   Нагрузка         93 non-null     object
        # 8   Количество       62 non-null     object
        # 9   Ед. изм.         93 non-null     object
        # 10  ЗЕТ              62 non-null     object

        # ЛИСТ 2

        update_workload(file, aup_num) ### Закинуть файлы в бд

    db.session.commit()
    print("[+] Запись данных завершена. Отключение от БД")
    # path = os.path.join(static_folder, 'temp', filename)
    # os.remove(path)
    return new_str_tbl_aup


def update_workload(file, aup_num):
    data = pd.read_excel(file, sheet_name="Лист2")

    id_aup = AUP.query.filter_by(num_aup = aup_num).first().id_aup

    for i in range(len(data)):
        row = []
        for column in data.columns:
            row.append(data[column][i])

        if pd.isna(row[3]):
            row[3] = 'Без названия'

        mod_id = Module.query.filter_by(name_module = row[3]).first()
        if mod_id == None:
            def r(): return randint(0, 128)
            color = '%02X%02X%02X' % (r(), r(), r())

            new_module = Module(**_params([row[3], color], MODULE_PARAMS))
            db.session.add(new_module)
            db.session.commit()

            mod_id = Module.query.filter_by(name_module = row[3]).first().id_module
        else:
            mod_id = mod_id.id_module

        if pd.isna(row[8]):
            row[8] = 0
        else:
            try:
                row[8] = int(float(row[8].replace(',', '.')))
            except:
                row[8] = int(float(row[8]))

        if pd.isna(row[10]):
            row[10] = 0
        else:
            try:
                row[10] = float(row[10].replace(',', '.'))
            except:
                row[10] = float(row[10])
                
        row[3] = mod_id

        row.insert(0, id_aup)
        row = list(map(lambda x: None if pd.isna(x) else x, row))
        # print('+++++++++++++++++', row)
        row.insert(5, None)
        new_str_workload = Workload(**_params(row, WORKLOAD_PARAMS))
        db.session.add(new_str_workload)
    db.session.commit()


def delete_from_workload(aup):
    
    id_aup = AUP.query.filter_by(num_aup=aup).first().id_aup
    Workload.query.filter_by(id_aup=id_aup).delete()
    db.session.commit()


def delete_from_workmap(aup):
    id_aup = AUP.query.filter_by(num_aup=aup).first().id_aup
    WorkMap.query.filter_by(id_aup=id_aup).delete()
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
        return True
    else: 
        return False
