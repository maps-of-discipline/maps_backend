from models import *
from .data_classes import *
from .excel import ExcelCreator
from .tests import *
from .utils import method_time


# TODO: проверить аупы, возможно считаются не правильно:
#     - 000016048
#     - 000019349
#


class BaseChecker:
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

    @method_time
    def __init__(self, db_instance: SQLAlchemy):
        self.db = db_instance
        self.aup = None
        self.creator = ExcelCreator(path='checker/excel/reports(temporary)/')
        value = {el.id: el.title for el in self.db.session.query(D_Period).all()}
        self.creator.period_id_to_title = value

    @method_time
    def _get_report(self, aup: str) -> Report:
        self.aup = db.session.query(AupInfo).filter_by(num_aup=aup).one()

        realized_okso, header = self._get_header_data()

        report = Report(
            aup=self.aup.num_aup,
            **header,
            result=False,
            tests=[]
        )

        for association in realized_okso.rule_associations:
            test = self.__test_dict[association.rule_id](self.db)
            test.fetch_test(association)

            if test.compilable_with_aup(self.aup):
                report.tests.append(test.assert_test(self.aup))

        report.result = all([el.result for el in report.tests])

        return report

    @method_time
    def _get_header_data(self):
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


