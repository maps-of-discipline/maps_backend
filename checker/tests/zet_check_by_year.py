from math import fsum

from models import D_Period, AupInfoHasRuleTable
from .base_test import BaseTest
from ..data_classes import Detailed, Test
from ..utils import method_time


class ZetCheckByYear(BaseTest):
    @method_time
    def assert_test(self) -> Test:
        semesters = {el.id: [] for el in self.db.session.query(D_Period).all()}

        for amount, el in self.data_filter.with_measure(self.measure_id):
            semesters[el.id_period].append(amount)

        self.report.detailed = []

        for key in semesters:
            semesters[key] = fsum(semesters[key]) / 100

            if semesters[key] > 0 and key % 2 == 0:
                self.report.detailed.append(Detailed(
                    period_id=[key - 1, key],
                    min=self.min,
                    max=self.max,
                    value=[semesters[key - 1], semesters[key]],
                    result=self._compare_value(semesters[key - 1] + semesters[key])
                ))

        self.report.result = all([el.result for el in self.report.detailed])

        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=self.aup_info.id_aup,
            min=None,
            max=70,
            ed_izmereniya_id=3,
        )
