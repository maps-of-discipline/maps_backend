from math import fsum
from .base_test import BaseTest
from models import AupInfo


class BaseZetCheckByBlock(BaseTest):
    # because of different names of blocks in db. Contains d_block.id
    block_nums: list

    def assert_test(self, aup: AupInfo) -> object:
        zet_sum = []

        for amount, el in self.processed_aup_data(aup):
            if el.id_block in self.block_nums:
                zet_sum.append(amount)

        zet_sum = fsum(zet_sum) // 100

        self.report.value = zet_sum
        self.report.result = self._compare_value(zet_sum)
        return self.report


class ZetCheckByFirstBlock(BaseZetCheckByBlock):
    block_nums = [1, 5, 12, 15]


class ZetCheckBySecondBlock(BaseZetCheckByBlock):
    block_nums = [2, 8, 10, 11]


class ZetCheckByThirdBlock(BaseZetCheckByBlock):
    block_nums = [3, 9, 14]