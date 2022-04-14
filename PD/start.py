import pandas as pd
import random
import main
import os
# функция подключения к базе данных, на вход требует путь к базе данных возвращает курсор, который указывает на БД


def start(file, fullname_db):

    cur, conn = main.connect_to_DateBase(fullname_db)
    data = pd.read_excel(file, sheet_name='Лист2').sort_values(by='Дисциплина')
    data = data.to_dict(orient='records')
    name_map = os.path.basename(file)[:-5]
    cur.execute("SELECT ID_OP FROM OP WHERE Name_OP LIKE ?", [name_map])
    row = cur.fetchall()
    if row == []:
        cur.execute('INSERT INTO OP (Name_OP, Faculty_ID) VALUES (?, 1);', [name_map])
    else:
        #print("Данные карты с таким названием уже существуют, произойдет удаление старых данных!")
        cur.execute('DELETE FROM Load WHERE ID_OP LIKE ?;', [row[0][0]])
    for i in range(len(data)):
        xl = data[i]
        cur.execute('SELECT ID_OP  FROM OP WHERE Name_OP LIKE ?', [name_map])
        pe_id = cur.fetchall()[0][0]
        block = xl['Блок']
        part = xl['Часть']
        mod = xl['Модуль']
        if str(mod) == 'nan':
            mod = 'Без названия'
        cur.execute('SELECT ID_module  FROM Module_reference WHERE Name_module LIKE ?', [mod])
        row = cur.fetchall()
        if row != []:
            mod_id = row[0][0]
        else:
            r = lambda: random.randint(0, 255)
            color = '%02X%02X%02X' % (r(), r(), r())
            cur.execute('INSERT INTO Module_reference (Name_module, Color) VALUES (?, ?);', [mod, color])
            cur.execute('SELECT ID_module  FROM Module_reference WHERE Name_module LIKE ?', [mod])
            mod_id = cur.fetchall()[0][0]
        record_t = xl['Тип записи']
        cypher = xl['Шифр']
        discipline = xl['Дисциплина']
        sem = xl['Период контроля']
        nagruzka = xl['Нагрузка']
        kolich = str(xl['Количество'])
        ed_izm = xl['Ед. изм.']
        zet = str(xl['ЗЕТ'])
        if kolich == 'nan':
            kolich = '0'
        if zet == 'nan':
            zet = '0'
        cur.execute(
            """INSERT INTO Load (ID_OP, Block, Part, ID_module, Record_type, Cypher, Discipline, Period, Load, Quantity, Measurement, ZET) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
            [pe_id, block, part, mod_id, record_t, cypher, discipline, sem,  nagruzka, float(kolich.replace(",", ".")), ed_izm, float(zet.replace(",", "."))])
    cur.commit()
    cur.close()
    del cur
    conn.close()
    #print("Отключение от базы данных")