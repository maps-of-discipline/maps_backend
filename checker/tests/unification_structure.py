from math import fsum
from pprint import pprint

from models import *
from .base_test import BaseTest
from ..data_classes import Test, Detailed
from ..utils import method_time, match_attribute, match_element
from .discipline_variation_config import discipline_variations


class UnificationStructure(BaseTest):
    @method_time
    def assert_test(self) -> Test:
        self.data_filter.filters = []

        program_code = self.aup_info.name_op.program_code
        realized_okso = RealizedOkso.query.filter_by(program_code=program_code).first()
        self.report.detailed = []

        for unification in realized_okso.unifications:
            detailed = Detailed(
                discipline=unification.discipline.title,
                period_id=[el.id for el in unification.periods],
                result=False
            )

            for el in self.data_filter.filtered():
                if (match_attribute(el.discipline, 'discipline', discipline_variations[detailed.discipline])
                        and el.id_period in detailed.period_id):

                    detailed.value = el.id_period
                    detailed.result = True

            self.report.detailed.append(detailed)
        
        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=self.aup_info.id_aup,
            min=None,
            max=None,
            ed_izmereniya_id=None,
        )
