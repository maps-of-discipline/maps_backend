from io import BytesIO

import xlsxwriter

from cabinet.models import Topics, SprPlace, SprBells
from maps.models import D_ControlType


def create_excel_lessons_report(topics: list[Topics]) -> BytesIO:
    in_memory_file = BytesIO()

    workbook = xlsxwriter.Workbook(in_memory_file)
    worksheet = workbook.add_worksheet()

    places = {place.id: place.prefix for place in SprPlace.query.all()}
    bells = {bell.id: bell.name for bell in SprBells.query.all()}
    type_controls = {type_.id: type_.shortname for type_ in D_ControlType.query.all()}

    worksheet.write_row(0, 0,
                        ['Место', 'Дата', 'Время', 'Вид', 'Глава', 'Тема', 'Загрузка', 'задания', 'Срок выполнения', 'Примечание', ])

    for i, topic in enumerate(topics, 1):
        worksheet.write(i, 0, places.get(topic.spr_place_id))

        worksheet.write(i, 1, str(topic.date or ""))

        worksheet.write(i, 2, bells.get(topic.spr_bells_id))
        worksheet.write(i, 3, type_controls.get(topic.id_type_control))
        worksheet.write(i, 4, topic.chapter)
        worksheet.write(i, 5, topic.topic)
        worksheet.write_url(i, 6, url=topic.task_link, string=topic.task_link_name)
        worksheet.write_url(i, 7, url=topic.completed_task_link, string=topic.completed_task_link_name)

        worksheet.write(i, 8, str(topic.date_task_finish or ""))

        worksheet.write(i, 9, topic.note)

    worksheet.autofit()
    workbook.close()

    return in_memory_file





