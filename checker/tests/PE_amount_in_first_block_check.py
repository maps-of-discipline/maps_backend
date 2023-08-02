from math import fsum
from .base_test import BaseTest
from models import *
from fuzzywuzzy import process


class PEAmountInFirstBlockTest(BaseTest):
    def assert_test(self, aup: AupInfo) -> dict:
        zet_zum = []
        for el in aup.aup_data:
            el: AupData
            # if process.extractOne()

        return self.result
