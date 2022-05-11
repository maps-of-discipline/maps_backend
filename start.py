import pandas as pd
from random import randint
import re


# def connect_to_DateBase(fullname_db):
#     try:
#         conn_string = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + fullname_db
#         conn = pyodbc.connect(conn_string)
#         cursor = conn.cursor()
#         print("[+] Подключение к базе данных")
#         return cursor, conn
#     except pyodbc.Error as e:
#         print("[!] Ошибка подключения к базе данных", e)


def start(files, Cursor):
    """Write to DataBase data from exel files. 
        :param files: path to file
        :type files: str or list
        
        :param dbfilename: path to DataBase
        :type files: str"""
    
    cursor = Cursor
    
    if type(files) != list:
        f = files
        files = [f,]

    for file in files:
        filename = re.split('\/', file)[-1]
        
        if len(files) > 1:
            print(f'[!] Файл: {filename}')
        
        data = pd.read_excel(file, sheet_name='Лист1')
        
        aup_num = filename.split(' - ')[1]
        
        cursor.execute(f'SELECT id_aup FROM tbl_aup WHERE num_aup LIKE "{aup_num}"')
        print("[DEBUG] row = ", cursor.fetchall())
        row = cursor.fetchall()
        if not row:
            data = data['Содержание']
            cursor.execute('SELECT faculty_id FROM spr_faculty WHERE name_faculty LIKE %s', (data[8],))
            id_faculty = cursor.fetchall()[0][0]
            year_begin = data[11]
            program_code = data[4]
            type_education = data[1]
            if data[2] == "Бакалавриат":
                data[2] = "Бакалавр"
            cursor.execute("SELECT id_degree FROM spr_degree_education WHERE name_deg LIKE %s", (data[2],))
            id_degree = cursor.fetchall()[0][0]
            qualification = data[1]
            cursor.execute("INSERT INTO spr_specialization (num_spec, name_spec) VALUES (%s, %s)", (data[4], data[6],))
            cursor.execute("SELECT id_spec FROM spr_specialization WHERE name_spec LIKE %s", (data[6],))
            id_spec = cursor.fetchall()[0][0]
            type_standart = data[7]
            department = data[9]
            if pd.isna(department):
                department = None 
            period_edication = data[12]
            direction = data[3]
            cursor.execute("SELECT id_form FROM spr_form_education WHERE form LIKE %s", (data[10],))
            id_form = cursor.fetchall()[0][0]
            
            #TODO fix id_rop
            
            cursor.execute("""INSERT INTO tbl_op (id_faculty, year_begin, program_code, type_educ, id_degree, qualification, 
                id_spec, type_standard, department, period_educ, direction, id_form, id_rop) VALUES
                (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", [id_faculty, year_begin, program_code, type_education, id_degree, qualification, id_spec, type_standart, department, period_edication, direction, id_form, 1])
            
            cursor.execute("SELECT id_op FROM tbl_op ORDER BY id_op DESC") 
            id_op = cursor.fetchall()[0][0]
            base = data[13]
            fso = data[14]
            cursor.execute("INSERT INTO tbl_aup (file, num_aup, id_op, base, fso) VALUES (%s, %s, %s, %s, %s)", (filename, aup_num, id_op, base, fso,)) 
        else: 
            print("[!] Данные карты с таким названием уже существуют, произойдет удаление старых данных!")
            cursor.execute('DELETE FROM workload WHERE id_aup LIKE %s', [row[0][0]])
        
        
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
        cursor.execute("SELECT id_aup FROM tbl_aup WHERE num_aup LIKE %s", [aup_num])
        id_aup = cursor.fetchall()[0][0]
        for i in range(len(data)):
            row = []
            for column in data.columns:
                row.append(data[column][i])
            
            if pd.isna(row[3]):
                row[3] = 'Без названия'
            cursor.execute("SELECT id_module FROM tbl_module WHERE name_module LIKE %s", [row[3],])
            mod_id = cursor.fetchall()
            if mod_id != []:
                mod_id = mod_id[0][0]
            else:
                r = lambda: randint(0,255)
                color = '%02X%02X%02X' % (r(),r(),r())
                cursor.execute("INSERT INTO tbl_module (name_module, color) VALUES (%s, %s)", [row[3], color])
                mod_id = cursor.execute("SELECT id_module FROM tbl_module WHERE name_module LIKE %s", [row[3]]).fetchall()[0][0]

            if pd.isna(row[8]):
                row[8] = 0
            else: row[8] = int(float(row[8].replace(',', '.')))

            if pd.isna(row[10]):
                row[10] = 0
            else:
                row[10] = float(row[10].replace(',', '.'))
            
            row[3] = mod_id

            row.insert(0, id_aup)
            print(row)

            
            
            cursor.execute('''INSERT INTO workload (`id_aup`, `block`, `cypher`, `part`, `id_module`, `record_type`, `discipline`, `period`, `load`, `quantity`, `measurement`, `zet`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''', row)
    

    cursor.close()    
    print("[+] Запись данных завершена. Отключение от БД")
    return aup_num