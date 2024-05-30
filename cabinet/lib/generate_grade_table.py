
from flask import jsonify
import datetime

from maps.models import db, AupInfo
from cabinet.models import RPD, StudyGroups, Topics, GradeTable, GradeType, GradeColumn

def generate_grade_table(num_aup, id_discipline, group_num, semester):
    aup_info: AupInfo = AupInfo.query.filter(AupInfo.num_aup == num_aup).first()
    group = StudyGroups.query.filter(StudyGroups.title == group_num).first()

    grade_table = GradeTable(id_aup=aup_info.id_aup, id_unique_discipline=id_discipline, study_group_id=group.id, semester=semester)

    db.session.add(grade_table)

    db.session.commit()

    grade_type_attendance = GradeType(name='Посещение', type='attendance', grade_table_id=grade_table.id)
    grade_type_tasks = GradeType(name='Задания', type='tasks', grade_table_id=grade_table.id)
    grade_type_activity = GradeType(name='Активность', type='activity', grade_table_id=grade_table.id)

    db.session.add(grade_type_attendance)   
    db.session.add(grade_type_tasks)   
    db.session.add(grade_type_activity)   


    rpd = RPD.query.filter(RPD.id_aup == aup_info.id_aup, RPD.id_unique_discipline == id_discipline).first()
    topics = Topics.query.filter(Topics.id_rpd == rpd.id, Topics.semester == semester, Topics.study_group_id == group.id).all()

    bulk_grade_columns= []
    for topic in topics:
        date = None
        if type(topic.date) is datetime.datetime:
            date = topic.date.strftime('%d.%m')

        bulk_grade_columns.append(GradeColumn(name=date, grade_table_id=grade_table.id, grade_type_id=grade_type_attendance.id, topic_id=topic.id))
        bulk_grade_columns.append(GradeColumn(name=topic.task_link_name, grade_table_id=grade_table.id, grade_type_id=grade_type_tasks.id, topic_id=topic.id))
        bulk_grade_columns.append(GradeColumn(name=date, grade_table_id=grade_table.id, grade_type_id=grade_type_activity.id, topic_id=topic.id))
 
    db.session.bulk_save_objects(bulk_grade_columns)

    db.session.commit()

    return jsonify(grade_table)