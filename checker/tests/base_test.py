from models import *
from abc import abstractmethod


class BaseTest:
    # test id according to db record
    # test_id: int
    title: str
    id: int

    def __init__(self, aup_data: AupData):
        self._aup_data = aup_data
        self.fetch_test()

    @abstractmethod
    def fetch_test(self):
        pass

    @abstractmethod
    def assert_test(self,) -> str:
        pass

