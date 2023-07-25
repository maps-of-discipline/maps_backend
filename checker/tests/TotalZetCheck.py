from .base_test import BaseTest
from models import *
from tools import check_skiplist


class TotalZetTest(BaseTest):
    def assert_test(self, aup: AupInfo) -> dict:
        result = {
            "id": self.instance.id,
            "title": self.instance.title,
        }

        sum_zet = 0
        for el in aup.aup_data:
            el: AupData

            # skip row if discipline in skip list
            if not check_skiplist(el.zet, el.discipline, el.record_type.title, el.block.title):
                continue

            amount = el.amount
            if el.id_edizm == 1:
                amount = amount / 36
            elif el.id_edizm == 2:
                amount = amount * 1.5
            sum_zet += amount / 100

        result['min'] = self.min
        result['value'] = sum_zet
        result['max'] = self.max

        res = True
        if self.min:
            res = sum_zet >= self.min

        if self.max:
            res = res and sum_zet <= self.max

        result['result'] = res
        return result
