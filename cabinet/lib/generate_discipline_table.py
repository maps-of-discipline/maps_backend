from flask import jsonify
from maps.models import db, AupInfo, AupData, SprDiscipline
from cabinet.models import DisciplineTable, StudyGroups, GradeType, Topics
from cabinet.utils.serialize import serialize

def bulk_insert_unique(session, existing, need_add, unique_fields):
    existing_tuple = {
        tuple(getattr(x, field) for field in unique_fields)
        for x in existing
    }
    
    unique_data = [
        item for item in need_add 
        if tuple(getattr(item, field) for field in unique_fields) not in existing_tuple
    ]
    
    if unique_data:
        session.bulk_save_objects(unique_data)
        session.commit()

# Создает РПД для дисциплины в АУП, а также генерирует
# пустые строки тем занятий
def generate_discipline_table(num_aup, id_discipline, group_num, semester, row_count):
    aup: AupInfo = AupInfo.query.filter(AupInfo.num_aup == num_aup).first()
    group = StudyGroups.query.filter(StudyGroups.title == group_num).first()

    discipline_table = DisciplineTable(id_aup=aup.id_aup, id_unique_discipline=id_discipline, study_group_id=group.id, semester=semester)
    
    db.session.add(discipline_table)
    db.session.commit()

    discipline_table = DisciplineTable.query.filter_by(id_aup=aup.id_aup, id_unique_discipline=id_discipline, study_group_id=group.id, semester=semester).first()

    need_add_grade_types = []

    need_add_grade_types.append(GradeType(name='Посещение', type='attendance', discipline_table_id=discipline_table.id))
    need_add_grade_types.append(GradeType(name='Задания', type='tasks', discipline_table_id=discipline_table.id))
    need_add_grade_types.append(GradeType(name='Активность', type='activity', discipline_table_id=discipline_table.id))

    db.session.bulk_save_objects(need_add_grade_types)
    db.session.commit()

    empty_topics = []

    print('empty_topics', empty_topics)
    print('row_count', row_count)
    for i in range(row_count):
        empty_topics.append(Topics(
            topic='',
            chapter='',
            id_type_control=None,
            task_link='',
            task_link_name='',
            completed_task_link='',
            completed_task_link_name='',
            discipline_table_id=discipline_table.id,
            study_group_id=group.id,
            spr_place_id = None,
            place_note = '',
            note = '',
        ))
    
    db.session.bulk_save_objects(empty_topics)
    db.session.commit()

    return {
        'data': discipline_table
    }