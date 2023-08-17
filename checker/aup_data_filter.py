from typing import Callable, Generator

from models import *
from tools import check_skiplist


class AupDataFilter:
    def __init__(self, aup_info: AupInfo):
        self.aup: AupInfo = aup_info
        self.filters: list[Callable[[AupData], bool]] = []

    def add_filters(self, filter_func: list[Callable[[AupData], bool]]) -> None:
        self.filters.append(*filter_func)

    def filtered(self) -> Generator[AupData, None, None]:
        for el in self.aup.aup_data:
            filter_res = [filter_(el) for filter_ in self.filters]
            if not all(filter_res):
                continue
            yield el

    def with_measure(self, measure_id: int) -> Generator[tuple[float, AupData], None, None]:
        transform_dict_coefficients = {
            # (from_id, to_id): coefficient
            (1, 1): 1,
            (2, 2): 1,
            (3, 3): 1,
            (1, 3): 1 / 36,
            (1, 2): 1.5 / 36,
            (2, 1): 54,
            (2, 3): 1.5,
            (3, 1): 36,
            (3, 2): 1 / 1.5
        }

        if measure_id > 3:
            measure_id = 3

        for el in self.filtered():
            amount = el.amount * transform_dict_coefficients[(el.id_edizm, measure_id)]
            yield amount, el


def skip(el: AupData):
    return check_skiplist(el.zet, el.discipline, el.record_type.title, el.block.title)
