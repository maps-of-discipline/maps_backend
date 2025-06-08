import string
from abc import abstractmethod

import pandas
from maps.logic.tools import timeit, check_skiplist
from maps.models import db, AupInfo
from pandas import DataFrame

from utils.logging import logger

# Константы для названий колонок
COL_BLOCK = "Блок"
COL_CODE = "Шифр"
COL_PART = "Часть"
COL_MODULE = "Модуль"
COL_RECORD_TYPE = "Тип записи"
COL_DISCIPLINE = "Дисциплина"
COL_CONTROL_PERIOD = "Период контроля"
COL_LOAD = "Нагрузка"
COL_QUANTITY = "Количество"
COL_UNIT = "Ед. изм."
COL_ZET = "ЗЕТ"

# Константы для опций
OPT_INTEGRITY_MODEL = "checkboxIntegralityModel"
OPT_SUM_MODEL = "checkboxSumModel"
OPT_FORCED_UPLOAD_MODEL = "checkboxForcedUploadModel"

# Константы для букв колонок, проверяемых на пустые значения
COLS_TO_CHECK_EMPTY_CELLS = "ABEFGHJ"
HEADER_COL_TO_CHECK = "B"


class ExcelValidator:
    @classmethod
    @timeit
    def validate(cls, options: dict, header: DataFrame, data: DataFrame) -> list[dict]:
        """
        Если Required истина, то в случае неудачного теста последующие за ним не будут выполнены.
        """
        validators = [
            (LoadTitlesCheck(header, data), True),
            (LoadEmptyCellsCheck(header, data), True),
            (HeaderEmptyCellsCheck(header, data), False),
        ]

        if options.get(OPT_INTEGRITY_MODEL, True):
            validators.append((IntegrityCheck(header, data), False))

        if options.get(OPT_SUM_MODEL, True):
            validators.append((TotalZetCheck(header, data), False))

        if not options.get(OPT_FORCED_UPLOAD_MODEL, True):
            validators.append((ForcedUploadCheck(header, data), False))

        errors = []

        for validator, required in validators:
            if error := validator.validate():
                errors.append(error)

            if error and required:
                return errors
        logger.info(f"End of excel validation.")
        return errors


class AupValidator:
    def __init__(self, header: DataFrame, data: DataFrame):
        self.header: DataFrame = header
        self.data: DataFrame = data

    @abstractmethod
    def validate(self) -> dict | None:
        raise NotImplementedError()

    def add_skipped_to_df(self):
        self.data["skipped"] = self.data.apply(
            lambda row: not check_skiplist(
                row[COL_QUANTITY],
                row[COL_DISCIPLINE],
                row[COL_RECORD_TYPE],
                row[COL_BLOCK],
            ),
            axis=1,
        )


class IntegrityCheck(AupValidator):
    def validate(self) -> dict | None:
        """
        Метод для проверки дисциплин учебного плана на целочисленность зет.
        Считает общий объем по дисциплине за семестр, если сумма не целая - записывает ошибку.
        Возвращает список ошибок.
        """
        logger.debug("IntegrityCheck: validating...")
        self.add_skipped_to_df()

        df = self.data[~self.data["skipped"]]  # '~' used to inverse
        df = df[[COL_DISCIPLINE, COL_CONTROL_PERIOD, COL_ZET]]
        df = df.groupby([COL_DISCIPLINE, COL_CONTROL_PERIOD], as_index=False)[COL_ZET].sum()
        df["res"] = df[COL_ZET].apply(lambda x: float(abs(x - round(x))) <= 0.05)

        errors = []
        for _, discipline, period, zet, res in df[~df["res"]].itertuples():
            errors.append(f"{period}: {discipline} {zet}")

        if not errors:
            logger.debug("IntegrityCheck: ok")
            return

        logger.debug("IntegrityCheck: failed")
        return {"message": f"Ошибка при подсчете ЗЕТ" + "\n".join(errors)}


class LoadEmptyCellsCheck(AupValidator):
    def validate(self) -> dict | None:
        logger.debug("LoadEmptyCellsCheck: validating...")

        columns = {el1: el2 for el1, el2 in zip(self.data, string.ascii_uppercase[:11])}
        df = self.data.rename(columns=columns)

        cells = []
        for i in range(len(df)):
            for column in COLS_TO_CHECK_EMPTY_CELLS:
                if df[column][i] is None or pandas.isna(df[column][i]):
                    cells.append(f"{column}{i + 2}")

        if not cells:
            logger.debug("LoadEmptyCellsCheck: ok")
            return

        logger.debug("LoadEmptyCellsCheck: failed")
        return {
            "message": "В документе на втором листе не заполнены ячейки",
            "cells": cells,
        }


class HeaderEmptyCellsCheck(AupValidator):
    def validate(self) -> dict | None:
        logger.debug("HeaderEmptyCellsCheck: validating...")
        columns = {
            el1: el2 for el1, el2 in zip(self.header, string.ascii_uppercase[:2])
        }
        data = self.header.rename(columns=columns)

        cells = []
        column = HEADER_COL_TO_CHECK
        for i in range(15):
            if data[column][i] is None or pandas.isna(data[column][i]):
                cells.append(f"{column}{i + 2}")

        if not cells:
            logger.debug("HeaderEmptyCellsCheck: ok")
            return

        logger.debug("HeaderEmptyCellsCheck: failed")
        return {
            "message": "В документе на первом листе не заполнены ячейки",
            "cells": cells,
        }


class LoadTitlesCheck(AupValidator):
    def validate(self) -> dict | None:
        logger.debug("LoadTitlesCheck: validating...")
        columns = [
            COL_BLOCK,
            COL_CODE,
            COL_PART,
            COL_MODULE,
            COL_RECORD_TYPE,
            COL_DISCIPLINE,
            COL_CONTROL_PERIOD,
            COL_LOAD,
            COL_QUANTITY,
            COL_UNIT,
            COL_ZET,
        ]
        if not all([col in list(self.data.columns) for col in columns]):
            logger.debug("LoadTitlesCheck: failed")
            return {
                "message": "Второй лист выгрузки должен содержать следующие колонки: "
                + ", ".join(columns)
            }

        logger.debug("LoadTitlesCheck: ok")


class TotalZetCheck(AupValidator):
    def validate(self) -> dict | None:
        """
        Метод для проверки, чтобы общая сумма ЗЕТ соответствовало норме (30 * кол-во семестров)
        """
        logger.debug("TotalZetCheck: validating...")

        self.add_skipped_to_df()

        periods = self.data.groupby(COL_CONTROL_PERIOD)

        total_sum = len(periods) * 30.0
        s = self.data[~self.data["skipped"]][COL_ZET].sum()

        if abs(total_sum - s) < 0.1:
            logger.debug("TotalZetCheck: ok")
            return

        logger.debug("TotalZetCheck: failed")
        return {
            "message": f"В выгрузке общая сумма ЗЕТ ({s} ЗЕТ) не соответствует норме ({total_sum} ЗЕТ)"
        }


class ForcedUploadCheck(AupValidator):
    def validate(self) -> dict | None:
        logger.debug("ForcedUploadValidator: validating...")

        aup = self.header.set_index("Наименование")["Содержание"].to_dict()["Номер АУП"]

        if AupInfo.query.filter_by(num_aup=aup).first():
            logger.debug(f"ForcedUploadValidator: failed. AUP {aup} already exists.")
            return {"message": f"Учебный план № {aup} уже существует.", "aup": aup}
        else:
            logger.debug("ForcedUploadValidator: ok")
