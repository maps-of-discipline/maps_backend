from models import *
from .base_test import BaseTest
from ..data_classes import Detailed, Test
from ..utils import match_element

history_filter = {
    'accept': {
        'discipline': [
            'история'
        ]
    },
    'decline': {
        'discipline': []
    }
}

philosopy_filter = {
    'accept': {
        'discipline': [
            'философ'
        ],
        'id_type_record': [1, 2]
    },
    'decline': {}
}

foreign_language_filter = {
    'accept': {
        'discipline': [
            'й язык',
            'fore'
        ],

        'id_type_record': [1, 2]
    },
    'decline': {
        'discipline': [
            'усский',
        ]
    }
}

bjd_filter = {
    'accept': {
        'discipline': [
            # 'безопас',
            'военн',
            'ость жизнед'
        ]
    },
    'decline': {
        'discipline': []
    }
}


class CompulsoryDisciplinesCheck(BaseTest):
    discipline_variations = {
        'Философия': philosopy_filter,
        'История России': history_filter,
        'Иностранный язык': history_filter,
        'Безопасность жизнедеятельности': bjd_filter
    }

    def assert_test(self) -> Test:

        program_code = self.aup_info.name_op.program_code
        realized_okso: RealizedOkso = RealizedOkso.query.filter_by(program_code=program_code).one()
        fgos: SprFgosVo = realized_okso.fgos_vo[0]

        compulsory_disciplines = [[el.title, False] for el in fgos.compulsory_disciplines]

        for el in self.data_filter.filtered():
            for cd in compulsory_disciplines:
                filter_ = self.discipline_variations.get(cd[0], None)

                if cd[0] in el.discipline or (filter_ and match_element(el, filter_)):
                    cd[1] = True
                    cd.append(el.discipline)

        result = True
        self.report.detailed = []
        for discipline in compulsory_disciplines:
            result = result and discipline[1]
            self.report.detailed.append(
                Detailed(
                    discipline=discipline[0],
                    result=discipline[1],
                    value=discipline[2]
                ))
        self.report.result = result
        return self.report

    def default_rule_association(self, rule_id: int) -> AupInfoHasRuleTable | None:
        program_code = self.aup_info.name_op.program_code
        realized_okso: RealizedOkso = RealizedOkso.query.filter_by(program_code=program_code).one()

        if len(realized_okso.fgos_vo) == 0:
            return None

        fgos: SprFgosVo = realized_okso.fgos_vo[0]

        compulsory_disciplines = [[el.title, False] for el in fgos.compulsory_disciplines]

        if len(compulsory_disciplines) == 0:
            return None

        return AupInfoHasRuleTable(
            rule_id=rule_id,
            aup_info_id=self.aup_info.id_aup,
            min=None,
            max=None,
            ed_izmereniya_id=None
        )
