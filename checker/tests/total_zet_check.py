from math import fsum

from models import *
from .base_test import BaseTest
from ..data_classes import Test
from ..utils import method_time


class TotalZetTest(BaseTest):
    @method_time
    def assert_test(self) -> Test:
        sum_zet = []
        self.report.headers = ['От', 'До', 'Значение', 'Результат']

        for amount, el in self.data_filter.with_measure(self.measure_id):
            sum_zet.append(amount)

        sum_zet = fsum(sum_zet) // 100

        self.report.value = sum_zet
        self.report.result = self._compare_value(sum_zet)
        self.report.data.append([self.min, self.max, self.report.value, self.report.result])
        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        id_aup = self.aup_info.id_aup
        degree_to_amount = {
            3: 240,
            4: 120,
            5: 330,
        }

        zet_amount = degree_to_amount.get(self.aup_info.id_degree, None)
        if zet_amount is None:
            return None

        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=id_aup,
            min=zet_amount,
            max=zet_amount,
            ed_izmereniya_id=3,
        )
