from base_test import BaseTest
from models import AupData


class ZetCheckBySemester(BaseTest):
    def __init__(self, aup_data: AupData):
        super().__init__(aup_data)
        self.minimal_value = None
        self.maximum_value = None
        print(f'[--LOG--] ZetCheckBySemestr test has inited')

    def fetch_test(self):
        self.id = 2
        self.title = "Объем учебной программы за семестр(зет)"
        self.minimal_value = 70
        self.maximum_value = 70

    def assert_test(self,) -> str:
        sum_zet = {}
        for row in self.aup_data:
            sum_zet[row.is_]
