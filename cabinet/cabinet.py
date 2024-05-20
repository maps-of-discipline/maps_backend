import json


from models.maps import D_ControlType, SprDiscipline, db, AupData, AupInfo
from models.cabinet import RPD, StudyGroups, Topics, Students, Grade, GradeTable, GradeType, GradeColumn
from flask import Blueprint, make_response, jsonify, request
from cabinet.utils.serialize import serialize
from cabinet.lib.generate_empty_rpd import generate_empty_rpd
from datetime import datetime
from docxtpl import DocxTemplate

from openpyxl import load_workbook
import os

# regexp
import re

from take_from_bd import (control_type_r)
import requests

from itertools import groupby

cabinet = Blueprint('cabinet', __name__)


@cabinet.route('/ping')
def test():
    return make_response('pong', 200)


# Получение списка РПД
@cabinet.route('/rpd', methods=['GET'])
def rpd():
    rpdList = RPD.query.all()
    rpdList = serialize(rpdList)
    return jsonify(rpdList)


# Получение тем занятий по номеру АУП и айди дисциплины
@cabinet.route('/lessons', methods=['GET'])
def getLessons():
    if 'aup' not in request.args:
        return make_response('Отсутствует параметр "aup"', 400)

    if 'id' not in request.args:
        return make_response('Отсутствует параметр "id"', 400)

    num_aup = request.args.get('aup')
    id_discipline = request.args.get('id')

    response_data = {
        'topics': [],
        'rpd_id': None,
        'title': None
    }

    aup_info: AupInfo = AupInfo.query.filter(AupInfo.num_aup == num_aup).first()
    if not aup_info:
        return jsonify({'error': 'Данный АУП отсутствует.'})

    discipline_is_exist = AupData.query.filter(AupData.id_discipline == id_discipline).first()
    if not discipline_is_exist:
        return jsonify({'error': 'Дисциплина отсутствует в АУП.'})

    rpd = RPD.query.filter(RPD.id_aup == aup_info.id_aup, RPD.id_unique_discipline == id_discipline).first()
    if not rpd:
        res = generate_empty_rpd(aup_info.id_aup, id_discipline)

        if 'error' in res:
            return jsonify(res)
        else:
            rpd = res['data']

    response_data['rpd_id'] = rpd.id

    spr_discipline = SprDiscipline.query.filter(SprDiscipline.id == id_discipline).first()
    response_data['title'] = spr_discipline.title

    topics: Topics = Topics.query.filter(Topics.id_rpd == rpd.id).all()
    response_data['topics'] = serialize(topics)

    groups = StudyGroups.query.filter(StudyGroups.num_aup == num_aup).all()
    response_data['groups'] = serialize(groups)

    return jsonify(response_data)


# Метод для обновления списка студентов по группе в базе данных
def bulkInsertStudentsByGroup(group):
    from app import app
    payload = {
        'getStudents': '',
        'group': group,
        'token': app.config.get('LK_TOKEN')
    }
    print(app.config.get('LK_TOKEN'))

    res = requests.get(app.config.get('LK_URL'), params=payload)
    data = res.json()
    data_students = data['items']

    bulk_students = []

    group_obj = StudyGroups.query.filter_by(title=group).first()

    group_obj_s = serialize(group_obj)

    for student in data_students:
        lk_id = student['id']
        is_exist = bool(Students.query.filter_by(lk_id=lk_id).first())

        if not is_exist:
            bulk_students.append(Students(name=student['fio'], study_group_id=group_obj_s['id'], lk_id=lk_id))

    db.session.bulk_save_objects(bulk_students)
    db.session.commit()

    return bulk_students


@cabinet.route('get-grades', methods=['GET'])
def getGrades():
    if 'aup' not in request.args:
        return make_response('Отсутствует параметр "aup"', 400)

    if 'id' not in request.args:
        return make_response('Отсутствует параметр "id"', 400)

    if 'group' not in request.args:
        return make_response('Отсутствует параметр "group"', 400)
    
    if 'semester' not in request.args:
        return make_response('Отсутствует параметр "semester"', 400)

    num_aup = request.args.get('aup')
    id_discipline = request.args.get('id')
    group_num = request.args.get('group')
    semester = request.args.get('semester')

    aup_info: AupInfo = AupInfo.query.filter(AupInfo.num_aup == num_aup).first()
    if not aup_info:
        return jsonify({'error': 'Данный АУП отсутствует.'})

    discipline_is_exist = AupData.query.filter(AupData.id_discipline == id_discipline).first()
    if not discipline_is_exist:
        return jsonify({'error': 'Дисциплина отсутствует в АУП.'})

    group = StudyGroups.query.filter(StudyGroups.title == group_num).first()
    if not group:
        return jsonify({'error': 'Данная группа отсутствует.'})


    grade_table = GradeTable.query.filter_by(id_aup=aup_info.id_aup, id_unique_discipline=id_discipline, study_group_id=group.id, semester=semester).first()

    if not grade_table:
        return jsonify({
            'is_not_exist': True,
            'message': 'Таблица успеваемости отсутствует'
        })

    grade_types = GradeType.query.filter_by(grade_table_id=grade_table.id).all()

    """ for group in groups:
        bulkInsertStudentsByGroup(group.title) """

    students = Students.query.filter(Students.study_group_id == group.id).all()
    students = serialize(students)

    rows = []
    for student in students:
        grades = Grade.query.filter(Grade.student_id == student['id'], Grade.grade_table_id == grade_table.id).all()
        grades = serialize(grades)

        values = {}
        for grade in grades:
            values[grade['grade_column_id']] = grade['value']

        rows.append({
            'id': student['id'],
            'name': student['name'],
            'values': values
        })

    columns = GradeColumn.query.filter_by(grade_table_id=grade_table.id).all()

    return jsonify({
        'gradeTypes': serialize(grade_types),
        'gradeTableId': grade_table.id,
        'columns': serialize(columns),
        'rows': rows
    })


@cabinet.route('create-grade-table')
def createGrades():
    num_aup = request.args.get('aup')
    id_discipline = request.args.get('id')
    group_num = request.args.get('group')
    semester = request.args.get('semester')

    aup_info: AupInfo = AupInfo.query.filter(AupInfo.num_aup == num_aup).first()
    if not aup_info:
        return jsonify({'error': 'Данный АУП отсутствует.'})

    group = StudyGroups.query.filter(StudyGroups.title == group_num).first()
    if not group:
        return jsonify({'error': 'Данная группа отсутствует.'})


    grade_table = GradeTable(id_aup = aup_info.id_aup, id_unique_discipline = id_discipline, study_group_id=group.id, semester=semester)

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
        if type(topic.date) is datetime:
            date = topic.date.strftime('%d.%m')

        bulk_grade_columns.append(GradeColumn(name=date, grade_table_id=grade_table.id, grade_type_id=grade_type_attendance.id, topic_id=topic.id))
        bulk_grade_columns.append(GradeColumn(name=topic.task_link_name, grade_table_id=grade_table.id, grade_type_id=grade_type_tasks.id, topic_id=topic.id))
        bulk_grade_columns.append(GradeColumn(name=date, grade_table_id=grade_table.id, grade_type_id=grade_type_activity.id, topic_id=topic.id))
 
    db.session.bulk_save_objects(bulk_grade_columns)

    db.session.commit()

    return jsonify(serialize(grade_table))


@cabinet.route('get-types-grade')
def getTypesGrade():
    num_aup = request.args.get('aup')
    id_discipline = request.args.get('id')
    group_num = request.args.get('group')

    aup_info: AupInfo = AupInfo.query.filter(AupInfo.num_aup == num_aup).first()
    if not aup_info:
        return jsonify({'error': 'Данный АУП отсутствует.'})

    group = StudyGroups.query.filter(StudyGroups.title == group_num).first()
    if not group:
        return jsonify({'error': 'Данная группа отсутствует.'})

    grade_table = GradeTable.query.filter_by(id_aup=aup_info.id_aup, id_unique_discipline=id_discipline,
                                             study_group_id=group.id).first()
    grade_types = GradeType.query.filter_by(grade_table_id=grade_table.id).all()

    return jsonify(serialize(grade_types))


@cabinet.route('update-grade-type', methods=['POST'])
def updateGradeType():
    data = request.get_json()

    grade_type = GradeType.query.filter_by(id=data['id']).first()

    grade_type.archived = data['archived']
    grade_type.name = data['name']
    grade_type.min_grade = data['min_grade']
    grade_type.max_grade = data['max_grade']    
    grade_type.binary = data['binary']
    grade_type.weight_grade = data['weight_grade']

    db.session.commit()

    res = serialize(grade_type)

    return jsonify(res)


@cabinet.route('create-grade-type', methods=['POST'])
def createGradeType():
    data = request.get_json()

    grade_type = GradeType(name=data['name'], grade_table_id=data['table_id'], type="custom")
    db.session.add(grade_type)
    db.session.commit()

    return jsonify(serialize(grade_type))


@cabinet.route('updateGrade', methods=['POST'])
def updateGrade():
    data = request.get_json()

    grade = Grade.query.filter_by(student_id=data['student_id'], grade_table_id=data['grade_table_id'],
                                  grade_column_id=data['grade_column_id']).first()

    if not grade:
        grade = Grade(value=data['value'], student_id=data['student_id'], grade_table_id=data['grade_table_id'],
                      grade_column_id=data['grade_column_id'])
        db.session.add(grade)
    else:
        grade.value = data['value']

    db.session.commit()

    res = serialize(grade)

    return jsonify(res)


# Роут для генерации несуществующей таблицы
@cabinet.route('/lessons', methods=['POST'])
def postLessons():
    if 'aup' not in request.args:
        return make_response('Отсутствует параметр "aup"', 401)

    if 'id' not in request.args:
        return make_response('Отсутствует параметр "id"', 401)

    aup = request.args.get('aup')
    id_discipline = request.args.get('id')

    success, data = generate_empty_rpd(aup, id_discipline)

    return jsonify({
        'success': success,
        'data': data
    })


@cabinet.route('/edit-lesson', methods=['POST'])
def edit_lesson():
    data = request.get_json()

    if 'lesson' not in data:
        return make_response('Отсутствует поле "lesson"', 401)

    topic = Topics.query.filter(Topics.id == data['lesson']['id']).first()

    topic.chapter = data['lesson']['chapter']
    topic.topic = data['lesson']['topic']
    topic.task_link = data['lesson']['task_link']
    topic.task_link_name = data['lesson']['task_link_name']
    topic.completed_task_link = data['lesson']['completed_task_link']
    topic.completed_task_link_name = data['lesson']['completed_task_link_name']
    topic.id_type_control = data['lesson']['id_type_control']

    if data['lesson']['date'] == None:
        topic.date = None
    else:
        topic.date = datetime.strptime(data['lesson']['date'], r'%d.%m.%Y')

    topic.lesson_order = data['lesson']['lesson_order']

    db.session.add(topic)
    db.session.commit()

    res = serialize(topic)

    return make_response(jsonify(res))


@cabinet.route('/create-lesson', methods=['POST'])
def create_lesson():
    data = request.get_json()

    if not data:
        return make_response('Отсутствует поле "lesson"', 400)

    new_lesson = Topics(
        topic=data['topic'],
        chapter=data['chapter'],
        id_type_control=data['id_type_control'],
        task_link=data['task_link'],
        task_link_name=data['task_link_name'],
        completed_task_link=data['completed_task_link'],
        completed_task_link_name=data['completed_task_link_name'],
        id_rpd=data['id_rpd'],
        semester=data['semester'],
        study_group_id=data['study_group_id'],
    )

    db.session.add(new_lesson)
    db.session.commit()

    res = serialize(new_lesson)
    return make_response(jsonify(res))


@cabinet.route('/delete-lesson', methods=['POST'])
def delete_lesson():
    data = request.get_json()

    if not data['id']:
        return make_response('Отсутствует "id"', 400)

    lesson = Topics.query.filter_by(id=data['id']).first()

    res = serialize(lesson)

    db.session.delete(lesson)
    db.session.commit()

    return make_response(jsonify(res), 200)


# Получение всех нагрузок дисциплины
@cabinet.route('/control_types', methods=['GET'])
def controlTypesRPD():
    id_rpd = request.args.get('rpd')

    rpd = RPD.query.filter(RPD.id == id_rpd).first()

    id_unique_discipline = rpd.id_unique_discipline
    id_aup = rpd.id_aup

    diciplines = AupData.query.filter(AupData.id_aup == id_aup, AupData.id_discipline == id_unique_discipline).all()
    serialized_diciplines = serialize(diciplines)

    control_types = {}
    control_type_q = D_ControlType.query.all()
    for row in control_type_q:
        control_types[row.id] = {
            'title': row.title,
            'shortname': row.shortname
        }

    # Преобразует все строки из выгрузки в список нагрузок на дисциплине
    def mapDisciplinesToControlType(dicipline):
        id = dicipline['id_type_control']

        return {
            'id_type_control': id,
            'name': control_types[id]['title'],
            'shortname': control_types[id]['shortname'],
            'id_edizm': dicipline['id_edizm'],
            'amount': dicipline['amount'] / 100,
            'id_period': dicipline['id_period']
        }

    control_types = list(map(mapDisciplinesToControlType, serialized_diciplines))

    grouped_control_types = groupby(sorted(control_types, key=lambda x: x['id_period']), key=lambda x: x['id_period'])

    result = {}
    for key, group in grouped_control_types:
        result[key] = list(group)

    return jsonify({
        'control_types': result
    })


@cabinet.route('/auth', methods=['POST'])
def auth():
    data = request.get_json()

    if not data['login']:
        return make_response('Отсутствует "login"', 400)

    if not data['password']:
        return make_response('Отсутствует "password"', 400)

    payload = {
        'ulogin': data['login'],
        'upassword': data['password'],
    }

    from app import app
    res = requests.post(app.config.get('LK_URL'), data=payload)

    if (res.status_code == 400):
        return make_response(jsonify({
            'error': True,
            'message': 'Неверный логин или пароль'
        }), 400)

    return jsonify(res.json())


@cabinet.route('getUser', methods=['POST'])
def getUser():
    data = request.get_json()

    if not data['token']:
        return make_response('Отсутствует "token"', 400)

    payload = {'getUser': '', 'token': data['token']}

    from app import app
    res = requests.get(app.config.get('LK_URL'), params=payload)

    return jsonify(res.json())


@cabinet.route('aup', methods=['GET'])
def getAup():
    search = request.args.get('search')

    found = AupInfo.query.filter(AupInfo.file.like("%" + search + "%")).all()

    res = serialize(found)

    return jsonify(res)


@cabinet.route('disciplines', methods=['GET'])
def disciplines():
    q_num_aup = request.args.get('aup')

    aup = AupInfo.query.filter(AupInfo.num_aup == q_num_aup).first()

    disciplines = AupData.query.filter(AupData.id_aup == aup.id_aup).all()
    disciplines = serialize(disciplines)

    unique_disciplines_map = {}

    for discipline in disciplines:
        if not discipline['unique_discipline']['id'] in unique_disciplines_map:
            unique_disciplines_map[discipline['unique_discipline']['id']] = discipline['unique_discipline']

    return jsonify(list(unique_disciplines_map.values()))


@cabinet.route('disciplines-new', methods=['GET'])
def disciplinesNew():
    num_aup = request.args.get('aup')

    aup_info = AupInfo.query.filter(AupInfo.num_aup == num_aup).first()
    aup_data = AupData.query.filter_by(id_aup=aup_info.id_aup).order_by(AupData.shifr, AupData._discipline,
                                                                        AupData.id_period).all()

    disciplines_items = {}
    flag = ""

    for i, item in enumerate(aup_data):
        if flag != item.discipline + str(item.id_period):
            flag = item.discipline + str(item.id_period)

            d = dict()

            d["id"] = item.id_discipline
            d["name"] = item.unique_discipline.title
            d["num_row"] = item.num_row
            d["color"] = '#5f60ec'

            if (item.id_period in disciplines_items):
                disciplines_items[item.id_period].append(d)
            else:
                disciplines_items[item.id_period] = [d]

    return jsonify(disciplines_items)


# Метод для загрузки файла выгрузки из 1С "Соответствие групп и учебных планов"
# и формирование на его основе таблицы в базе данных
@cabinet.route('uploadGroups', methods=['POST'])
def uploadGroups():
    files = request.files.getlist("file")
    file = files[0]

    from app import app

    path = os.path.join(app.static_folder, 'temp', file.filename)
    file.save(path)

    wb = load_workbook(file)
    sheet = wb.active

    study_groups = []

    for i in range(1, sheet.max_row + 1):
        group_cell = sheet.cell(row=i, column=2)
        aup_cell = sheet.cell(row=i, column=3)

        group_name = group_cell.value
        num_aup_regexp = re.search(r'\d{9}', aup_cell.value)

        if not num_aup_regexp == None:
            num_aup = num_aup_regexp[0]

            study_groups.append(StudyGroups(title=group_name, num_aup=num_aup))

    db.session.bulk_save_objects(study_groups)
    db.session.commit()

    res = serialize(study_groups)

    return jsonify(res)


# Метод для получения списка доступных групп
@cabinet.route('getGroups', methods=['GET'])
def getGroups():
    groups = StudyGroups.query.all()

    res = serialize(groups)

    return jsonify(res)


@cabinet.route('getReportByDiscipline', methods=['GET'])
def getReport():
    id_discipline = request.args.get('id_discipline')

    rpds: RPD = RPD.query.filter(RPD.id_unique_discipline == id_discipline).all()

    grades = {
        2: 0,
        3: 0,
        4: 0,
        5: 0,
    }

    for rpd in rpds:
        for topic in rpd.topics:
            for grade in topic.grades:
                grades[grade.value] += 1

    res = grades

    return jsonify(res)


from flask import current_app
@cabinet.route('get-word', methods=['POST'])
def getWord():
    data = request.get_json()
    docx = DocxTemplate('static/docx_templates/tutor_template.docx')
    print(current_app.static_folder)

    docx.render(data)
    docx.save('static/docx_templates/tutor_template_res.docx')

    return ''
