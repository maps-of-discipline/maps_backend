import xml.etree.ElementTree as et
from maps.models import AupData, AupInfo
from take_from_bd import create_json

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

# Константы для форм обучения
EDUCATION_FORMS = {
    "full_time": "очная",
    "part_time": "заочная",
    "evening": "вечерняя"
}

# Константы для уровней образования
EDUCATION_LEVELS = {
    "bachelor": "ВПО",
    "master": "ВО",
    "specialist": "СПО"
}

def create_json_xml(aup):
    """Создает JSON-структуру данных для последующего преобразования в XML"""
    aup_info = AupInfo.query.filter_by(num_aup=aup).first()
    aup_data = AupData.query.filter_by(id_aup=aup_info.id_aup).order_by(
        AupData.shifr, AupData.id_discipline, AupData.id_period, AupData.id_type_control).all()

    result = {
        "aup": aup_info.id_aup,
        "Строка": []
    }
    
    current_discipline = None
    discipline_data = {}

    for item in aup_data:
        if current_discipline != item.discipline.title:
            if discipline_data:
                result["Строка"].append(discipline_data)
            
            current_discipline = item.discipline.title
            discipline_data = {
                "Дис": current_discipline,
                "НовЦикл": item.type_record.title,
                "НовИдДисциплины": f"{item.type_record.title} что-то (.1.1)",
                "Цикл": f"{item.type_record.title} что-то (.ДВ8)",
                "ИдетификаторДисциплины": f"{item.type_record.title} что-то (.1.1)",
                "sem": []
            }

            # Обработка типов контроля
            for control_type in ["test", "exam", "diff_test"]:
                control_data = AupData.query.filter_by(
                    id_aup=aup_info.id_aup,
                    id_discipline=item.id_discipline,
                    id_type_control=CONTROL_TYPES[control_type]["id"]
                ).order_by(AupData.id_period)
                
                periods = "".join(str(elem.id_period) for elem in control_data)
                if periods:
                    discipline_data[f"Сем{CONTROL_TYPES[control_type]['name'].replace(' ', '')}"] = periods

        # Обработка данных по семестрам
        semester_data = AupData.query.filter_by(
            id_aup=aup_info.id_aup, 
            id_discipline=item.id_discipline
        ).order_by(AupData.id_period)
        
        for semester in semester_data:
            semester_group = semester_data.filter_by(id_period=semester.id_period)
            sem_dict = {"Ном": semester.id_period}
            
            for activity in semester_group:
                if activity.id_type_control == CONTROL_TYPES["exam"]["id"]:
                    sem_dict["Экз"] = "1"
                elif activity.id_type_control == CONTROL_TYPES["lecture"]["id"]:
                    sem_dict[ACTIVITY_TYPES["lecture"]["code"]] = str(activity.amount // 100)
                elif activity.id_type_control == CONTROL_TYPES["self_study"]["id"]:
                    sem_dict[ACTIVITY_TYPES["self_work"]["code"]] = str(activity.amount // 100)
                elif activity.id_type_control == CONTROL_TYPES["lab"]["id"]:
                    sem_dict[ACTIVITY_TYPES["lab"]["code"]] = str(activity.amount // 100)
                elif activity.id_type_control == CONTROL_TYPES["test"]["id"]:
                    sem_dict["Зач"] = "1"
                elif activity.id_type_control == CONTROL_TYPES["diff_test"]["id"]:
                    sem_dict["ДифЗач"] = "1"
                elif activity.id_type_control == CONTROL_TYPES["course_project"]["id"]:
                    sem_dict["КП"] = "1"
            
            if sem_dict not in discipline_data["sem"]:
                discipline_data["sem"].append(sem_dict)

    if discipline_data:
        result["Строка"].append(discipline_data)

    return result

def create_xml(aup):
    """Создает XML-файл на основе данных учебного плана"""
    json_data = create_json(aup)
    xml_data = create_json_xml(aup)
    
    doc = et.Element("Документ")
    doc.set("Тип", "Академический учебный план")
    
    # Создание элемента План
    plan = et.SubElement(doc, "План")
    plan.set("ПодТип", "рабочий учебный план")
    plan.set("Шифр", "PLM")
    plan.set("ОбразовательнаяПрограмма", "подготовка бакалавриатов")
    plan.set("ФормаОбучения", EDUCATION_FORMS["full_time"])
    plan.set("УровеньОбразования", EDUCATION_LEVELS["bachelor"])
    
    # Создание элемента Титул
    titul = et.SubElement(doc, "Титул")
    titul.set("ИмяПлана", f"Академический учебный план {aup} от 01.11.{json_data['year']} 0:00:00")
    titul.set("ПолноеИмяПлана", f"Академический учебный план {aup} от 01.11.{json_data['year']} 0:00:00")
    titul.set("ИмяВуза", "Федеральное государственное автономное образовательное учреждение высшего образования «Московский политехнический университет»")
    titul.set("ИмяВуза2", json_data["header"][3])
    titul.set("Факультет", json_data["header"][3])
    titul.set("ПоследнийШифр", json_data["header"][0])
    titul.set("ГодНачалаПодготовки", str(json_data["year"]))
    titul.set("ВидПлана", "2")
    titul.set("КодУровня", "B")
    titul.set("СеместровНаКурсе", "2")
    titul.set("ЭлементовВНеделе", "6")
    titul.set("ТипГОСа", "3.5")
    titul.set("Приложение", "UpVpoGosInsp")
    titul.set("ВерсияПриложения", "22233")
    titul.set("DetailGIA", "1")
    
    # Дополнительные элементы
    et.SubElement(titul, "АтрибутыЦикловНов")
    et.SubElement(titul, "АтрибутыЦиклов")
    et.SubElement(titul, "Специальности")
    
    # Создание строк плана
    stroki_plan = et.SubElement(doc, "СтрокиПлана")
    
    for item in xml_data["Строка"]:
        line = et.SubElement(stroki_plan, "Строка")
        
        for key, value in item.items():
            if key != "sem":
                line.set(key, value)
            else:
                for semester in value:
                    sem_elem = et.SubElement(line, "Сем")
                    for activity_key, activity_value in semester.items():
                        sem_elem.set(activity_key, activity_value)
                        
                        # Добавление элементов VZ для видов занятий
                        if activity_key in [ACTIVITY_TYPES["lab"]["code"], 
                                         ACTIVITY_TYPES["lecture"]["code"], 
                                         "Пр", 
                                         ACTIVITY_TYPES["self_work"]["code"], 
                                         "Сем"]:
                            vz = et.SubElement(sem_elem, "VZ")
                            activity_type = next(
                                (a for a in ACTIVITY_TYPES.values() if a["code"] == activity_key), 
                                ACTIVITY_TYPES["self_work"]
                            )
                            vz.set("ID", str(activity_type["id"]))
                            vz.set("Н", activity_value)

    # Сохранение XML
    et.ElementTree(doc).write("sample.txt", encoding='UTF-8')
    return open("../../sample.txt", 'r')