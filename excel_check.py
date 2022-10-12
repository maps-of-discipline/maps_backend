from openpyxl import load_workbook

def get_maximum_rows(*, sheet_object):
    rows = 0
    for max_row, row in enumerate(sheet_object, 1):
        if not all(col.value is None for col in row):
            rows += 1
    return rows

def check_empty_ceils(file):
    wb = load_workbook(file)
    ws = wb['Лист2']
    max_row = get_maximum_rows(sheet_object=ws)
    # print('!!!!!!!!!!!!!!!!!!!!!!!!!', ws.max_row)
    err_arr = []
    for letter in 'ABCEFGH':
        for num in range(1, max_row + 1):
            if ws[letter+str(num)].value == None:
                err_arr.append(letter+str(num))
    if err_arr == []:
        return True, err_arr
    else:
        return False, err_arr

def layout_of_disciplines(file):
    wb = load_workbook(file)
    ws = wb['Лист2']
    max_row = get_maximum_rows(sheet_object=ws)
    for num in range(1, max_row + 1):
        if 'Элективные дисциплины' in ws['E'+str(num)].value:
            temp_num = ws['E'+str(num)].value
            temp_value = ws['F'+str(num)].value
            count = 0
            for i in range(num, max_row + 1):
                count += 1
                if ws['E'+str(i)].value == temp_num and ws['F'+str(i)].value != temp_value:
                    for j in range(1, count):
                        ws['F'+str(i-j)] = temp_value + ' / ' + ws['F'+str(i+(j-1))].value
                        ws['F'+str(i+(j-1))] = 'None'
                        ws['E'+str(i+(j-1))] = 'None'
    for num in range(1, max_row + 1):
        if ws['E'+str(num)].value == 'None':
            ws.delete_rows(num)
    for num in range(1, max_row + 1):
        if ws['E'+str(num)].value == 'None':
            ws.delete_rows(num)
    wb.save(file)

