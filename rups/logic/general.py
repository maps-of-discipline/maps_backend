from sqlalchemy import select
from werkzeug.exceptions import NotFound
from maps.models import AupData, AupInfo, db
from rups.logic.cosin_rups import get_rups


def get_control_type(title: str) -> str:
    if title in ["Зачет", "Экзамен", "Курсовой проект", "Курсовая работа"]:
        return title
    else:
        return ""


def format_aup_info_for_rups(aup_num: str, sem_num: int) -> list[dict]:
    aup_data = db.session.scalars(
        select(AupData)
        .join(AupInfo)
        .where(AupInfo.num_aup == aup_num, AupData.id_period <= sem_num)
    )
    disciplines = {}
    for el in aup_data:
        el: AupData
        control_title = get_control_type(el.type_control.title)
        suffix = (
            "[КП]" if control_title in ["Курсовой проект", "Курсовая работа"] else ""
        )
        suffix += f"[{el.id_period}]"

        key = el.discipline.title + suffix
        if key not in disciplines:
            disciplines.update(
                {
                    key: {
                        "title": el.discipline.title,
                        "zet": el.amount
                        * (1 / 36 if el.ed_izmereniya.title == "Часы" else 1.5)
                        / 100,
                        "control": control_title,
                        "sem": el.id_period,
                    }
                }
            )
        else:
            disciplines[key]["zet"] += (
                el.amount * (1 / 36 if el.ed_izmereniya.title == "Часы" else 1.5) / 100
            )

    for key in disciplines.keys():
        disciplines[key]["zet"] = int(round(disciplines[key]["zet"], 0))

    return list(disciplines.values())


def get_data_for_rups(aup1: str, aup2: str, sem_num: int):
    formatted_aup1 = format_aup_info_for_rups(aup1, sem_num)
    formatted_aup2 = format_aup_info_for_rups(aup2, sem_num)
    df1, df2 = get_rups(formatted_aup1, formatted_aup2)

    return {
        "method1": df1.to_dict(orient="records"),
        "method2": df2.to_dict(orient="records"),
    }
