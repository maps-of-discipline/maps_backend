import json
import operator


from auth import approved_required, login_required
from models import Users
from models.maps import D_ControlType, SprDiscipline, db, AupData, AupInfo, SprFaculty, Department
from models.cabinet import RPD, StudyGroups, Topics, Students, Grade, GradeTable, GradeType, GradeColumn, SprBells

from flask import Blueprint, make_response, jsonify, request, send_file, send_from_directory
from cabinet.utils.serialize import serialize
from cabinet.lib.generate_empty_rpd import generate_empty_rpd
import datetime
from dateutil.parser import parse
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
@login_required(request)
@approved_required(request)
def rpd():
    rpdList = RPD.query.all()
    rpdList = serialize(rpdList)
    return jsonify(rpdList)


# Получение тем занятий по номеру АУП и айди дисциплины
@cabinet.route('/lessons', methods=['GET'])
@login_required(request)
@approved_required(request)
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
@login_required(request)
@approved_required(request)
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
    # students = serialize(students)

    rows = []
    for student in students:
        student: Students
        grades = serialize(student.grades)

        values = {}
        for grade in grades:
            values[grade['grade_column_id']] = grade['value']

        rows.append({
            'id': student.id,
            'name': student.name,
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
@login_required(request)
@approved_required(request)
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
        if type(topic.date) is datetime.datetime:
            date = topic.date.strftime('%d.%m')

        bulk_grade_columns.append(GradeColumn(name=date, grade_table_id=grade_table.id, grade_type_id=grade_type_attendance.id, topic_id=topic.id))
        bulk_grade_columns.append(GradeColumn(name=topic.task_link_name, grade_table_id=grade_table.id, grade_type_id=grade_type_tasks.id, topic_id=topic.id))
        bulk_grade_columns.append(GradeColumn(name=date, grade_table_id=grade_table.id, grade_type_id=grade_type_activity.id, topic_id=topic.id))
 
    db.session.bulk_save_objects(bulk_grade_columns)

    db.session.commit()

    return jsonify(serialize(grade_table))


@cabinet.route('get-types-grade')
@login_required(request)
@approved_required(request)
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
@login_required(request)
@approved_required(request)
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
@login_required(request)
@approved_required(request)
def createGradeType():
    data = request.get_json()

    grade_type = GradeType(name=data['name'], grade_table_id=data['table_id'], type="custom")
    db.session.add(grade_type)
    db.session.commit()

    return jsonify(serialize(grade_type))


@cabinet.route('updateGrade', methods=['POST'])
@login_required(request)
@approved_required(request)
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
@login_required(request)
@approved_required(request)
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
@login_required(request)
@approved_required(request)
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
    topic.date_task_finish_include = data['lesson']['date_task_finish_include']
    topic.spr_bells_id = data['lesson']['spr_bells_id']

    if data['lesson']['date'] == None:
        topic.date = None
    else:
        topic.date = parse(data['lesson']['date']).astimezone(datetime.timezone(datetime.timedelta(hours=3)))
        """ date_obj = datetime.datetime.strptime(data['lesson']['date'], r'%Y-%m-%dT%H:%M:%S.%f%z')
        topic.date = date_obj.astimezone(datetime.timezone(datetime.timedelta(hours=3))) """


    if data['lesson']['date_task_finish'] == None:
        topic.date_task_finish = None
    else:
        topic.date_task_finish = parse(data['lesson']['date_task_finish']).astimezone(datetime.timezone(datetime.timedelta(hours=3)))
        """ date_obj = datetime.datetime.strptime(data['lesson']['date_task_finish'], r'%Y-%m-%dT%H:%M:%S.%f%z')
        topic.date_task_finish = date_obj.astimezone(datetime.timezone(datetime.timedelta(hours=3))) """

    topic.lesson_order = data['lesson']['lesson_order']

    db.session.add(topic)
    db.session.commit()

    res = serialize(topic)

    return make_response(jsonify(res))


@cabinet.route('/create-lesson', methods=['POST'])
@login_required(request)
@approved_required(request)
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
@login_required(request)
@approved_required(request)
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
@login_required(request)
@approved_required(request)
def controlTypesRPD():
    id_rpd = request.args.get('rpd')

    rpd = RPD.query.filter(RPD.id == id_rpd).first()

    id_unique_discipline = rpd.id_unique_discipline
    id_aup = rpd.id_aup

    diciplines = AupData.query.filter(AupData.id_aup == id_aup, AupData.id_discipline == id_unique_discipline).all()
    serialized_diciplines = [discipline.to_dict() for discipline in diciplines]

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

@cabinet.route('get-lk-users', methods=['GET'])
@login_required(request)
@approved_required(request)
def getLKUsers():
    users = Users.query.filter_by(auth_type='lk').all()

    res = []
    for user in users:
        roles = []
        for role in user.roles:
            roles.append({
                "id_role": role.id_role,
                "name_role": role.name_role
            })

        res.append({
            'id_user': user.id_user,
            'name': user.name,
            'approved_lk': user.approved_lk,
            'request_approve_date': user.request_approve_date,
            'roles': roles,
        })

    return jsonify(res)


@cabinet.route('update-approve-user', methods=['POST'])
@login_required(request)
@approved_required(request)
def updateApproveUser():
    data = request.get_json()

    user: Users = Users.query.filter_by(id_user=data['id_user']).first()
    user.approved_lk = data['value']

    db.session.commit()

    return jsonify(True)

@cabinet.route('getUser', methods=['POST'])
@login_required(request)
@approved_required(request)
def getUser():
    data = request.get_json()

    if not data['token']:
        return make_response('Отсутствует "token"', 400)

    payload = {'getUser': '', 'token': data['token']}

    from app import app
    res = requests.get(app.config.get('LK_URL'), params=payload)

    return jsonify(res.json())


@cabinet.route('aup', methods=['GET'])
@login_required(request)
@approved_required(request)
def getAup():
    search = request.args.get('search')

    found = AupInfo.query.filter(AupInfo.file.like("%" + search + "%")).all()

    res = serialize(found)

    return jsonify(res)


@cabinet.route('disciplines', methods=['GET'])
@login_required(request)
@approved_required(request)
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
@login_required(request)
@approved_required(request)
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
@login_required(request)
@approved_required(request)
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
@login_required(request)
@approved_required(request)
def getGroups():
    groups = StudyGroups.query.all()

    res = serialize(groups)

    return jsonify(res)


@cabinet.route('getReportByDiscipline', methods=['GET'])
@login_required(request)
@approved_required(request)
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
@cabinet.route('download-tutor-order', methods=['POST'])
@login_required(request)
@approved_required(request)
def downloadTutorOrder():
    body = request.get_json()


    template = {
        "date": "01.09.2023",
        "order": "10-Р",
        "year": "2023/2024",
        "faculty": "факультет информационных технологий",
        "form_education": "очная",
        "body": body,
        "need_report": "раз в месяц",
        "need_report_day": "первый понедельник",
        "provide_person": {
            "jobtitle": "заместитель декана по общим вопросам",
            "name": "В.М. Черновой"
        },
        "signer": {
            "name": "Д.Г. Демидов"
        },
        "executor": "Олейникова Е.В., тел: 1704"
    }

    docx = DocxTemplate('static/docx_templates/tutor_template.docx')


    docx.render(template)
    docx.save('static/docx_templates/tutor_template_res.docx')

    return send_from_directory('static/docx_templates', 'tutor_template_res.docx', as_attachment=True)

# Тьюторы
@cabinet.route('get-faculties', methods=['GET'])
@login_required(request)
@approved_required(request)
def getFaculties():
    faculties = SprFaculty.query.all()
    return jsonify(serialize(faculties))

@cabinet.route('get-departments', methods=['GET'])
@login_required(request)
@approved_required(request)
def getDepartments():
    departments = Department.query.all()
    return jsonify(serialize(departments))

@cabinet.route('get-bells', methods=['GET'])
@login_required(request)
@approved_required(request)
def getBells():
    bells = SprBells.query.all()
    return jsonify(serialize(bells))

@cabinet.route('update-bells', methods=['POST'])
@login_required(request)
@approved_required(request)
def updateBells():
    data = request.get_json()

    db.session.bulk_update_mappings(SprBells, data)
    db.session.commit()

    return jsonify('ok')

@cabinet.route('get-staff', methods=['GET'])
@login_required(request)
@approved_required(request)
def getStaff():
    division = request.args.get('division')

    from app import app
    payload = {
        'getStaff': '',
        'division': division,
        'token': app.config.get('LK_TOKEN')
    }

    res = requests.get(app.config.get('LK_URL'), params=payload)
    data = res.json()
    staff = data['items']

    return jsonify(staff)

@cabinet.route('get-report', methods=['GET'])
@login_required(request)
@approved_required(request)
def getReportByGroup():
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
    grades = Grade.query.filter_by(grade_table_id=grade_table.id).all()

    grades = serialize(grades)

    grouped_grades_by_students = groupby(sorted(grades, key=lambda x: x['student_id']), key=lambda x: x['student_id'])
    # grouped_grades_by_column = groupby(grouped_grades_by_students, key=lambda x: x['grade_column_id'])

    example = [        
        {
            'name': 'Шеховцов Всеволод Антонович',
            'categories': [
                {
                    'name': 'Посещение',
                    'value': 44,
                },
                {
                    'name': 'Активность',
                    'value': 53,
                },
                {
                    'name': 'Задания',
                    'value': 12,
                },
            ],
	    }
    ]

    result = {}

    def get_sum_cols(cols):
        res = {
            'value': 0
        }
        
        for col in cols:
            if 'name' not in res:
                res['name'] = col['grade_column']['grade_type']['name']

            if 'grade_type_id' not in res:
                res['grade_type_id'] = col['grade_column']['grade_type']['id']

            if isinstance(col['value'], int):
                res['value'] = res['value'] + col['value']

        return res

    for key, grades_student in grouped_grades_by_students:
        grouped_by_grade_type = groupby(sorted(grades_student, key=lambda x: x['grade_column']['grade_type_id']), key=lambda x: x['grade_column']['grade_type_id'])

        if key not in result:
            result[key] = dict()

        result[key]['categories'] = {}
        for grade_type in grade_types:
            result[key]['categories'][grade_type.id] = {
                'grade_type_id': grade_type.id,
                'name': grade_type.name,
                'value': 0,
            }

        for key_cols, cols in grouped_by_grade_type:
            if 'categories' not in result[key]:
                result[key]['categories'] = dict()

            list_cols = list(cols)

            if 'name' not in result[key]:
                result[key]['name'] = list_cols[0]['student']['name']

            grade_type_id = list_cols[0]['grade_column']['grade_type_id']
            for col in list_cols:
                if isinstance(col['value'], int):
                    result[key]['categories'][grade_type_id]['value'] = result[key]['categories'][grade_type_id]['value'] + col['value']

    print()

    return jsonify({
        'rating_chart': result,
    })