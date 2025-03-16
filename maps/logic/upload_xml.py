import io
import xml.etree.ElementTree as et
from maps.models import AupData, AupInfo, Weeks, NameOP, SprDegreeEducation, SprFormEducation

def create_xml(aup):
    aupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    if not aupInfo:
        return None 
    
    aupData = AupData.query.filter_by(id_aup=aupInfo.id_aup).order_by(
        AupData.shifr, AupData.id_discipline, AupData.id_period, AupData.id_type_control).all()
    weeks_data = Weeks.query.filter_by(aup_id=aupInfo.id_aup).all()
    spec_data = NameOP.query.get(aupInfo.id_spec) if aupInfo.id_spec else None
    degree_data = SprDegreeEducation.query.get(aupInfo.id_degree)
    form_data = SprFormEducation.query.get(aupInfo.id_form)
    
    doc = et.Element("Документ", Тип="Академический учебный план")
    
    plan = et.SubElement(doc, "План", ПодТип="рабочий учебный план", Шифр="PLM",
                         ОбразовательнаяПрограмма=aupInfo.qualification, 
                         УровеньОбразования="ВПО", 
                         ФормаОбучения=form_data.form if form_data else "")
    
    # Секция Титул
    titul = et.SubElement(plan, "Титул",
        DetailGIA="1",
        ВерсияПриложения="22233",
        ВидПлана="2",
        ГодНачалаПодготовки=str(aupInfo.year_beg),
        ИмяВуза="Федеральное государственное автономное образовательное учреждение высшего образования «Московский политехнический университет»",
        ИмяВуза2=aupInfo.faculty.name_faculty,
        ИмяПлана=f"Академический учебный план {aup}",
        КодУровня="B",
        ПолноеИмяПлана=f"Академический учебный план {aup}",
        ПоследнийШифр=spec_data.program_code if spec_data else "",
        Факультет=aupInfo.faculty.name_faculty,
        СеместровНаКурсе="2",
        ТипГОСа="3.5",
        ЭлементовВНеделе="6"
    )
    
    # Атрибуты циклов
    atr_iz = et.SubElement(titul, "АтрибутыЦикловНов")
    cycles = [
        ("1", "Б1", "Дисциплины (модули)"),
        ("4", "", "Элективные курсы по физической культуре"),
        ("5", "Б2", "Практики"),
        ("6", "ФТД", "Факультативы"),
        ("7", "Б3", "Государственная итоговая аттестация")
    ]
    
    for num, abbrev, name in cycles:
        et.SubElement(atr_iz, "Цикл", 
            Ном=num,
            Аббревиатура=abbrev,
            Название=name
        )
    
    # Специальности
    spec_section = et.SubElement(titul, "Специальности")
    if spec_data:
        et.SubElement(spec_section, "Специальность",
            Название=f"Направление подготовки: {spec_data.program_code} {spec_data.name_spec}",
            Ном="1"
        )
    
    # Квалификации
    kval_section = et.SubElement(titul, "Квалификации")
    et.SubElement(kval_section, "Квалификация",
        Название=degree_data.name_deg,
        Ном="1",
        СрокОбучения=f"{aupInfo.years}г"
    )
    
    graph = et.SubElement(titul, "ГрафикУчПроцесса")
    for year in range(1, aupInfo.years+1):
        kurs = et.SubElement(graph, "Курс", Ном=str(year))
        
        # Добавляем семестры на основе периодов
        periods = {week.period_id for week in weeks_data}
        for period_id in sorted(periods):
            sem = et.SubElement(kurs, "Семестр",
                Ном=str(period_id),
                НомерПервойНедели="1"  # Нужно уточнить логику расчета
            )
    
    stroki_plan = et.SubElement(plan, "СтрокиПлана")
    for item in aupData:
        discipline = item.discipline.title if item.discipline else item._discipline
        line = et.SubElement(stroki_plan, "Строка",
            Дис=discipline,
            ИдентификаторДисциплины=str(item.id_discipline) if item.id_discipline else "",
            НовЦикл=item.type_record.title,
            Цикл=item.type_record.title
        )
        sem_element = et.SubElement(line, "Сем", Ном=str(item.id_period))
        
        type_map = {1: "Лек", 2: "Пр", 4: "СРС", 5: "Зач", 6: "Лаб", 9: "КП", 18: "ДифЗач"}
        if item.id_type_control in type_map:
            sem_element.set(type_map[item.id_type_control], str(item.amount))
        
        vz = et.SubElement(sem_element, "VZ",
            H=str(item.amount),
            ID=str(item.id_type_control)
        )
    
    xml_buffer = io.BytesIO()
    tree = et.ElementTree(doc)
    tree.write(xml_buffer, encoding='UTF-8', xml_declaration=True)
    xml_buffer.seek(0)
    
    return xml_buffer
