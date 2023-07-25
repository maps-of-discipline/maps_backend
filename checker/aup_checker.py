from flask_sqlalchemy import SQLAlchemy
from models import AupInfo
from .tests import *

import json


class AupChecker:

    # index in db: associated python test
    __test_dict = {
        1: TotalZetTest,
        2: ZetCheckBySemester
    }

    def __init__(self, aup_object: AupInfo, db_instance: SQLAlchemy):
        self.db = db_instance
        self.aup = aup_object

    def get_report(self,) -> str:
        report = {
            "aup": self.aup.num_aup,
            "tests": []
        }

        for el in self.aup.rule_associations:
            test = self.__test_dict[el.rule_id](self.db)
            test.fetch_test(el)
            report["tests"].append(test.assert_test(self.aup))

        return json.dumps(report, ensure_ascii=False)


