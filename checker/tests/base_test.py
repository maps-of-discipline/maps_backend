from abc import abstractmethod

from checker.aup_data_filter import AupDataFilter, skip
from models import *
from ..data_classes import Test
from ..utils import method_time


class BaseTest:

    @method_time
    def __init__(self, db_instance: SQLAlchemy, aup: AupInfo):
        self.report: Test | None = None
        self.db = db_instance
        self.min = self.max = self.measure_id = None
        self.instance: Rule | None = None
        self.aup_info = aup
        self.data_filter: AupDataFilter = AupDataFilter(aup)
        self.data_filter.filters = [skip]

    def fetch_test(self, association: AupInfoHasRuleTable):
        self.min = association.min
        self.max = association.max
        self.measure_id = association.ed_izmereniya_id
        self.instance = association.rule

        self.report = Test(
            id=self.instance.id,
            title=self.instance.title,
            result=False,
            headers=[],
            data=[],
        )

    @abstractmethod
    def assert_test(self) -> Test:
        pass

    @abstractmethod
    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        return None

    def _compare_value(self, value: float):
        result = True
        if self.min:
            result = value >= self.min

        if self.max:
            result = result and value <= self.max

        return result
