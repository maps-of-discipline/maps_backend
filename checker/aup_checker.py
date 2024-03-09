import json
from datetime import datetime
# from PD/ models import SQLAlchemy

from models import *
from .base_checker import BaseChecker
from .data_classes import DataclassJSONEncoder
from .utils import method_time


class AupChecker(BaseChecker):
    def __init__(self, db_instance: SQLAlchemy, hide_title=False, hide_detailed=False):
        self.hide_detailed = hide_detailed
        self.hide_title = hide_title
        super().__init__(db_instance)

    def get_json_report(self, aup: str) -> str:
        return json.dumps(self._get_report(aup, self.hide_title, self.hide_detailed), cls=DataclassJSONEncoder,
                          ensure_ascii=False)

    def get_json_reports(self, aups: list[str]) -> str:
        return json.dumps([self._get_report(el, self.hide_title, self.hide_detailed) for el in aups],
                          cls=DataclassJSONEncoder, ensure_ascii=False)

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

        return json.dumps([self._get_report(el[2], self.hide_title, self.hide_detailed) for el in query.all()],
                          cls=DataclassJSONEncoder,
                          ensure_ascii=False)

