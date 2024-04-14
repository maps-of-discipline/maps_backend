from maps.models import AupInfo


def elective_disciplines(num_aup: str) -> dict:
    """
        Функция для получения факультативных дисциплин учебного плана с суммарным объемам по всем видам нагрузок
    """
    ELECTIVE_TYPE_ID = [13, 15, 16]

    aup_info: AupInfo = AupInfo.query.filter_by(num_aup=num_aup).first()

    elective_disciplines = {}
    for el in aup_info.aup_data:
        if el.id_type_record in ELECTIVE_TYPE_ID:
            try:
                elective_disciplines[el.discipline] += el.amount // 100
            except:
                elective_disciplines[el.discipline] = el.amount // 100

    return elective_disciplines
