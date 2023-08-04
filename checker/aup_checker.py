from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from models import *
from .tests import *

import json

# TODO: проверить аупы, возможно считаются не правильно:
#     - 000016048
#     - 000019349
#


class AupChecker:

    # index in db: associated python test
    __test_dict = {
        1: TotalZetTest,
        2: ZetCheckByYear,
        3: ZetCheckByFirstBlock,
        4: ZetCheckBySecondBlock,
        5: ZetCheckByThirdBlock,
        6: PEAmountInFirstBlockTest,
        7: OptionalPEAmount,
        11: MinDisciplineZet,
    }

    def __init__(self, aup_object: AupInfo, db_instance: SQLAlchemy):
        self.db = db_instance
        self.aup = aup_object

    def get_report(self,) -> str:

        program_code = self.aup.name_op.program_code
        realized_okso: RealizedOkso = RealizedOkso.query.filter_by(program_code=program_code).one()

        report = {
            "aup": self.aup.num_aup,
            "okso": realized_okso.program_code,
            "total_result": False,
            "tests": []
        }

        for el in realized_okso.rule_associations:
            test = self.__test_dict[el.rule_id](self.db)
            test.fetch_test(el)
            report["tests"].append(test.assert_test(self.aup))

        report['total_result'] = all([el['result'] for el in report["tests"]])

        return json.dumps(report, ensure_ascii=False)


