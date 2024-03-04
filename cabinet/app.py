from flask import Blueprint, make_response, jsonify
from models import RPD, Topics, AupData
from cabinet.utils.serialize import serialize

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
@cabinet.route('/topics/<string:id_rpd>', methods=['GET'])
def topics(id_rpd):
    topics = Topics.query.filter(Topics.id_rpd == id_rpd).all()
    topics = serialize(topics)

    return jsonify(topics)

# Получение всех нагрузок (дисциплин*) по РПД
@cabinet.route('/control_types/<string:id_rpd>', methods=['GET'])
def controlTypesRPD(id_rpd):
    rpd = RPD.query.filter(RPD.id == id_rpd).first()

    id_unique_discipline = rpd.id_unique_discipline
    id_aup = rpd.id_aup

    diciplines = AupData.query.filter(AupData.id_aup == id_aup, AupData.id_unique_discipline == id_unique_discipline).all()
    diciplines = serialize(diciplines)

    return jsonify(diciplines)