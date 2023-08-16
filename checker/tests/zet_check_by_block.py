from math import fsum

from flask_sqlalchemy import SQLAlchemy

from models import AupInfoHasRuleTable, AupInfo
from .base_test import BaseTest
from ..data_classes import Test
from ..utils import method_time


class BaseZetCheckByBlock(BaseTest):
    # because of different names of blocks in db. Contains d_block.id
    block_nums: list
    degree_id_to_amount: dict

    def __init__(self, db_instance: SQLAlchemy, aup: AupInfo):
        super().__init__(db_instance, aup)
        aup_id = self.aup_info.id_aup

        self._default_association = AupInfoHasRuleTable(
            rule_id=None,
            aup_info_id=aup_id,
            min=None,
            max=None,
            ed_izmereniya_id=3,
        )

    @method_time
    def assert_test(self, ) -> Test:
        self.data_filter.filters.append(lambda x: x.id_block in self.block_nums)
        zet_sum = []

        for amount, el in self.data_filter.with_measure(self.measure_id):
            zet_sum.append(amount)

        zet_sum = fsum(zet_sum) // 100

        self.report.value = zet_sum
        self.report.result = self._compare_value(zet_sum)
        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        self._default_association.rule_id = rule_id
        (self._default_association.min,
         self._default_association.max) = self.degree_id_to_amount.get(self.aup_info.id_degree, (None, None))
        return self._default_association if self._default_association.min else None


class ZetCheckByFirstBlock(BaseZetCheckByBlock):
    block_nums = [1, 5, 12, 15]

    degree_id_to_amount = {
        3: (160, None),  # Бакалавриат
        4: (80, None),  # Магистратура
        5: (282, None),  # Специалитет
    }


class ZetCheckBySecondBlock(BaseZetCheckByBlock):
    block_nums = [2, 8, 10, 11]

    degree_id_to_amount = {
        3: (20, None),  # Бакалавриат
        4: (21, None),  # Магистратура
        5: (27, None),  # Специалитет0
    }


class ZetCheckByThirdBlock(BaseZetCheckByBlock):
    block_nums = [3, 9, 14]

    degree_id_to_amount = {
        3: (9, None),  # Бакалавриат
        4: (9, None),  # Магистратура
        5: (6, 9),  # Специалитет
    }
