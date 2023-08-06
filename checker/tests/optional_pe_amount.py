from math import fsum
from .base_test import BaseTest
from models import *


class OptionalPEAmount(BaseTest):
    def assert_test(self, aup: AupInfo) -> dict:
        for amount, el in self.processed_aup_data(aup):
            pass

        return self.report
