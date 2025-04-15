from pprint import pprint

from flask import Blueprint, jsonify

from unification.models import *

bp = Blueprint("unification", __name__)


@bp.route("/unification-config")
def unification():
    res = []
    for el in UnificationDiscipline.query.all():
        el: UnificationDiscipline
        periods = {}
        for period_assoc in el.periods:
            period_assoc: DisciplinePeriodAssoc
            faculties = []
            if el.is_faculties_different:
                faculties = [
                    {"id": fac.id_faculty, "title": fac.name_faculty}
                    for fac in period_assoc.faculties
                ]

            periods[period_assoc.period.id] = {
                "faculties": faculties,
                "load": [load.as_dict() for load in period_assoc.load],
            }

        unification = {
            "id": el.id,
            "discipline": el.discipline,
            "is_faculties_different": el.is_faculties_different,
            "semesters_count": el.semesters_count,
            "ugsn": el.ugsn,
            "degree": el.degree,
            "direction": el.direction,
            "amount": el.amount,
            "measure": {
                "id": el.measure.id,
                "title": el.measure.title,
            },
            "okso": [okso.program_code for okso in el.related_okso]
            if el.direction
            else [],
            "periods": periods,
        }

        res.append(unification)

    return jsonify(res)
