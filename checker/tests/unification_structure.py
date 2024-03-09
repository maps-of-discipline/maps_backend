from math import fsum
from pprint import pprint

from models import *
from .base_test import BaseTest
from ..data_classes import Test
from ..utils import method_time, match_attribute, match_element
from .discipline_variation_config import discipline_variations


class UnificationStructure(BaseTest):
    @method_time
    def assert_test(self) -> Test:
        self.data_filter.filters = []

        program_code = self.aup_info.name_op.program_code
        realized_okso = RealizedOkso.query.filter_by(program_code=program_code).first()
        self.report.headers = ['Период', 'Дисциплина', 'Значение', 'Результат']

        for unification in realized_okso.unifications:
            detailed = [
                [el.id for el in unification.periods],
                unification.discipline.title,
            ]

            for el in self.data_filter.filtered():
                if (match_attribute(el.discipline, 'discipline', discipline_variations[detailed[1]])
                        and el.id_period in detailed[0]):

                    detailed.append(el.id_period)
                    detailed.append(True)

            self.report.data.append(detailed)
        
        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=self.aup_info.id_aup,
            min=None,
            max=None,
            ed_izmereniya_id=3,
        )
