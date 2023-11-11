from math import fsum
from pprint import pprint

from models import *
from .base_test import BaseTest
from ..data_classes import Test, Detailed
from ..utils import method_time


class UnificationLoadCheck(BaseTest):
    @method_time
    def assert_test(self) -> Test:
        program_code = self.aup_info.name_op.program_code
        realized_okso = RealizedOkso.query.filter_by(program_code=program_code).first()

        disciplines = {}

        for amount, el in self.data_filter.with_measure(self.measure_id):
            key = (el.id_period, el.discipline)
            value = {el.type_control.title: round(amount / 100)}
            if key not in disciplines.keys():
                disciplines.update({key: {**value}})
            else:
                disciplines[key].update({**value})

        self.report.detailed = []

        for unification in realized_okso.unifications:
            unification: Unification

            discipline = None
            period_id = None
            for key in [(period.id, unification.discipline.title) for period in unification.periods]:
                if key in disciplines.keys():
                    discipline = disciplines.pop(key)
                    period_id = key[0]

            if discipline is None:
                continue

            for el in unification.load:
                el: UnificationLoad
                self.report.detailed.append(Detailed(
                    period_id=period_id,
                    discipline=', '.join([el.unification.discipline.title, el.control_type.title]),
                    min=el.amount,
                    max=el.amount,
                    value=discipline.get(el.control_type.title),
                    result=(discipline.get(el.control_type.title) is not None and
                            discipline.get(el.control_type.title) == el.amount)
                ))

        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=self.aup_info.id_aup,
            min=None,
            max=None,
            ed_izmereniya_id=1,
        )
