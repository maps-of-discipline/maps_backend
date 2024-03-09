from models import *
from .base_test import BaseTest
from ..data_classes import Test
from ..utils import match_element
from .discipline_variation_config import discipline_variations


class CompulsoryDisciplinesCheck(BaseTest):
    def assert_test(self) -> Test:
        self.report.headers = ["Дисциплина", "Результат", "Значение"]

        program_code = self.aup_info.name_op.program_code
        realized_okso: RealizedOkso = RealizedOkso.query.filter_by(program_code=program_code).one()
        fgos: SprFgosVo = realized_okso.fgos_vo[0]

        compulsory_disciplines = [[el.title, False] for el in fgos.compulsory_disciplines]

        for el in self.data_filter.filtered():
            for cd in compulsory_disciplines:
                filter_ = discipline_variations.get(cd[0], None)

                if cd[0] in el.discipline or (filter_ and match_element(el, filter_)):
                    cd[1] = True
                    cd.append(el.discipline)

        result = True
        for discipline in compulsory_disciplines:
            result = result and discipline[1]
            self.report.data.append([discipline[0], discipline[1], discipline[2]])
        self.report.result = result
        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        program_code = self.aup_info.name_op.program_code
        realized_okso: RealizedOkso = RealizedOkso.query.filter_by(program_code=program_code).one()

        if len(realized_okso.fgos_vo) == 0:
            return None

        fgos: SprFgosVo = realized_okso.fgos_vo[0]

        compulsory_disciplines = [[el.title, False] for el in fgos.compulsory_disciplines]

        if len(compulsory_disciplines) == 0:
            return None

        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=self.aup_info.id_aup,
            min=None,
            max=None,
            ed_izmereniya_id=3
        )
