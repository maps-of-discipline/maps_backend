history_filter = {
    'accept': {
        'discipline': [
            'история рос'
        ]
    },
    'decline': {
        'discipline': ["всео"]
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

digital_literacy = {
        'accept': {
            'discipline': [
                'грамот',
            ]
        },
        'decline': {},
    }

elective_disciplines_in_physical_culture_and_sports = {
        'accept': {
            'discipline': [
                'электив',
            ]
        },
        'decline': {
            'discipline': ['курсы']
        },
    }

electrical_engineering_and_electronics = _filter = {
       'accept': {
           'discipline': [
            'электротехника и э'
         ]
       },
        'decline': {
            'discipline': ['строит']
        }
    }

business_communications = {
       'accept': {
           'discipline': [
            'деловые к'
         ]
       },
        'decline': {
            'discipline': ["практ"]
        }
    }

linear_algebra = {
       'accept': {
           'discipline': [
            'линейн'
         ]
       },
        'decline': {
            'discipline': [
                ' и ',
                '/'
            ]
        }
    }

mathematical_analysis = {
       'accept': {
           'discipline': [
            'матический анали'
         ]
       },
        'decline': {
            'discipline': [

            ]
        }
    }

physics = {
       'accept': {
           'discipline': [
            'физика'
         ]
       },
        'decline': {
            'discipline': [
                ' '
            ]
        }
    }

fundamentals_of_military_training = {
       'accept': {
           'discipline': [
            'военной'
         ]
       },
        'decline': {
            'discipline': [

            ]
        }
    }

marching_drill = {
       'accept': {
           'discipline': [
            'строев'
         ]
       },
        'decline': {
            'discipline': [

            ]
        }
    }

introduction_to_project_activity = {
       'accept': {
           'discipline': [
            'введение в прое'
         ]
       },
        'decline': {
            'discipline': [

            ]
        }
    }

project_management = {
       'accept': {
           'discipline': [
            'ние проектами'
         ]
       },
        'decline': {
            'discipline': [
                'строит',
                'разра',
                'гибк',
            ]
        }
    }

fundamentals_of_technological_entrepreneurship = {
       'accept': {
           'discipline': [
            'технологического предпри'
         ]
       },
        'decline': {
            'discipline': [
            ]
        }
    }

physical_education_and_sports = {
        'accept': {
            'discipline': ['физическая культ']
        },
        'decline': {}

    }

discipline_variations = {
        'Философия': philosopy_filter,
        'История России': history_filter,
        'Иностранный язык': foreign_language_filter,
        'Безопасность жизнедеятельности': bjd_filter,
        'Цифровая грамотность': digital_literacy,
        'Элективные дисциплины по физической культуре и спорту': elective_disciplines_in_physical_culture_and_sports,
        'Электротехника и электроника': electrical_engineering_and_electronics,
        'Деловые коммуникации': business_communications,
        'Линейная алгебра': linear_algebra,
        'Математический анализ': mathematical_analysis,
        'Физика': physics,
        'Основы военной подготовки': fundamentals_of_military_training,
        'Строевая подготовка': marching_drill,
        'Введение в проектную деятельность': introduction_to_project_activity,
        'Управление проектами': project_management,
        'Основы технологического предпринимательства': fundamentals_of_technological_entrepreneurship,
        'Физическая культура и спорт': physical_education_and_sports,
    }
