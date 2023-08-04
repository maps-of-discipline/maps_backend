from math import fsum
from pprint import pprint

from .base_test import BaseTest
from models import *


class MinDisciplineZet(BaseTest):
    """Минимальный объем по дисциплине кроме БЖД и военной подготовки"""

    skip_list = [
        "Безопасность жизнедеятельности",
        "Безопасность жизнедеятельности (First Aid and Emergency Response)",
        "Безопасность жизнедеятельности в ЧС",
        "Безопасность жизнедеятельности в условиях чрезвычайных ситуаций / Защита населения и территорий в условиях чрезвычайных ситуаций",
        "Основы военной подготовки",
        "Основы военной подготовки (Basic Military Training)"
    ]

    def assert_test(self, aup: AupInfo) -> dict:
        disciplines = {}
        for amount, el in self.processed_aup_data(aup):
            if el.discipline in self.skip_list:
                continue

            if (el.discipline, el.id_period) not in disciplines.keys():
                disciplines.update({(el.discipline, el.id_period): [amount]})
            else:
                disciplines[(el.discipline, el.id_period)].append(amount)

        result = True
        self.result['detailed'] = []

        for key in disciplines:
            disciplines[key] = fsum(disciplines[key]) / 100

            result = result and self._compare_value(disciplines[key])

            self.result['detailed'].append({
                "discipline": key[0],
                'period_id': key[1],
                "value": disciplines[key],
                "result": self._compare_value(disciplines[key])
            })

        self.result['result'] = result

        return self.result
