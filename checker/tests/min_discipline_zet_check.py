from math import fsum

from models import AupInfoHasRuleTable
from .base_test import BaseTest
from ..data_classes import Test
from ..utils import method_time, match_element


class MinDisciplineZet(BaseTest):
    """Минимальный объем по дисциплине кроме БЖД и военной подготовки"""

    __filter_list = {
        'accept': {},
        'decline': {
            'discipline': [
                "Безопасность жизнедеятельности",
                "Безопасность жизнедеятельности (First Aid and Emergency Response)",
                "Безопасность жизнедеятельности в ЧС",
                "Безопасность жизнедеятельности в условиях чрезвычайных ситуаций / Защита населения и территорий в условиях чрезвычайных ситуаций",
                "Основы военной подготовки",
                "Основы военной подготовки (Basic Military Training)"
            ]
        }
    }

    @method_time
    def assert_test(self) -> Test:
        self.report.headers = ['Дисциплина', 'Период', 'значение', 'От', 'Результат']
        self.data_filter.add_filters([lambda x: match_element(x, self.__filter_list)])
        disciplines = {}

        for amount, el in self.data_filter.with_measure(self.measure_id):
            if (el.discipline, el.id_period) not in disciplines.keys():
                disciplines.update({(el.discipline, el.id_period): [amount]})
            else:
                disciplines[(el.discipline, el.id_period)].append(amount)

        result = True
        for key in disciplines:
            disciplines[key] = round(fsum(disciplines[key]), 2) / 100
            result = result and self._compare_value(disciplines[key])

            self.report.data.append([key[0], key[1], disciplines[key], self.min, self._compare_value(disciplines[key])])

        self.report.result = result

        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=self.aup_info.id_aup,
            min=2,
            max=None,
            ed_izmereniya_id=3,
        )
