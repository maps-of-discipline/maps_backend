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
        13: OptionalDisciplinesCheck,
        14: ClassroomClassesCheck,
        15: WorkloadControlCheck
    }

    @method_time
    def __init__(self, db_instance: SQLAlchemy):
        self.db = db_instance
        self.aup: AupInfo | None = None
        self.creator = ExcelCreator(path='checker/excel/reports(temporary)/')
        value = {el.id: el.title for el in self.db.session.query(D_Period).all()}
        self.creator.period_id_to_title = value

    @method_time
    def _get_report(self, aup: str, hide_title=False, hide_detailed=False) -> Report:
        self.aup = db.session.query(AupInfo).filter_by(num_aup=aup).one()
        print(f"[_get_report] {aup=}")
        report = Report(
            aup=self.aup.num_aup,
            **self._get_header_data(),
            result=False,
            tests=[]
        )

        if len(self.aup.rule_associations) == 0:
            aup_rule_associations = []
            for key, value in self.__test_dict.items():
                test = value(self.db, self.aup)
                aup_rule_associations.append(test.default_rule_association(key))

            aup_rule_associations = list(filter(lambda x: x is not None, aup_rule_associations))

            self.db.session.add_all(aup_rule_associations)
            self.db.session.commit()

        for association in self.aup.rule_associations:
            test = self.__test_dict[association.rule_id](self.db, self.aup)
            test.fetch_test(association)
            test_result = test.assert_test()
            if hide_title == True and test_result.result == True:
                continue
            report.tests.append(test_result)
            if hide_detailed == True and test_result.detailed is not None :
                index = 0
                while index < len(test_result.detailed):
                    value = test_result.detailed[index]
                    if value.result==True:
                        test_result.detailed.pop(index)
                    else:
                        index+=1
                
             
                report.tests.append(test_result)

        report.result = all([el.result for el in report.tests])
        return report
    
    def _remove_positive_detailed(self, detailed: list[Detailed] | None) -> list[Detailed] | None:
        if detailed is None:
            return None
        return [d for d in detailed if not d.result]

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

        return {
            "okso": okso[0],
            "program": program,
            "profile": profile,
            "faculty": faculty,
            "education_form": form,
            "check_date": date
        }
