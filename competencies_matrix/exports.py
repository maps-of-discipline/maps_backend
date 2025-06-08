# filepath: competencies_matrix/exports.py
import io
import logging
from typing import Dict, Any
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side, Alignment
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

def generate_tf_list_excel_export(selected_data: Dict[str, Any]) -> bytes:
    """
    (НОВАЯ ФУНКЦИЯ)
    Генерирует Excel-файл с перечнем выбранных ОТФ и ТФ в формате,
    соответствующем Таблице 1 из документа ОПОП.
    ЗУНы на этом этапе не учитываются.

    Args:
        selected_data: Словарь, содержащий данные о выбранных ТФ.
                       Формат: { 'profStandards': [ { 'id': ..., 'code': ..., 'name': ...,
                                'generalized_labor_functions': [ { ..., 'labor_functions': [ ... ] } ] } ] }
    Returns:
        bytes: Содержимое Excel-файла в виде байтов.
    """
    logger.info("Starting Excel export generation for TF List.")
    wb = Workbook()
    ws = wb.active
    ws.title = "Перечень ТФ"

    # --- Стили ---
    header_font = Font(name='Calibri', size=11, bold=True)
    cell_border = Border(top=Side(style='thin'), bottom=Side(style='thin'), left=Side(style='thin'), right=Side(style='thin'))
    alignment_wrap_center = Alignment(wrap_text=True, vertical='center', horizontal='center')
    alignment_wrap_left = Alignment(wrap_text=True, vertical='top', horizontal='left')

    # --- Заголовки ---
    headers = [
        ("Код и наименование\nпрофессионального\nстандарта", 40),
        ("Обобщенные трудовые функции", None), # Заголовок для группы
        ("Трудовые функции", None) # Заголовок для группы
    ]
    sub_headers = [
        "", "код", "наименование", "уровень\nквалификации",
        "наименование", "код", "уровень\n(подуровень)\nквалификации"
    ]

    # Объединение ячеек для основных заголовков
    ws.append([h[0] for h in headers])
    ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=1)
    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=4)
    ws.merge_cells(start_row=1, start_column=5, end_row=1, end_column=7)

    # Добавление подзаголовков
    ws.append(sub_headers)

    # Применение стилей к заголовкам
    for row in ws.iter_rows(min_row=1, max_row=2):
        for cell in row:
            cell.font = header_font
            cell.border = cell_border
            cell.alignment = alignment_wrap_center

    # Установка ширины колонок
    ws.column_dimensions[get_column_letter(1)].width = headers[0][1]
    ws.column_dimensions[get_column_letter(2)].width = 10
    ws.column_dimensions[get_column_letter(3)].width = 40
    ws.column_dimensions[get_column_letter(4)].width = 15
    ws.column_dimensions[get_column_letter(5)].width = 40
    ws.column_dimensions[get_column_letter(6)].width = 15
    ws.column_dimensions[get_column_letter(7)].width = 15

    # --- Заполнение данными ---
    current_row_idx = 3 # Начинаем с третьей строки
    for ps_data in selected_data.get('profStandards', []):
        ps_start_row = current_row_idx
        for otf_data in ps_data.get('generalized_labor_functions', []):
            otf_start_row = current_row_idx
            for tf_data in otf_data.get('labor_functions', []):
                row_values = [
                    f"{ps_data.get('code', '')}\n{ps_data.get('name', '')}",
                    otf_data.get('code', ''),
                    otf_data.get('name', ''),
                    otf_data.get('qualification_level', ''),
                    tf_data.get('name', ''),
                    tf_data.get('code', ''),
                    tf_data.get('qualification_level', '')
                ]
                ws.append(row_values)
                current_row_idx += 1
            
            # Слияние ячеек для ОТФ, если в ней было больше одной ТФ
            if current_row_idx - 1 > otf_start_row:
                ws.merge_cells(start_row=otf_start_row, start_column=2, end_row=current_row_idx - 1, end_column=2)
                ws.merge_cells(start_row=otf_start_row, start_column=3, end_row=current_row_idx - 1, end_column=3)
                ws.merge_cells(start_row=otf_start_row, start_column=4, end_row=current_row_idx - 1, end_column=4)

        # Слияние ячеек для ПС, если в нем было больше одной строки
        if current_row_idx - 1 > ps_start_row:
            ws.merge_cells(start_row=ps_start_row, start_column=1, end_row=current_row_idx - 1, end_column=1)

    # Применение стилей ко всем ячейкам данных
    for row in ws.iter_rows(min_row=3, max_row=current_row_idx - 1):
        for cell in row:
            cell.border = cell_border
            if cell.column > 1:
                cell.alignment = alignment_wrap_left if cell.column in [3, 5] else alignment_wrap_center
            else:
                 cell.alignment = alignment_wrap_left # Для объединенной ячейки ПС

    # Сохранение в байты
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    logger.info("Excel export for TF List generation finished.")
    return bio.getvalue()