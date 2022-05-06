import pandas as pd
import random
import main
# функция подключения к базе данных, на вход требует путь к базе данных возвращает курсор, который указывает на БД


def start(file, fullname_db):

    cur, conn = main.connect_to_DateBase(fullname_db)
    print("[Start]" + file)
    data = pd.read_excel(file)
    data = data.to_dict(orient='records')
    name_map = file[:-5]

    cur.execute("SELECT id_op FROM tbl_op WHERE Name_OP LIKE ?", [name_map]) #TODO fix name_op
    row = cur.fetchall()
    if row == []:
        cur.execute('INSERT INTO tbl_op (Name_OP, id_faculty) VALUES (?, 1);', [name_map]) #TODO fix name_op
    else:
        print("Данные карты с таким названием уже существуют, произойдет удаление старых данных!")
        cur.execute('DELETE FROM workload WHERE id_op LIKE ?;', [row[0][0]]) 
    for i in range(len(data)):
        xl = data[i]
        cur.execute('SELECT id_op FROM tbl_op WHERE Name_OP LIKE ?', [name_map]) #TODO fix name_op
        pe_id = cur.fetchall()[0][0]
        block = xl['Блок']
        part = xl['Часть']
        mod = xl['Модуль']
        if str(mod) == 'nan':
            mod = 'Без названия'
        cur.execute('SELECT ID_module FROM tbl_module WHERE Name_module LIKE ?', [mod])
        row = cur.fetchall()
        if row != []:
            mod_id = row[0][0]
        else:
            r = lambda: random.randint(0, 255)
            color = '%02X%02X%02X' % (r(), r(), r())
            cur.execute('INSERT INTO tbl_module (Name_module, Color) VALUES (?, ?);', [mod, color])
            cur.execute('SELECT ID_module FROM tbl_module WHERE Name_module LIKE ?', [mod])
            mod_id = cur.fetchall()[0][0]
        record_t = xl['Тип записи']
        cypher = xl['Шифр']
        discipline = xl['Дисциплина']
        sem = xl['Период контроля']
        nagruzka = xl['Нагрузка']
        kolich = str(xl['Количество'])
        ed_izm = xl['Единица измерения']
        zet = str(xl['ЗЕТ'])
        if kolich == 'nan':
            kolich = 0
        if zet == 'nan':
            zet = 0
        cur.execute(
            """INSERT INTO workload (id_aup, block, Part, ID_module, Record_type, Cypher, Discipline, Period, Load, Quantity, Measurement, ZET) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
            [pe_id, block, part, mod_id, record_t, cypher, discipline, sem,  nagruzka, float(kolich), ed_izm, float(zet)])
    cur.commit()
    cur.close()
    del cur
    conn.close()
    print("Отключение от базы данных")