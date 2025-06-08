import xml.etree.ElementTree as et

from maps.models import AupData, AupInfo
from maps.logic.take_from_bd import create_json

# Константы для типов контроля
CONTROL_TYPES = {
    "exam": {"id": 1, "name": "Экзамен", "code": "exam"},
    "lecture": {"id": 2, "name": "Лекция", "code": "lecture"},
    "self_study": {"id": 4, "name": "СРС", "code": "self_study"},
    "test": {"id": 5, "name": "Зачет", "code": "test"},
    "lab": {"id": 6, "name": "Лабораторная", "code": "lab"},
    "diff_test": {"id": 9, "name": "Дифференцированный зачет", "code": "diff_test"},
    "course_project": {"id": 18, "name": "КП", "code": "course_project"}
}

# Константы для видов занятий
ACTIVITY_TYPES = {
    "lecture": {"id": 101, "code": "Лек"},
    "lab": {"id": 102, "code": "Лаб"},
    "practice": {"id": 103, "code": "Пр"},
    "self_work": {"id": 107, "code": "СРС"}
}

# Константы для циклов дисциплин
DISCIPLINE_CYCLES = {
    "base": {"num": 1, "abbr": "Б1", "name": "Дисциплины (модули)"},
    "pe_elective": {"num": 4, "name": "Элективные курсы по физической культуре"},
    "practice": {"num": 5, "abbr": "Б2", "name": "Практики"},
    "electives": {"num": 6, "abbr": "ФТД", "name": "Факультативы"},
    "final_cert": {"num": 7, "abbr": "Б3", "name": "Государственная итоговая аттестация"},
    "state_exam": {"num": 8, "abbr": "Б3.Г", "name": "Подготовка и сдача государственного экзамена"},
    "thesis": {"num": 9, "abbr": "Б3.Д", "name": "Подготовка и защита ВКР"},
    "block3": {"num": 10, "abbr": "Блок 3. Государственная итоговая аттестация", "name": "Б.3"},
    "block2": {"num": 11, "abbr": "Блок 2. Практика", "name": "Б.2"},
    "block1": {"num": 12, "abbr": "Блок 1 Дисциплины (модули)", "name": "Б1"},
    "facultative": {"num": 13, "abbr": "Факультативные дисциплины"}
}

def create_json_xml(aup):
    aupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    aupData = AupData.query.filter_by(id_aup=aupInfo.id_aup).order_by(
        AupData.shifr, AupData.id_discipline, AupData.id_period, AupData.id_type_control).all()

    json = dict()
    json["aup"] = aupInfo.id_aup
    json["Строка"] = list()
    flag = ""
    d = dict()
    load = False
    
    for i, item in enumerate(aupData):
        item: AupData

        if load and flag != item.discipline.title:
            json["Строка"].append(d)
            d = dict()
            load = False

        if flag != item.discipline.title:
            load = True
            d["Дис"] = item.discipline.title
            flag = item.discipline.title
            d["НовЦикл"] = item.type_record.title
            d["НовИдДисциплины"] = f"{d['НовЦикл']} что-то (.1.1)"
            d["Цикл"] = f"{d['НовЦикл']} что-то (.ДВ8)"
            d["ИдетификаторДисциплины"] = d["НовИдДисциплины"]
            
            # Заменяем числовые ID типов контроля на строковые идентификаторы
            if item.type_control.title == CONTROL_TYPES["test"]["name"]:
                data = AupData.query.filter_by(
                    id_aup=aupInfo.id_aup, 
                    id_discipline=item.id_discipline, 
                    id_type_control=CONTROL_TYPES["test"]["id"]
                ).order_by(AupData.id_period)
                
                for j, elem in enumerate(data):
                    d.setdefault("СемЗач", "")
                    d["СемЗач"] += str(elem.id_period)
                    
            elif item.type_control.title == CONTROL_TYPES["exam"]["name"]:
                data = AupData.query.filter_by(
                    id_aup=aupInfo.id_aup, 
                    id_discipline=item.id_discipline, 
                    id_type_control=CONTROL_TYPES["exam"]["id"]
                ).order_by(AupData.id_period)
                
                for j, elem in enumerate(data):
                    d.setdefault("СемЭкз", "")
                    d["СемЭкз"] += str(elem.id_period)
                    
            elif item.type_control.title == CONTROL_TYPES["diff_test"]["name"]:
                data = AupData.query.filter_by(
                    id_aup=aupInfo.id_aup, 
                    id_discipline=item.id_discipline, 
                    id_type_control=CONTROL_TYPES["diff_test"]["id"]
                ).order_by(AupData.id_period)
                
                for j, elem in enumerate(data):
                    d.setdefault("СемДифЗач", "")
                    d["СемДифЗач"] += str(elem.id_period)

            d["sem"] = []
            data = AupData.query.filter_by(id_aup=aupInfo.id_aup, id_discipline=item.id_discipline).order_by(AupData.id_period)
            
            for j, elem in enumerate(data):
                data_2 = data.filter_by(id_period=elem.id_period)
                sem = dict()
                sem["Ном"] = elem.id_period
                
                for k, ter in enumerate(data_2):
                    # Заменяем числовые проверки на строковые константы
                    if ter.id_type_control == CONTROL_TYPES["exam"]["id"]:
                        sem["Экз"] = "1"
                    if ter.id_type_control == CONTROL_TYPES["lecture"]["id"]:
                        sem[ACTIVITY_TYPES["lecture"]["code"]] = str(ter.amount // 100)
                    if ter.id_type_control == CONTROL_TYPES["self_study"]["id"]:
                        sem[ACTIVITY_TYPES["self_work"]["code"]] = str(ter.amount // 100)
                    if ter.id_type_control == CONTROL_TYPES["lab"]["id"]:
                        sem[ACTIVITY_TYPES["lab"]["code"]] = str(ter.amount // 100)
                    if ter.id_type_control == CONTROL_TYPES["test"]["id"]:
                        sem["Зач"] = "1"
                    if ter.id_type_control == CONTROL_TYPES["diff_test"]["id"]:
                        sem["ДифЗач"] = "1"
                    if ter.id_type_control == CONTROL_TYPES["course_project"]["id"]:
                        sem["КП"] = "1"
                
                if sem not in d["sem"]:
                    d["sem"].append(sem)

    return json

def create_xml(aup):
    aupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    dict_data = create_json(aup)
    dict_xml = create_json_xml(aup)

    doc = et.Element("Документ")
    doc.set("Тип", "Академический учебный план")
    
    plan = et.SubElement(doc, "План")
    plan.set("ПодТип", "рабочий учебный план")
    plan.set("Шифр", "PLM")
    plan.set("ОбразовательнаяПрограмма", aupInfo.qualification)
    plan.set("ФормаОбучения", str(aupInfo.form.form))
    plan.set("УровеньОбразования", "ВПО")
    
    titul = et.SubElement(doc, "Титул")
    titul.set("ИмяПлана", f"Академический учебный план {aup} от 01.11.{dict_data['year']} 0:00:00")
    titul.set("ПолноеИмяПлана", f"Академический учебный план {aup} от 01.11.{dict_data['year']} 0:00:00")
    titul.set("ИмяВуза", "Федеральное государственное автономное образовательное учреждение высшего образования «Московский политехнический университет»")
    titul.set("ИмяВуза2", dict_data["header"][3])
    titul.set("Факультет", dict_data["header"][3])
    titul.set("ПоследнийШифр", dict_data["header"][0])
    titul.set("ГодНачалаПодготовки", str(dict_data["year"]))
    titul.set("ВидПлана", "2")
    titul.set("КодУровня", "B")
    titul.set("СеместровНаКурсе", "2")
    titul.set("ЭлементовВНеделе", "6")
    titul.set("ТипГОСа", "3.5")
    titul.set("Приложение", "UpVpoGosInsp")
    titul.set("ВерсияПриложения", "22233")
    titul.set("DetailGIA", "1")
    
    atr_new = et.SubElement(titul, "АтрибутыЦикловНов")
    
    # Создаем циклы дисциплин из констант
    for cycle in DISCIPLINE_CYCLES.values():
        cycle_elem = et.SubElement(atr_new, "Цикл")
        cycle_elem.set("Ном", str(cycle["num"]))
        if "abbr" in cycle:
            cycle_elem.set("Аббревиатура", cycle["abbr"])
        if "name" in cycle:
            cycle_elem.set("Название", cycle["name"])
    
    atr = et.SubElement(titul, "АтрибутыЦиклов")
    spec = et.SubElement(titul, "Специальности")
    stroki_plan = et.SubElement(doc, "СтрокиПлана")

    for item in dict_xml["Строка"]:
        line = et.SubElement(stroki_plan, "Строка")
        for key in item.keys():
            if key != "sem":
                line.set(key, item[key])
            else:
                for num_sem in item[key]:
                    sem = et.SubElement(line, "Сем")
                    for key_sem in num_sem:
                        sem.set(key_sem, str(num_sem[key_sem]))
                        
                        # Заменяем числовые ID видов занятий на строковые константы
                        if key_sem == ACTIVITY_TYPES["lab"]["code"]:
                            vz = et.SubElement(sem, "VZ")
                            vz.set("ID", str(ACTIVITY_TYPES["lab"]["id"]))
                            vz.set("Н", str(num_sem[key_sem]))
                        elif key_sem == ACTIVITY_TYPES["lecture"]["code"]:
                            vz = et.SubElement(sem, "VZ")
                            vz.set("ID", str(ACTIVITY_TYPES["lecture"]["id"]))
                            vz.set("Н", str(num_sem[key_sem]))
                        elif key_sem == "Пр":  # Практика
                            vz = et.SubElement(sem, "VZ")
                            vz.set("ID", str(ACTIVITY_TYPES["practice"]["id"]))
                            vz.set("Н", str(num_sem[key_sem]))
                        elif key_sem in [ACTIVITY_TYPES["self_work"]["code"], "Сем"]:
                            vz = et.SubElement(sem, "VZ")
                            vz.set("ID", str(ACTIVITY_TYPES["self_work"]["id"]))
                            vz.set("Н", str(num_sem[key_sem]))

    save = et.ElementTree(doc)
    save.write("sample.txt", encoding='UTF-8')
    return "sample.txt"