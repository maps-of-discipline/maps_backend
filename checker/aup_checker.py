from models import *
from .excel import ExcelCreator
from .tests import *
from .data_classes import *

import json


# TODO: проверить аупы, возможно считаются не правильно:
#     - 000016048
#     - 000019349
#


class AupChecker:
    # index in db: associated python test
    __test_dict = {
        1: TotalZetTest,
        2: ZetCheckByYear,
        3: ZetCheckByFirstBlock,
        4: ZetCheckBySecondBlock,
        5: ZetCheckByThirdBlock,
        6: PEAmountInFirstBlockTest,
        7: OptionalPEAmount,
        11: MinDisciplineZet,
        12: CompulsoryDisciplinesCheck,
    }

    def __init__(self, aup_object: AupInfo, db_instance: SQLAlchemy):
        self.db = db_instance
        self.aup = aup_object
        self.report = None

    def get_report(self, ) -> str:
        if self.report:
            return self.report

        realized_okso, header = self.__get_header_data()

        report = Report(
            aup=self.aup.num_aup,
            **header,
            result=False,
            tests=[]
        )

        for el in realized_okso.rule_associations:
            test = self.__test_dict[el.rule_id](self.db)
            test.fetch_test(el)
            report.tests.append(test.assert_test(self.aup))

        report.result = all([el.result for el in report.tests])

        self.report = json.dumps(report, cls=DataclassJSONEncoder, ensure_ascii=False)
        return self.report

    def __get_header_data(self):
        program_code = self.aup.name_op.program_code
        realized_okso: RealizedOkso = RealizedOkso.query.filter_by(program_code=program_code).one()

        okso = realized_okso.program_code,

        program = realized_okso.okco.name_okco

        profile = self.aup.name_op.name_spec

        faculty = self.aup.faculty.name_faculty

        form = self.aup.form.form

        from datetime import datetime
        date = datetime.today().strftime('%Y-%m-%d')

        return realized_okso, {
            "okso": okso[0],
            "program": program, "profile": profile,
            "faculty": faculty,
            "education_form": form,
            "check_date": date
        }

    def create_excel(self, ) -> None:
        if self.report is None:
            return

        creator = ExcelCreator(path='checker/excel/reports(temporary)/', report=self.report)
        value = {el.id: el.title for el in self.db.session.query(D_Period).all()}
        print(value)
        creator.period_id_to_title = value
        creator.save_report()

