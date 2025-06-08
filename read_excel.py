import pandas
from pandas import DataFrame
from werkzeug.datastructures import FileStorage

# Константы для названий листов и колонок
SHEET_HEADER = 'Лист1'
SHEET_DATA = 'Лист2'

COL_NAME = 'Наименование'
COL_ZET = 'ЗЕТ'
COL_QUANTITY = 'Количество'
COL_CIPHER = 'Шифр'
COL_MODULE = 'Модуль'

# Значения для форматирования стандарта
STANDARD_OLD_VALUES = ['ФГОС3++', 'ФГОС ВО (3++)']
STANDARD_NEW_VALUE = 'ФГОС ВО 3++'

# Значение по умолчанию для модуля
DEFAULT_MODULE_NAME = 'Без названия'


def format_standard(value: str) -> str:
    return STANDARD_NEW_VALUE if value in STANDARD_OLD_VALUES else value


def format_cipher(value) -> str:
    return str(value).replace('Б.', 'Б')


def read_excel(file: FileStorage) -> tuple[DataFrame, DataFrame]:
    data = pandas.read_excel(file, sheet_name=None, engine='calamine')

    header_df = data[SHEET_HEADER]
    header_df.loc[7, COL_NAME] = format_standard(header_df[COL_NAME][7])

    data_df = data[SHEET_DATA]

    # remove unnamed columns
    data_df.drop(data_df.columns[data_df.columns.str.contains('unnamed', case=False)], axis=1, inplace=True)

    to_float = lambda x: float(str(x).replace(',', '.'))

    data_df[COL_ZET] = data_df[COL_ZET].apply(to_float)
    data_df[COL_QUANTITY] = data_df[COL_QUANTITY].apply(to_float)
    data_df[COL_CIPHER] = data_df[COL_CIPHER].apply(format_cipher)

    data_df = data_df.fillna(
        {
            COL_MODULE: DEFAULT_MODULE_NAME,
            COL_QUANTITY: 0,
            COL_ZET: 0,
        },
    )

    return header_df, data_df