import json
from models import *
from .base_checker import BaseChecker
from .data_classes import DataclassJSONEncoder
from .excel import ExcelCreator
from .utils import method_time


class AupChecker(BaseChecker):

    def create_excel(self, aup: str, folder: str = '') -> str:
        report = self._get_report(aup)
        return self.creator.save_report(report, folder)

    def get_json_report(self, aup: str) -> str:
        return json.dumps(self._get_report(aup), cls=DataclassJSONEncoder, ensure_ascii=False)

    def get_json_reports(self, aups: list[str]) -> str:
        return json.dumps([self._get_report(el) for el in aups])

    @method_time
    def get_json_reports_by_okso(self, okso: str) -> str:
        query = (
            self.db.session.query(
                RealizedOkso.id,
                AupInfo.id_aup,
                AupInfo.num_aup
            )
            .join(NameOP, RealizedOkso.program_code == NameOP.program_code)
            .join(AupInfo, NameOP.id_spec == AupInfo.id_spec)
            .filter(NameOP.program_code == okso)
        )

        return json.dumps([self._get_report(el[2]) for el in query.all()], cls=DataclassJSONEncoder,
                          ensure_ascii=False)

    def make_excel_reports_by_okso(self, okso: str):
        query = (
            self.db.session.query(
                RealizedOkso.id,
                AupInfo.id_aup,
                AupInfo.num_aup
            )
            .join(NameOP, RealizedOkso.program_code == NameOP.program_code)
            .join(AupInfo, NameOP.id_spec == AupInfo.id_spec)
            .filter(NameOP.program_code == okso)
        )

        return json.dumps([self.create_excel(el[2], f'{okso}/') for el in query.all()], ensure_ascii=False)
