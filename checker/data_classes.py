import dataclasses
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class Test:
    id: int
    title: str
    result: bool
    headers: list[str] | None
    data: list[list[Any]]

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
