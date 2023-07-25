from math import fsum
from .base_test import BaseTest
from models import *


class TotalZetTest(BaseTest):
    def assert_test(self, aup: AupInfo) -> dict:
        sum_zet = []

        for amount, el in self.processed_aup_data(aup):
            sum_zet.append(amount)

        sum_zet = fsum(sum_zet) // 100

        self.result['value'] = sum_zet
        self.result['result'] = self._compare_value(sum_zet)
        return self.result
