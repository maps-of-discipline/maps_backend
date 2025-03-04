import xml.etree.ElementTree as et
from maps.models import AupData, AupInfo

def create_json_xml(aup):
    aupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aupInfo:
        return None
    
    aupData = AupData.query.filter_by(id_aup=aupInfo.id_aup).order_by(
        AupData.shifr, AupData.id_discipline, AupData.id_period, AupData.id_type_control).all()
    
    json_data = {"aup": aupInfo.id_aup, "Строка": []}
    current_discipline = None
    discipline_data = None
    
    for item in aupData:
        if current_discipline != item.discipline:
            if discipline_data and discipline_data["sem"]:
                json_data["Строка"].append(discipline_data)
            discipline_data = {
                "Дис": item.discipline.title, 
                "НовЦикл": item.type_record.title,
                "Цикл": item.type_record.title,
                "ИдентификаторДисциплины": str(item.discipline.id), 
                "sem": []
            }
            current_discipline = item.discipline
        
        sem_data = next((sem for sem in discipline_data["sem"] if sem["Ном"] == item.id_period), None)
        if not sem_data:
            sem_data = {"Ном": item.id_period}
            discipline_data["sem"].append(sem_data)
        
        type_map = {1: "Экз", 2: "Лек", 4: "СРС", 6: "Лаб", 5: "Зач", 9: "ДифЗач", 18: "КП"}
        if item.id_type_control in type_map:
            sem_data[type_map[item.id_type_control]] = str(item.amount // 100)
    
    if discipline_data and discipline_data["sem"]:
        json_data["Строка"].append(discipline_data)
    
    return json_data

def create_xml(aup):
    dict_data = create_json_xml(aup)
    if not dict_data:
        return None 
    
    aupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    doc = et.Element("Документ", Тип="Академический учебный план")
    
    plan = et.SubElement(doc, "План", ПодТип="рабочий учебный план", Шифр="PLM", 
                         ОбразовательнаяПрограмма=aupInfo.qualification, 
                         ФормаОбучения=str(aupInfo.form.form), УровеньОбразования="ВПО")
    
    titul = et.SubElement(doc, "Титул", ИмяПлана=f"Академический учебный план {aup}", 
                          ПолноеИмяПлана=f"Академический учебный план {aup}",
                          ИмяВуза="Федеральное государственное автономное образовательное учреждение высшего образования",
                          ГодНачалаПодготовки=str(aupInfo.year_beg), ВидПлана="2")
    
    stroki_plan = et.SubElement(doc, "СтрокиПлана")
    for item in dict_data["Строка"]:
        line = et.SubElement(stroki_plan, "Строка", Дис=item["Дис"], НовЦикл=item["НовЦикл"], 
                              Цикл=item["Цикл"], ИдентификаторДисциплины=item["ИдентификаторДисциплины"])
        for sem in item["sem"]:
            sem_element = et.SubElement(line, "Сем", Ном=str(sem["Ном"]))
            for key, value in sem.items():
                if key != "Ном":
                    sem_element.set(key, value)
    
    save = et.ElementTree(doc)
    save.write("corrected.xml", encoding='UTF-8')
    return "corrected.xml"