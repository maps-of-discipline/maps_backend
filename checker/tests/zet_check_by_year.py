from tools import check_skiplist
from .base_test import BaseTest
from models import AupInfo, D_Period, AupData
from math import fsum


class ZetCheckByYear(BaseTest):
    def assert_test(self, aup: AupInfo) -> object:
        semesters = {el.id: [] for el in self.db.session.query(D_Period).all()}

        for amount, el in self.processed_aup_data(aup):
            semesters[el.id_period].append(amount)

        self.result["detailed"] = []

        for key in semesters:
            semesters[key] = fsum(semesters[key]) / 100

            if semesters[key] > 0 and key % 2 == 0:
                self.result["detailed"].append({
                    'period_id': [key-1, key],
                    'min': self.min,
                    'max': self.max,
                    'value': [semesters[key-1], semesters[key]],
                    'result': self._compare_value(semesters[key-1] + semesters[key])
                })

        self.result['result'] = all([el['result'] for el in self.result['detailed']])

        return self.result
