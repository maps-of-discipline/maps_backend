from flask import Blueprint, make_response, jsonify
from models import RPD, Topics

cabinet = Blueprint('cabinet', __name__)

@cabinet.route('/ping')
def test():
    return make_response('pong', 200)

# Получение списка РПД
@cabinet.route('/rpd', methods=['GET'])
def rpd():
    rpdList = RPD.query.all()
    return jsonify(rpdList)

@cabinet.route('/topics/<string:rpd_id>', methods=['GET'])
def topics(rpd_id):
    topics = Topics.query.filter(Topics.id_rpd == rpd_id).all()

    return jsonify(topics)

@cabinet.route('/control_types/<string:rpd_id>', methods=['GET'])
def controlTypesRPD():
    pass