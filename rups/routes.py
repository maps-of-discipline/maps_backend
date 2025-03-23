from flask import Blueprint, jsonify, Response, request


from rups.logic.general import get_data_for_rups


rups = Blueprint("rups", __name__, url_prefix="/api", static_folder="static")


@rups.route("/get-rups-for-two-aups", methods=["GET"])
def get_aup_for_rups() -> Response:
    data = get_data_for_rups(
        request.args["aup1"],
        request.args["aup2"],
        int(request.args["sem_num"]),
    )

    return jsonify(data)
