import pandas as pd
from random import randint
import re
import pyodbc

def connect_to_DateBase(fullname_db):
    try:
        conn_string = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + fullname_db
        conn = pyodbc.connect(conn_string)
        cursor = conn.cursor()
        print("[+] Подключение к базе данных")
        return cursor, conn
    except pyodbc.Error as e:
        print("[!] Ошибка подключения к базе данных", e)


def start(files, dbfilename):
    """Write to DataBase data from exel files. 
        :param files: path to file
        :type files: str or list
        
        :param dbfilename: path to DataBase
        :type files: str"""
    
    cursor, conn = connect_to_DateBase(dbfilename)
    
    if type(files) != list:
        f = files
        files = [f,]

    for file in files:
        filename = re.split('\/', file)[-1]
        
        if len(files) > 1:
            print(f'[!] Файл: {filename}')
        
        data = pd.read_excel(file, sheet_name='Лист1')
        
        aup_num = filename.split(' - ')[1]
            
        row = cursor.execute('SELECT id_aup FROM tbl_aup WHERE num_aup LIKE ?', [aup_num]).fetchall()    
        if row == []:
            # print(data["Содержание"][8])
            id_faculty = cursor.execute("SELECT faculty_id FROM spr_faculty WHERE name_faculty LIKE ?", [data["Содержание"][8]]).fetchall()[0][0]
            year_begin = data["Содержание"][11]
            program_code = data["Содержание"][4]
            type_education = data["Содержание"][1]
            if data["Содержание"][2] == "Бакалавриат":
                data["Содержание"][2] = "Бакалавр"
            id_degree = cursor.execute("SELECT id_degree FROM spr_degree_education WHERE name_deg LIKE ?", [data["Содержание"][2]]).fetchall()[0][0]
            qualification = data["Содержание"][1]
            cursor.execute("INSERT INTO spr_specialization (num_spec, name_spec) VALUES (?, ?)", [data["Содержание"][4], data["Содержание"][6]])
            id_spec = cursor.execute("SELECT id_spec FROM spr_specialization WHERE name_spec LIKE ?", [data["Содержание"][6]]).fetchall()[0][0]
            type_standart = data["Содержание"][7]
            department = data["Содержание"][9]
            period_edication = data["Содержание"][12]
            direction = data["Содержание"][3]
            id_form = cursor.execute("SELECT id_form FROM spr_form_education WHERE form LIKE ?", [data["Содержание"][10]]).fetchall()[0][0]
            
            #TODO fix id_rop
            cursor.execute(""" INSERT INTO tbl_op (id_faculty, year_begin, program_code, type_educ, id_degree, qualification, 
                id_spec, type_standard, department, period_educ, direction, id_form, id_rop) VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?)""", [id_faculty, year_begin, program_code, type_education, id_degree, qualification, id_spec, type_standart, department, period_edication, direction, id_form, 1])
            
            id_op = cursor.execute("SELECT id_op FROM tbl_op ORDER BY id_op DESC").fetchall()[0][0]
            base = data["Содержание"][13]
            fso = data["Содержание"][14]
            
            cursor.execute("INSERT INTO tbl_aup (file, num_aup, id_op, base, fso) VALUES (?, ?, ?, ?, ?)", [filename, aup_num, id_op, base, fso]) 
        else: 
            print("[!] Данные карты с таким названием уже существуют, произойдет удаление старых данных!")
            cursor.execute('DELETE FROM workload WHERE id_aup LIKE ?', [row[0][0]])
        
        
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


        data = pd.read_excel(file, sheet_name="Лист2")
        id_aup = cursor.execute("SELECT id_aup FROM tbl_aup WHERE num_aup LIKE ?", [aup_num]).fetchall()[0][0]
        
        for i in range(len(data)):
            row = []
            for column in data.columns:
                row.append(data[column][i])
            
            if pd.isna(row[3]):
                row[3] = 'Без названия'
            mod_id = cursor.execute("SELECT id_module FROM tbl_module WHERE name_module LIKE ?", [row[3],]).fetchall()

            if mod_id != []:
                mod_id = mod_id[0][0]
            else:
                r = lambda: randint(0,255)
                color = '%02X%02X%02X' % (r(),r(),r())
                cursor.execute("INSERT INTO tbl_module (name_module, color) VALUES (?, ?)", [row[3], color])
                mod_id = cursor.execute("SELECT id_module FROM tbl_module WHERE name_module LIKE ?", [row[3]]).fetchall()[0][0]

            if pd.isna(row[8]):
                row[8] = None
            
            if pd.isna(row[10]):
                row[10] = None
            
            row[3] = mod_id

            row.insert(0, id_aup)
            cursor.execute('''INSERT INTO workload (id_aup, block, cypher, part, id_module, record_type, discipline, period, load, quantity, measurement, zet) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', row)
    
    cursor.commit()
    cursor.close()    
    conn.close()
    print("[+] Запись данных завершена. Отключение от БД")