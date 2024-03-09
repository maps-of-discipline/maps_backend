from math import fsum
from pprint import pprint

from models import *
from .base_test import BaseTest
from ..data_classes import Test
from ..utils import method_time


class UnificationAmountCheck(BaseTest):
    @method_time
    def assert_test(self) -> Test:
        self.data_filter.filters = []

        program_code = self.aup_info.name_op.program_code
        realized_okso: RealizedOkso = RealizedOkso.query.filter_by(program_code=program_code).first()
        self.report.detailed = []

        disciplines = {}
        for amount, el in self.data_filter.with_measure(3):
            el: AupData
            key = (el.discipline, el.id_period)
            if key not in disciplines.keys():
                disciplines.update( {key : [amount]} )
            else:
                disciplines[key].append(amount)

        for key in disciplines:
            disciplines[key] = round(fsum(disciplines[key])) / 100

        self.report.result = True
        self.report.headers = ['Период', 'Дисциплина', 'От', 'До', 'Значение', 'Результат']

        for unification in realized_okso.unifications:
            keys = [(unification.discipline.title, el.id) for el in unification.periods]
            amount = 0
            for key in keys:
                value = disciplines.get(key, None)
                if value:
                    amount = value
                    break

            self.report.data.append([
                [el.id for el in unification.periods],
                unification.discipline.title,
                unification.amount,
                unification.amount,
                amount,
                amount == unification.amount
            ])

        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=self.aup_info.id_aup,
            min=None,
            max=None,
            ed_izmereniya_id=3,
        )
