from models.maps import db, AupData, AupInfo
from models.cabinet import RPD, Topics
from flask import Blueprint, make_response, jsonify, request
from cabinet.utils.serialize import serialize

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

# Получение всех тем по РПД
# TODO Обработать ошибки и ненаход данных
@cabinet.route('/lessons/<string:aupCode>', methods=['GET'])
def topics(aupCode):
    # Добавить сюда поиск по id_unique_dicipline, т.к.
    # сейчас возвращаются все темы по всем дисциплинам
    aup: AupInfo = AupInfo.query.filter(AupInfo.num_aup == aupCode).first()

    if not aup:
        return jsonify([])

    rpd: RPD = RPD.query.filter(RPD.id_aup == aup.id_aup).first()

    topics: Topics = Topics.query.filter(Topics.id_rpd == rpd.id).all()
    topics = serialize(topics)

    return jsonify(topics)

@cabinet.route('/save-topic', methods=['POST'])
def saveTopic():
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
