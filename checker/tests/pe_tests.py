from math import fsum

from models import *
from .base_test import BaseTest
from ..utils import match_disciple
from ..data_classes import Test, Detailed


# aup 114: 'Элективные дисциплины по физической культуре и спорту' id_type_record changed: 2 -> 3

class PEBaseTest(BaseTest):
    __filter_conditions = {
        "accept": [
            'физи',
            'спорт',
        ],
        "decline": {
            'матем',
            'метод',
            'процес',
            'неупруг',
            "хими",
            "ремонт",
            "авто",
            "анатом",
            'транспорт',
            "физик",
            "физио",
            "спортивный трек",
            "физические основы",
            "физическое моделирование",
        }
    }
    _type_records: list[int] = []

    def assert_test(self, aup: AupInfo) -> Test:
        sums = {}
        print(self._type_records)
        for amount, el in self.aup_data_with_zet(aup):

            if match_disciple(el.discipline, self.__filter_conditions) and el.id_type_record in self._type_records:
                key = el.discipline

                if key not in sums.keys():
                    sums.update({key: [amount]})
                else:
                    sums[key].append(amount)

        for key in sums:
            sums[key] = fsum(sums[key]) / 100

            if self.report.measure_id == 1:
                sums[key] *= 36

        if len(sums.keys()) != 1:
            self.report.result = False
            raise ValueError(f'Error in <{self.__class__.__name__}>. Количеств найденных дисциплин по физической культуре({len(sums.keys())}) не равно 1. AupID: {aup.id_aup} \n {sums=}')

        self.report.result = self._compare_value(sums[list(sums)[0]])

        return self.report


class PEAmountInFirstBlockTest(PEBaseTest):
    _type_records = [1, 2]


class OptionalPEAmount(PEBaseTest):
    _type_records = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 16, 19]

    def compilable_with_aup(self, aup: AupInfo) -> bool:
        return aup.id_form not in [2, 3]
