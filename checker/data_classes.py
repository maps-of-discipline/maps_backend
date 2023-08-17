import dataclasses
import json
from dataclasses import dataclass


@dataclass
class Detailed:
    period_id: int | list = None
    discipline: str = None
    min: float | None = None
    max: float | None = None
    value: float | str | list = None
    result: bool = None


@dataclass
class Test:
    id: int
    title: str
    min: float
    max: float
    measure_id: int
    value: float | None
    result: bool
    detailed: list[Detailed] | None


@dataclass
class Report:
    aup: str
    okso: str
    faculty: str
    program: str
    profile: str
    education_form: str
    check_date: str
    result: bool
    tests: list[Test]


class DataclassJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)
