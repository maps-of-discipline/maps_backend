from models import *
from .base_test import BaseTest
from ..data_classes import Detailed, Test


class CompulsoryDisciplinesCheck(BaseTest):
    def assert_test(self, aup: AupInfo) -> Test:

        program_code = aup.name_op.program_code
        realized_okso: RealizedOkso = RealizedOkso.query.filter_by(program_code=program_code).one()
        fgos: SprFgosVo = realized_okso.fgos_vo[0]

        compulsory_disciplines = [[el.title, False] for el in fgos.compulsory_disciplines]

        for amount, el in self.processed_aup_data(aup):
            for cd in compulsory_disciplines:
                if cd[0] in el.discipline:
                    cd[1] = True

        result = True
        self.report.detailed = []
        for discipline in compulsory_disciplines:
            result = result and discipline[1]
            self.report.detailed.append(
                Detailed(
                    discipline=discipline[0],
                    result=discipline[1]
                ))
        self.report.result = result
        return self.report
