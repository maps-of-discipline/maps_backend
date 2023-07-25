from models import *
from abc import abstractmethod

from tools import check_skiplist


class BaseTest:
    instance: Rule

    def __init__(self, db_instance: SQLAlchemy):
        self.result = {}
        self.db = db_instance
        self.min = self.max = self.ed_izmereniya_id = None

    def fetch_test(self, association: AupInfoHasRuleTable):
        self.min = association.min
        self.max = association.max
        self.ed_izmereniya_id = association.ed_izmereniya_id
        self.instance = association.rule

        self.result = {
            "id": self.instance.id,
            "title": self.instance.title,
            "min": self.min,
            "max": self.max,
            "value": None,
            "result": False,
            "detailed": None,
        }

    @abstractmethod
    def assert_test(self, aup: AupInfo) -> object:
        pass

    def _compare_value(self, value: float):
        result = True
        if self.min:
            result = value >= self.min

        if self.max:
            result = result and value <= self.max

        return result

    @staticmethod
    def processed_aup_data(aup: AupInfo):
        """Used for skip disciplines and convert amount from hours to zet"""
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

            yield amount, el
