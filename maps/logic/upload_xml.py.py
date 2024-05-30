import xml.etree.ElementTree as et

from maps.models import AupData, AupInfo
from take_from_bd import (create_json)


def create_json_xml(aup):
    aupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    aupData = AupData.query.filter_by(id_aup=aupInfo.id_aup).order_by(AupData.shifr, AupData.discipline,
                                                                      AupData.id_period, AupData.id_type_control).all()

    json = dict()
    json["aup"] = aupInfo.id_aup
    json["Строка"] = list()
    # index = 0
    flag = ""
    flag_sem = ""
    d = dict()
    load = False
    sem = dict()
    load_sem = False
    for i, item in enumerate(aupData):

        if load == True and flag != item.discipline:
            json["Строка"].append(d)
            d = dict()
            load = False

        if flag != item.discipline:

            load = True
            # d['last']=last
            d["Дис"] = item.discipline
            flag = item.discipline
            d["НовЦикл"] = item.type_record.title
            d["НовИдДисциплины"] = d["НовЦикл"] + " что-то (.1.1)"
            d["Цикл"] = d["НовЦикл"] + " что-то (.ДВ8)"
            d["ИдетификаторДисциплины"] = d["НовИдДисциплины"]
            if item.type_control.title == "Зачет":
                type_control = 5
                data = AupData.query.filter_by(id_aup=aupInfo.id_aup, discipline=d["Дис"], id_type_control=5).order_by(
                    AupData.id_period)
                for j, elem in enumerate(data):
                    try:
                        d["СемЗач"] += str(elem.id_period)
                    except:
                        d["СемЗач"] = ""
                        d["СемЗач"] += str(elem.id_period)
            if item.type_control.title == "Экзамен":
                type_control = 5
                data = AupData.query.filter_by(id_aup=aupInfo.id_aup, discipline=d["Дис"], id_type_control=1).order_by(
                    AupData.id_period)
                for j, elem in enumerate(data):
                    try:
                        d["СемЭкз"] += str(elem.id_period)
                    except:
                        d["СемЭкз"] = ""
                        d["СемЭкз"] += str(elem.id_period)
            if item.type_control.title == "Дифференцированный зачет":
                type_control = 5
                data = AupData.query.filter_by(id_aup=aupInfo.id_aup, discipline=d["Дис"], id_type_control=9).order_by(
                    AupData.id_period)
                for j, elem in enumerate(data):
                    try:
                        d["СемДифЗач"] += str(elem.id_period)
                    except:
                        d["СемДифЗач"] = ""
                        d["СемДифЗач"] += str(elem.id_period)
            # data = AupData.query.filter_by(id_aup=aupInfo.id_aup, discipline=d["Дис"],id_type_control=6).order_by(AupData.id_period)
            # for j, elem in enumerate(data):
            #     d["СРС"]=str(elem.amount//100)
            # data = AupData.query.filter_by(id_aup=aupInfo.id_aup, discipline=d["Дис"]).order_by(AupData.id_period)
            d["sem"] = []

            # if item.id_period!=flag_sem and load_sem==True:
            #     d["sem"].append(sem)
            #     sem = dict()

            # if item.id_period!=flag_sem:
            # d["sem"].append(sem)

            data = AupData.query.filter_by(id_aup=aupInfo.id_aup, discipline=d["Дис"]).order_by(AupData.id_period)
            for j, elem in enumerate(data):
                data_2 = data.filter_by(id_period=elem.id_period)
                sem = dict()
                sem["Ном"] = elem.id_period
                for k, ter in enumerate(data_2):
                    if ter.id_type_control == 1:
                        sem["Экз"] = "1"
                    if ter.id_type_control == 2:
                        sem["Лек"] = str(ter.amount // 100)
                    if ter.id_type_control == 4:
                        sem["СРС"] = str(ter.amount // 100)
                    if ter.id_type_control == 6:
                        sem["Лаб"] = str(ter.amount // 100)
                    if ter.id_type_control == 5:
                        sem["Зач"] = "1"
                    if ter.id_type_control == 9:
                        sem["ДифЗач"] = "1"
                    if ter.id_type_control == 18:
                        sem["КП"] = "1"
                if not (sem in d["sem"]):
                    d["sem"].append(sem)

            # flag_sem = 0
            # for j, elem in enumerate(data):
            #     if elem.id_period!=flag_sem and load_sem==False:
            #         load_sem=True
            #         sem["Ном"]=elem.id_period
            # if elem.id_type_control==4:
            #     sem["СРС"] = str(elem.amount//100)
            # if elem.id_type_control==6:
            #     sem["Лаб"]= str(elem.amount//100)
            # if elem.id_type_control==1:
            #     sem["Экз"]= "1"
            # if elem.id_type_control==5:
            #     sem["Зач"]= "1"
            # if elem.id_type_control==9:
            #     sem["ДифЗач"]= "1"
            # if elem.id_type_control==18:
            #     sem["КП"]= "1"
            #         flag_sem = elem.id_period
            #     if elem.id_period==flag_sem:
            #         if elem.id_type_control==4:
            #             sem["СРС"] = str(elem.amount//100)
            #         if elem.id_type_control==6:
            #             sem["Лаб"]= str(elem.amount//100)
            #         if elem.id_type_control==1:
            #             sem["Экз"]= "1"
            #         if elem.id_type_control==5:
            #             sem["Зач"]= "1"
            #         if elem.id_type_control==9:
            #             sem["ДифЗач"]= "1"
            #         if elem.id_type_control==18:
            #             sem["КП"]= "1"
            #         flag_sem = elem.id_period
            #     elif load_sem==True:

            #         d["sem"].append(sem)
            #         flag_sem = elem.id_period
            #         load_sem=False

            # flag_sem = elem.id_period

        # else:

        #     if item.id_period!=flag_sem:

        #         # d["sem"].append(sem)
        #         sem = dict()
        #         sem["Ном"]=item.id_period
        #         if item.id_type_control==4:
        #             sem["СРС"] = str(item.amount//100)
        #         if item.id_type_control==6:
        #             sem["Лаб"]= str(item.amount//100)
        #         if item.id_type_control==1:
        #             sem["Экз"]= "1"
        #         if item.id_type_control==5:
        #             sem["Зач"]= "1"
        #         if item.id_type_control==9:
        #             sem["ДифЗач"]= "1"
        #         if item.id_type_control==18:
        #             sem["КП"]= "1"
        #         flag_sem = item.id_period
        #     else:
        #         if item.id_type_control==4:
        #             sem["СРС"] = str(item.amount//100)
        #         if item.id_type_control==6:
        #             sem["Лаб"]= str(item.amount//100)
        #         if item.id_type_control==1:
        #             sem["Экз"]= "1"
        #         if item.id_type_control==5:
        #             sem["Зач"]= "1"
        #         if item.id_type_control==9:
        #             sem["ДифЗач"]= "1"
        #         if item.id_type_control==18:
        #             sem["КП"]= "1"
        #         flag_sem = item.id_period

        #     # d["sem"].append(sem)

    return json


def create_xml(aup):
    dict = create_json(aup)
    dict_2 = create_json_xml(aup)
    doc = et.Element("Документ")
    doc.set("Тип", "Академический учебный план")
    plan = et.SubElement(doc, "План")
    plan.set("ПодТип", "рабочий учебный план")
    plan.set("Шифр", "PLM")
    plan.set("ОбразовательнаяПрограмма", "подготовка бакалавриатов")  # подтянуть из базы тип обучения Бак/Спец/Маг и тд
    plan.set("ФормаОбучения", "очная")  # тоже самое формой обучения
    plan.set("УровеньОбразования", "ВПО")  # и тут тоже
    titul = et.SubElement(doc, "Титул")
    titul.set("ИмяПлана", "Академический учебный план " + aup + " от 01.11." + str(dict["year"]) + " 0:00:00")
    titul.set("ПолноеИмяПлана", "Академический учебный план " + aup + " от 01.11." + str(dict["year"]) + " 0:00:00")
    titul.set("ИмяВуза",
              "Федеральное государственное автономное образовательное учреждение высшего образования «Московский политехнический университет»")
    titul.set("ИмяВуза2", dict["header"][3])
    titul.set("Факультет", dict["header"][3])
    titul.set("ПоследнийШифр", dict["header"][0])
    titul.set("ГодНачалаПодготовки", str(dict["year"]))
    titul.set("ВидПлана", "2")
    titul.set("КодУровня", "B")
    titul.set("СеместровНаКурсе", "2")
    titul.set("ЭлементовВНеделе", "6")
    titul.set("ТипГОСа", "3.5")
    titul.set("Приложение", "UpVpoGosInsp")
    titul.set("ВерсияПриложения", "22233")
    titul.set("DetailGIA", "1")
    atr_new = et.SubElement(titul, "АтрибутыЦикловНов")
    atr = et.SubElement(titul, "АтрибутыЦиклов")
    spec = et.SubElement(titul, "Специальности")
    stroki_plan = et.SubElement(doc, "СтрокиПлана")

    for item in dict_2["Строка"]:
        line = et.SubElement(stroki_plan, "Строка")
        for key in item.keys():
            if key != "sem":
                line.set(key, item[key])
            else:
                # sem = et.SubElement(line, "Сем")
                for num_sem in item[key]:
                    sem = et.SubElement(line, "Сем")
                    for key_sem in num_sem:
                        print(key_sem, num_sem[key_sem])
                        sem.set(key_sem, str(num_sem[key_sem]))
                        if key_sem == "Лаб":
                            vz = et.SubElement(sem, "VZ")
                            vz.set("ID", "102")
                            vz.set("Н", str(num_sem[key_sem]))
                        elif key_sem == "Лек":
                            vz = et.SubElement(sem, "VZ")
                            vz.set("ID", "101")
                            vz.set("Н", str(num_sem[key_sem]))
                        elif key_sem == "Пр":
                            vz = et.SubElement(sem, "VZ")
                            vz.set("ID", "103")
                            vz.set("Н", str(num_sem[key_sem]))
                        elif key_sem == "СРС":
                            vz = et.SubElement(sem, "VZ")
                            vz.set("ID", "107")
                            vz.set("Н", str(num_sem[key_sem]))
                        elif key_sem == "Сем":
                            vz = et.SubElement(sem, "VZ")
                            vz.set("ID", "107")
                            vz.set("Н", str(num_sem[key_sem]))
    save = et.ElementTree(doc)
    save.write("sample.txt", encoding='UTF-8')
    return open("../../sample.txt", 'r')
