from typing import Dict
from .base_test import BaseTest
from models import *


class TotalZetTest(BaseTest):
    def __init__(self, aup_data):
        super().__init__(aup_data)
        self.minimal_value = None
        self.maximum_value = None
        self.fetch_test()

    def fetch_test(self):
        # query to db to get values
        print("fetch test called")
        self.title = "Объем учебной программы за весь период обучаения(зет)"
        self.id = 1
        self.minimal_value = 240
        self.maximum_value = 240

    def assert_test(self,) -> dict[str, str]:
        zet_sum = 0
        for row in self._aup_data:
            print(f"{row.id} {row.id_aup} {row.discipline} {row.zet} {row.ed_izmereniya.title}")
            zet_sum += row.zet // 100

        return {
            "test_id": self.id,
            "test": self.title,
            "min": self.minimal_value,
            "max": self.maximum_value,
            "value": zet_sum,
            "resul": self.minimal_value <= zet_sum <= self.maximum_value
        }


