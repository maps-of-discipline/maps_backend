from models.maps import D_ControlType, SprDiscipline, db, AupData, AupInfo
from models.cabinet import RPD, StudyGroups, Topics
from flask import Blueprint, make_response, jsonify, request
from cabinet.utils.serialize import serialize
from cabinet.lib.generate_empty_rpd import generate_empty_rpd

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

    groups = StudyGroups.query.filter(StudyGroups.id_aup == aup_info.id_aup).all()
    response_data['groups'] = serialize(groups)

    return jsonify(response_data)


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


