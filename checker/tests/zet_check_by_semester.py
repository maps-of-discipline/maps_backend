from tools import check_skiplist
from .base_test import BaseTest
from models import AupInfo, D_Period, AupData
from math import fsum


class ZetCheckBySemester(BaseTest):
    def assert_test(self, aup: AupInfo) -> object:
        result = {
            "id": self.instance.id,
            "title": self.instance.title,
        }

        semesters = {el.id: [] for el in self.db.session.query(D_Period).all()}

        for amount, el in self.processed_aup_data(aup):
            semesters[el.id_period].append(amount)

        result['result'] = False
        result["detailed"] = []

        for key in semesters:
            semesters[key] = fsum(semesters[key]) / 100
            if semesters[key] > 0:
                result["detailed"].append({
                    'period_id': key,
                    'min': self.min,
                    'max': self.max,
                    'value': semesters[key],
                    'result': self._compare_value(semesters[key])
                })

        result['result'] = all([el['result'] for el in result['detailed']])

        return result
