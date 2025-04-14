from flask import Blueprint, jsonify, Response, request
from rups.logic.general import get_data_for_rups

rups = Blueprint("rups", __name__, url_prefix="/api", static_folder="static")

@rups.route("/get-rups-for-two-aups", methods=["GET"]) 
def get_aup_for_rups() -> Response:
    aup1 = request.args.get("aup1")
    aup2 = request.args.get("aup2")
    tr = request.args.get("tr", None)
    sem_num = request.args.get("sem_num", default=1, type=int)
    
    if not aup1 or not aup2:
        return jsonify({
            "error": "Missing required parameters",
            "message": "Both aup1 and aup2 parameters are required"
        }), 400
    
    try:
        data = get_data_for_rups(aup1, aup2, sem_num)
        return jsonify(data)
    except Exception as e:
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500
