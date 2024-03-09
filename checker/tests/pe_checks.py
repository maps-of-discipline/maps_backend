from math import fsum

from models import AupInfoHasRuleTable
from .base_test import BaseTest
from ..data_classes import Test
from ..utils import match_element


# [Руками поменял данные в бд] aup 114: 'Элективные дисциплины по физической культуре и спорту' id_type_record: 2 -> 3

class PEBaseTest(BaseTest):
    __filter_conditions = {
        "accept": {
            'discipline': [
                'физи',
                'спорт',
            ]
        },
        "decline": {
            'discipline': {
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
    }

    _type_records: list[int] = []

    def assert_test(self, ) -> Test:
        self.report.headers = ['От', 'До', 'Значение', 'Результат']
        self.data_filter.filters = [
            lambda x: match_element(x, self.__filter_conditions),
            lambda x: x.id_type_record in self._type_records
        ]

        sums = {}
        for amount, el in self.data_filter.with_measure(self.measure_id):
            if el.discipline not in sums.keys():
                sums.update({el.discipline: [amount]})
            else:
                sums[el.discipline].append(amount)

        for key in sums:
            sums[key] = fsum(sums[key]) / 100

        if len(sums.keys()) != 1:
            self.report.result = False
            return self.report

        self.report.value = sums[list(sums)[0]]
        self.report.result = self._compare_value(sums[list(sums)[0]])
        self.report.data.append([self.min, self.max, self.report.value, self.report.result])
        return self.report


class PEAmountInFirstBlockTest(PEBaseTest):
    _type_records = [1, 2]

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        if self.aup_info.id_degree in [3, 5]:
            return AupInfoHasRuleTable(
                rule_id=rule_id,
                aup_info_id=self.aup_info.id_aup,
                min=2,
                max=None,
                ed_izmereniya_id=3
            )
        else:
            return None


class OptionalPEAmount(PEBaseTest):
    _type_records = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 16, 19]

    # TODO: [?] Уточнить насчет физры на заочке\очке-заочке
    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        if self.aup_info.id_degree in [3, 5] and self.aup_info.id_form not in [2, 3]:
            return AupInfoHasRuleTable(
                rule_id=rule_id,
                aup_info_id=self.aup_info.id_aup,
                min=328,
                max=None,
                ed_izmereniya_id=1
            )
        else:
            return None
