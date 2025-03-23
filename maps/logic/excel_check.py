import string
from abc import abstractmethod

import pandas
from maps.logic.tools import timeit, check_skiplist
from maps.models import db, AupInfo
from pandas import DataFrame


from utils.logging import logger


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

        if options.get("checkboxIntegralityModel", True):
            validators.append((IntegrityCheck(header, data), False))

        if options.get("checkboxSumModel", True):
            validators.append((TotalZetCheck(header, data), False))

        if not options.get("checkboxForcedUploadModel", True):
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
                row["Количество"],
                row["Дисциплина"],
                row["Тип записи"],
                row["Блок"],
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
        df = df[["Дисциплина", "Период контроля", "ЗЕТ"]]
        df = df.groupby(["Дисциплина", "Период контроля"], as_index=False)["ЗЕТ"].sum()
        df["res"] = df["ЗЕТ"].apply(lambda x: float(abs(x - round(x))) <= 0.05)

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
            for column in "ABEFGHJ":
                if df[column][i] is None or pandas.isna(df[column][i]):
                    cells.append(f"{column}{i + 2}")

        if not cells:
            logger.debug("IntegrityCheck: ok")
            return

        logger.debug("IntegrityCheck: failed")
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
        column = "B"
        for i in range(15):
            if data[column][i] is None or pandas.isna(data[column][i]):
                cells.append(f"{column}{i + 2}")

        if not cells:
            logger.debug("IntegrityCheck: ok")
            return

        logger.debug("IntegrityCheck: failed")
        return {
            "message": "В документе на первом листе не заполнены ячейки",
            "cells": cells,
        }


class LoadTitlesCheck(AupValidator):
    def validate(self) -> dict | None:
        logger.debug("LoadTitlesCheck: validating...")
        columns = [
            "Блок",
            "Шифр",
            "Часть",
            "Модуль",
            "Тип записи",
            "Дисциплина",
            "Период контроля",
            "Нагрузка",
            "Количество",
            "Ед. изм.",
            "ЗЕТ",
        ]
        if not all([col in list(self.data.columns) for col in columns]):
            logger.debug("IntegrityCheck: failed")
            return {
                "message": "Второй лист выгрузки должен содержать следующие колонки: "
                + ", ".join(columns)
            }

        logger.debug("IntegrityCheck: ok")


class TotalZetCheck(AupValidator):
    def validate(self) -> dict | None:
        """
        Метод для проверки, чтобы общая сумма ЗЕТ соответствовало норме (30 * кол-во семестров)
        """
        logger.debug("TotalZetCheck: validating...")

        self.add_skipped_to_df()

        periods = self.data.groupby("Период контроля")

        total_sum = len(periods) * 30.0
        s = self.data[~self.data["skipped"]]["ЗЕТ"].sum()

        if abs(total_sum - s) < 0.1:
            logger.debug("IntegrityCheck: ok")
            return

        logger.debug("IntegrityCheck: failed")
        return {
            "message": f"В выгрузке общая сумма ЗЕТ ({s} ЗЕТ) не соответствует норме ({total_sum} ЗЕТ)"
        }


class ForcedUploadCheck(AupValidator):
    def validate(self) -> dict | None:
        logger.debug("ForcedUploadValidator: validating...")

        aup = self.header.set_index("Наименование")["Содержание"].to_dict()["Номер АУП"]

        if AupInfo.query.filter_by(num_aup=aup).first():
            logger.debug(f"ForcedUploadValidator: failed. AUP {aup} alreade exists.")
            return {"message": f"Учебный план № {aup} уже существует.", "aup": aup}
        else:
            logger.debug("ForcedUploadValidator: ok")
