from maps.models import db, AupInfo, SprDiscipline
from cabinet.models import DisciplineTable


# Создает РПД для дисциплины в АУП, а также генерирует
# пустые строки тем занятий
def generate_discipline_table(id_aup, id_discipline, group_id, semester):
    discipline_table: DisciplineTable = DisciplineTable.query.filter_by(id_aup=id_aup, id_unique_discipline=id_discipline, study_group_id=group_id).first()
    
    if discipline_table:
        return { 'error': 'discipline_table exist' }
    
    aup: AupInfo = AupInfo.query.filter(AupInfo.id_aup == id_aup).first()
    if not aup:
        return { 'error': 'aup not exist' }
    
    spr_discipline: SprDiscipline = SprDiscipline.query.filter(SprDiscipline.id == id_discipline).first()
    if not spr_discipline:
        return { 'error': 'discipline not exist' }
    
    new_discipline_table = DisciplineTable(id_aup=aup.id_aup, id_unique_discipline=id_discipline, study_group_id=group_id, semester=semester)

    db.session.add(new_discipline_table)   
    db.session.commit()

    return {
        'data': new_discipline_table
    }