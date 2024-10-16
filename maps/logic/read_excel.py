import pandas
from pandas import DataFrame
from werkzeug.datastructures import FileStorage


def format_standard(value: str) -> str:
    return 'ФГОС ВО 3++' if value in ['ФГОС3++', 'ФГОС ВО (3++)'] else value


def format_cipher(value) -> str:
    return str(value).replace('Б.', 'Б')


def read_excel(file: FileStorage) -> tuple[DataFrame, DataFrame]:
    data = pandas.read_excel(file, sheet_name=None, engine='calamine')

    header_df = data['Лист1']
    header_df.loc[7, 'Наименование'] = format_standard(header_df['Наименование'][7])

    data_df = data['Лист2']

    # remove unnamed columns
    data_df.drop(data_df.columns[data_df.columns.str.contains('unnamed', case=False)], axis=1, inplace=True)

    to_float = lambda x: float(str(x).replace(',', '.'))

    data_df['ЗЕТ'] = data_df['ЗЕТ'].apply(to_float)
    data_df['Количество'] = data_df['Количество'].apply(to_float)
    data_df['Шифр'] = data_df['Шифр'].apply(format_cipher)


    data_df = data_df.fillna(
        {
            'Модуль': 'Без названия',
            'Количество': 0,
            'ЗЕТ': 0,
        },
    )

    return header_df, data_df
