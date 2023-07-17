from .tests.base_test import BaseTest
import json


class AupChecker:
    def __init__(self, aup: str, test_list: list[BaseTest] = None):
        self._aup = aup
        self._tests: list[BaseTest] = test_list if test_list else []

    def add_test(self, test: BaseTest) -> None:
        self._tests.append(test)

    def get_report(self,) -> str:
        report = {
            "aup": self._aup,
            "tests": []
        }
        for test in self._tests:
            report["tests"].append(test.assert_test())

        return json.dumps(report, ensure_ascii=False)