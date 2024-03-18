from models.maps import AupData, AupInfo
from models.cabinet import RPD, Topics
from flask import Blueprint, make_response, jsonify
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
    aup: AupInfo = AupInfo.query.filter(AupInfo.num_aup == aupCode).first()

    if not aup:
        return jsonify([])


    rpd: RPD = RPD.query.filter(RPD.id_aup == aup.id_aup).first()

    topics: Topics = Topics.query.filter(Topics.id_rpd == rpd.id).all()
    topics = serialize(topics)

    return jsonify(topics)

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
