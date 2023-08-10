from math import fsum

from models import AupInfo, D_Period
from .base_test import BaseTest
from ..data_classes import Detailed
from ..utils import method_time


class ZetCheckByYear(BaseTest):
    @method_time
    def assert_test(self, aup: AupInfo) -> object:
        semesters = {el.id: [] for el in self.db.session.query(D_Period).all()}

        for amount, el in self.processed_aup_data(aup):
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
