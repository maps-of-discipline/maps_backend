from math import fsum

from .base_test import BaseTest
from models import *
from tools import check_skiplist


class TotalZetTest(BaseTest):
    def assert_test(self, aup: AupInfo) -> dict:
        result = {
            "id": self.instance.id,
            "title": self.instance.title,
        }

        sum_zet = []
        for amount, el in self.processed_aup_data(aup):
            sum_zet.append(amount)

        sum_zet = fsum(sum_zet) // 100
        result['min'] = self.min
        result['value'] = sum_zet
        result['max'] = self.max
        result['result'] = self._compare_value(sum_zet)
        return result
