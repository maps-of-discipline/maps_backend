from flask import Blueprint, jsonify, Response, request
from rups.logic.general import get_data_for_rups
from rups.logic.cosin_rups_v2 import compare_two_aups

rups = Blueprint("rups", __name__, static_folder="static", url_prefix="/rups")


@rups.route("/get-rups-for-two-aups", methods=["GET"])
def get_aup_for_rups():
    aup1 = request.args.get("aup1")
    aup2 = request.args.get("aup2")
    tr = request.args.get("tr", None)
    sem_num = request.args.get("sem_num", default=1, type=int)

    if not aup1 or not aup2:
        return jsonify(
            {
                "error": "Missing required parameters",
                "message": "Both aup1 and aup2 parameters are required",
            }
        ), 400

    try:
        data = get_data_for_rups(aup1, aup2, sem_num)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": "Internal server error", "message": str(e)}), 500


@rups.route("/get-rups-for-two-aups/v2", methods=["POST"])
def get_rups_for_aup_v2():
    data = request.get_json()
    aup1 = {
        "num": data["aup1"]["num"],
        "sem": int(data["aup1"]["sem"]),
    }

    aup2 = {
        "num": data["aup2"]["num"],
        "sem": int(data["aup2"]["sem"]),
    }

    res = compare_two_aups(aup1, aup2)
    return jsonify(res)
