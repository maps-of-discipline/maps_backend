from models import *
from abc import abstractmethod


class BaseTest:

    instance: Rule

    def __init__(self, db_instance: SQLAlchemy):
        self.db = db_instance
        self.min = self.max = self.ed_izmereniya_id = None

    def fetch_test(self, association: AupInfoHasRuleTable):
        self.min = association.min
        self.max = association.max
        self.ed_izmereniya_id = association.ed_izmereniya_id
        self.instance = association.rule

    @abstractmethod
    def assert_test(self, aup_object: AupInfo) -> str:
        pass
