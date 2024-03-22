from models.maps import SprDiscipline, db, AupData, AupInfo
from models.cabinet import RPD, Topics
from flask import Blueprint, make_response, jsonify, request
from cabinet.utils.serialize import serialize
from cabinet.lib.generate_empty_rpd import generate_empty_rpd

from take_from_bd import (control_type_r)

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
        return jsonify({ 'error': 'Данный АУП отсутствует.' })
    
    discipline_is_exist = AupData.query.filter(AupData.id_discipline == id_discipline).first()
    if not discipline_is_exist:
        return jsonify({ 'error': 'Дисциплина отсутствует в АУП.' })

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

@cabinet.route('/save-topic', methods=['POST'])
def save_topic():
    data = request.get_json()
    print(data)

    if 'id' not in data:
        return make_response('Отсутствует поле "id"', 401)
    
    if 'lesson' not in data:
        return make_response('Отсутствует поле "lesson"', 401)
    
    topic = Topics.query.filter(Topics.id == data['id']).first()

    topic.chapter = data['lesson']['chapter']
    topic.topic = data['lesson']['topic']

    db.session.add(topic)
    db.session.commit()

    res = serialize(topic)

    return make_response(jsonify(res))

# Получение всех нагрузок дисциплины
@cabinet.route('/control_types/<string:id_rpd>', methods=['GET'])
def controlTypesRPD(id_rpd):
    rpd = RPD.query.filter(RPD.id == id_rpd).first()

    id_unique_discipline = rpd.id_unique_discipline
    id_aup = rpd.id_aup

    diciplines = AupData.query.filter(AupData.id_aup == id_aup, AupData.id_unique_discipline == id_unique_discipline).all()
    diciplines = serialize(diciplines)
    
    # Преобразует все строки из выгрузки в список нагрузок на дисциплине
    def mapDisciplinesToControlType(dicipline):
        id = dicipline['id_type_control']

        return {
            'id_type_control': id,
            'name': control_type_r[id],
            'id_edizm': dicipline['id_edizm'],
            'amount': dicipline['amount'] / 100,
        }
    
    controlTypes = list(map(mapDisciplinesToControlType, diciplines))

    return jsonify(controlTypes)
