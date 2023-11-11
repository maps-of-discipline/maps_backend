from models import *
from .base_test import BaseTest
from ..data_classes import Test, Detailed
from ..utils import method_time


# TODO: [?] Уточнить какие дисциплины надо проверять
class WorkloadBaseCheck(BaseTest):
    type_control_filter: list
    @method_time
    def assert_test(self) -> Test:
        disciplines = {}

        for amount, el in self.data_filter.with_measure(3):
            if (el.discipline, el.id_period) not in disciplines.keys():
                disciplines.update({(el.discipline, el.id_period): False})

            if el.id_type_control in self.type_control_filter:
                disciplines[(el.discipline, el.id_period)] = True

        self.report.result = True
        self.report.detailed = []
        for key in disciplines:
            self.report.result = self.report.result and disciplines[key]
            self.report.detailed.append(Detailed(
                period_id=key[1],
                discipline=key[0],
                result=disciplines[key]
            ))

        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=self.aup_info.id_aup,
            min=None,
            max=None,
            ed_izmereniya_id=3,
        )


class ClassroomClassesCheck(WorkloadBaseCheck):
    type_control_filter = [2, 3, 17]


class WorkloadControlCheck(WorkloadBaseCheck):
    type_control_filter = [1, 5, 9]
