from maps.models import db, AupInfo, SprDiscipline
from cabinet.models import RPD


# Создает РПД для дисциплины в АУП, а также генерирует
# пустые строки тем занятий
def generate_empty_rpd(id_aup, id_discipline):
    rpd: RPD = RPD.query.filter(RPD.id_aup == id_aup, RPD.id_unique_discipline == id_discipline).first()
    if rpd:
        return { 'error': 'Данный РПД уже существует в таблице.' }
    
    aup: AupInfo = AupInfo.query.filter(AupInfo.id_aup == id_aup).first()
    if not aup:
        return { 'error': 'Данный АУП отсутствует.' }
    
    spr_discipline: SprDiscipline = SprDiscipline.query.filter(SprDiscipline.id == id_discipline).first()
    if not spr_discipline:
        return { 'error': 'Данная дисциплина отсутствует.' }
    
    new_rpd = RPD(id_aup=aup.id_aup, id_unique_discipline=id_discipline)

    db.session.add(new_rpd)   
    db.session.commit()

    return {
        'data': new_rpd
    }