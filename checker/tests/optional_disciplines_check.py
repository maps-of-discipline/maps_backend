from math import fsum

from models import *
from .base_test import BaseTest
from ..data_classes import Test
from ..utils import method_time, match_element


# Факультативные дисциплины (общий объём до 10 ЗЕТ)
class OptionalDisciplinesCheck(BaseTest):
    optional_filter = {
        'accept': {
            'id_type_record': [13, 15, 16],
        },
        'decline': {}
    }

    @method_time
    def assert_test(self) -> Test:
        self.data_filter.filters = [lambda x: match_element(x, self.optional_filter)]
        self.report.headers = ['Период', 'Дисциплина', 'От', 'До', 'Значение', 'Результат']
        sum_zet = {}
        for amount, el in self.data_filter.with_measure(self.measure_id):
            if (el.discipline, el.id_period) not in sum_zet.keys():
                sum_zet.update({(el.discipline, el.id_period): [amount]})
            else:
                sum_zet[(el.discipline, el.id_period)].append(amount)

        for key in sum_zet:
            sum_zet[key] = fsum(sum_zet[key]) / 100
            self.report.data.append([key[1], key[0], None, None, sum_zet[key], self._compare_value(sum_zet[key])])

        self.report.value = sum([el[4] for el in self.report.data])
        self.report.result = self._compare_value(self.report.value)
        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=self.aup_info.id_aup,
            min=None,
            max=10,
            ed_izmereniya_id=3
        )
