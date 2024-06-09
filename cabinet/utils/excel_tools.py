from io import BytesIO
from itertools import cycle

import xlsxwriter
from xlsxwriter.utility import xl_col_to_name

from cabinet.models import Topics, SprPlace, SprBells, DisciplineTable, GradeColumn, StudyGroups, Students
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


def create_performance_report(discipline_table: DisciplineTable, study_group: StudyGroups):
    performance_types = [grade_type.name for grade_type in discipline_table.grade_types]
    performance_types.sort()
    type_colors = cycle(['#90b3e7', '#c895f8', '#7cbbb4', '#75cada', '#db8480'])
    value_begin_row_index = 3

    in_memory_file = BytesIO()

    workbook = xlsxwriter.Workbook(in_memory_file)
    worksheet = workbook.add_worksheet()

    worksheet.freeze_panes(3, 2)
    worksheet.set_zoom(175)

    format_default = workbook.add_format({})
    format_default.set_align("left")
    format_default.set_border(1)

    format_header = workbook.add_format({})
    format_header.set_align("left")
    format_header.set_border(1)
    format_header.set_bold(True)

    format_nums = workbook.add_format({})
    format_nums.set_align("center")
    format_nums.set_border(1)


    format_formula = workbook.add_format({})
    format_formula.set_align("center")
    format_formula.set_border(1)
    format_formula.set_bg_color("#81c89b")

    students = {stud.id: stud.name for stud in study_group.students}

    worksheet.write_column(value_begin_row_index - 1, 0, ["№", *list(range(1, len(students) + 1))], format_header)
    worksheet.write_column(value_begin_row_index - 1, 1, ["ФИО", *list(students.values())], format_header)

    col_num = 2
    merge_range_args = []

    for type_name, type_color in zip(performance_types, cycle(type_colors)):
        temp_format_header = workbook.add_format()
        temp_format_header.set_align("left")
        temp_format_header.set_border(1)
        
        temp_format_header.set_bold(True)

        columns: list[GradeColumn] = list(filter(
            lambda el: el.grade_type.name == type_name and not el.grade_type.archived and not el.hidden,
            discipline_table.grade_columns
        ))

        if not len(columns):
            continue

        columns.sort(key=lambda el: el.topic.date)
        num = 0

        temp_format_header.set_bg_color(columns[0].grade_type.color if columns[0].grade_type.color else '#ffffff')


        merge_range_args.append((value_begin_row_index - 3, col_num, value_begin_row_index - 3, col_num + len(columns),
                                 columns[0].grade_type.name, temp_format_header))
        first_col = col_num
        for col in columns:
            num += 1
            col_headers = [num, str(col.topic.date.strftime(r'%d.%m'))] if col.grade_type.type != 'tasks' else [num,
                                                                                                  col.topic.task_link_name]

            grades = {grade.student_id: grade.value for grade in col.grades}
            grades = [grades[stud_id] if stud_id in grades else "" for stud_id in students.keys() if stud_id]
            grades = list(map(lambda x: "" if int(x or 0) == 0 else float(x), grades))

            worksheet.write_column(value_begin_row_index - len(col_headers), col_num, col_headers, format_header)
            worksheet.write_column(value_begin_row_index, col_num, grades, format_nums)
            col_num += 1

        worksheet.write(value_begin_row_index - 1, col_num, "Итого:", temp_format_header)
        worksheet.write(value_begin_row_index - 2, col_num, "", temp_format_header)
        for i in range(1, len(students) + 1):
            worksheet.write_formula(
                value_begin_row_index + i - 1, col_num,
                f'=SUM({xl_col_to_name(first_col)}{value_begin_row_index + i}:{xl_col_to_name(col_num - 1)}{value_begin_row_index + i})',
                temp_format_header
            )

        col_num += 1

    worksheet.autofit()

    for args in merge_range_args:
        worksheet.merge_range(*args)

    workbook.close()
    in_memory_file.seek(0)
    return in_memory_file
