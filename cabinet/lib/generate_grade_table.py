
from flask import jsonify
import datetime

from maps.models import db, AupInfo
from cabinet.models import RPD, StudyGroups, Topics, DisciplineTable, GradeType, GradeColumn

def generate_grade_table(discipline_table_id):
    discipline_table = DisciplineTable.query.filter_by(id=discipline_table_id).first()

    grade_types = list()

    grade_types.append(GradeType(name='Посещение', type='attendance', discipline_table_id=discipline_table.id))
    grade_types.append(GradeType(name='Задания', type='tasks', discipline_table_id=discipline_table.id))
    grade_types.append(GradeType(name='Активность', type='activity', discipline_table_id=discipline_table.id))

    db.session.bulk_save_objects(grade_types)

    """ topics = Topics.query.filter(Topics.id_rpd == rpd.id, Topics.semester == semester, Topics.study_group_id == group.id).all() """

    """ bulk_grade_columns= []
    for topic in topics:
        date = None
        if type(topic.date) is datetime.datetime:
            date = topic.date.strftime('%d.%m')

        bulk_grade_columns.append(GradeColumn(name=date, grade_table_id=grade_table.id, grade_type_id=grade_type_attendance.id, topic_id=topic.id))
        bulk_grade_columns.append(GradeColumn(name=topic.task_link_name, grade_table_id=grade_table.id, grade_type_id=grade_type_tasks.id, topic_id=topic.id))
        bulk_grade_columns.append(GradeColumn(name=date, grade_table_id=grade_table.id, grade_type_id=grade_type_activity.id, topic_id=topic.id))
 
    db.session.bulk_save_objects(bulk_grade_columns)
    db.session.commit() """

    return jsonify(grade_types)