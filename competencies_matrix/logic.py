# competencies_matrix/logic.py
from maps.models import db, AupData, SprDiscipline, TblAup # Импорт из основного модуля
from .models import ( # Импорт моделей нашего модуля
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramPs,
    CompetencyType, LaborFunction # и т.д.
)
# from .parsers import parse_html_to_structured_data # Импорт функции парсера
# from .nlp_service import suggest_links_nlp, suggest_ipk_nlp # Заглушки для NLP

def get_educational_programs_list():
    """Возвращает список всех ОП."""
    return EducationalProgram.query.order_by(EducationalProgram.name).all()

def get_program_details(program_id):
    """Возвращает детали ОП, включая ФГОС, АУП, ПС."""
    program = EducationalProgram.query.get(program_id)
    if not program:
        return None

    # Используем SQLAlchemy relationships для получения связанных данных
    details = program.to_dict(rules=[
        '-selected_ps_assoc.educational_program', # Убираем обратную ссылку
        '-aup_assoc.educational_program',
        '-fgos.educational_programs'
    ])

    # Добавляем списки ID и названий для удобства фронтенда
    details['fgos_details'] = program.fgos.to_dict(rules=['-educational_programs','-recommended_ps_assoc']) if program.fgos else None
    details['aup_list'] = [assoc.aup.to_dict() for assoc in program.aup_assoc if assoc.aup]
    details['selected_ps_list'] = [assoc.prof_standard.to_dict(only=('id', 'code', 'name')) for assoc in program.selected_ps_assoc if assoc.prof_standard]

    # Получаем рекомендованные ПС для связанного ФГОС
    if program.fgos:
         recommended_ps_ids = {assoc.prof_standard_id for assoc in program.fgos.recommended_ps_assoc}
         recommended_ps = ProfStandard.query.filter(ProfStandard.id.in_(recommended_ps_ids)).all()
         details['recommended_ps_list'] = [ps.to_dict(only=('id', 'code', 'name')) for ps in recommended_ps]
    else:
         details['recommended_ps_list'] = []


    return details

def get_matrix_for_aup(aup_id):
    """
    Собирает все данные для отображения матрицы компетенций для АУП:
    - Информацию об АУП
    - Список дисциплин этого АУП (из AupData)
    - Список всех компетенций и их ИДК, релевантных для ОП этого АУП
    - Существующие связи из CompetencyMatrix
    - Опционально: Предложения от NLP
    """
    aup_info = TblAup.query.get(aup_id)
    if not aup_info:
        return None

    # Находим ОП, связанные с этим АУП (может быть несколько, берем первую?)
    # TODO: Уточнить логику, если АУП может быть в нескольких ОП
    program_assoc = EducationalProgramAup.query.filter_by(aup_id=aup_id).first()
    if not program_assoc:
        print(f"Предупреждение: АУП {aup_id} не связан ни с одной ОП")
        # Можно либо вернуть ошибку, либо попытаться найти компетенции по ФГОС АУПа, если он там есть
        return None # Пока возвращаем None
    program = program_assoc.educational_program

    # 1. Получаем дисциплины АУП из AupData
    aup_data_entries = AupData.query.filter_by(aup_id=aup_id).join(SprDiscipline).order_by(AupData.semester, SprDiscipline.title).all()
    disciplines_list = [
        {
            "aup_data_id": entry.id, # ID из aup_data, нужен для связи в матрице
            "discipline_id": entry.id_discipline,
            "title": entry.unique_discipline.title,
            "semester": entry.semester
            # Можно добавить ZET, часы и т.д.
        } for entry in aup_data_entries
    ]

    # 2. Получаем все компетенции (УК, ОПК, ПК) и их ИДК, связанные с этой ОП
    # УК/ОПК берем из ФГОС программы
    competencies = []
    if program.fgos:
        fgos_competencies = Competency.query.join(CompetencyType).filter(
            Competency.fgos_vo_id == program.fgos_vo_id, # Нужно добавить fgos_vo_id в Competency!
            CompetencyType.code.in_(['УК', 'ОПК'])
        ).options(db.joinedload(Competency.indicators)).all()
        competencies.extend(fgos_competencies)

    # ПК берем те, что связаны с выбранными для ОП профстандартами
    # TODO: Уточнить, как ПК связаны с ОП (возможно, через based_on_labor_function_id и EducationalProgramPs?)
    # Пока для примера возьмем все ПК
    pk_competencies = Competency.query.join(CompetencyType).filter(
        CompetencyType.code == 'ПК'
        # TODO: Добавить фильтр по program_id или связанным ПС
    ).options(db.joinedload(Competency.indicators)).all()
    competencies.extend(pk_competencies)

    # Форматируем компетенции и ИДК
    competencies_data = []
    for comp in sorted(competencies, key=lambda c: (c.competency_type.code, c.code)):
        comp_dict = comp.to_dict(rules=['-indicators']) # Сериализуем без индикаторов сначала
        comp_dict['type_code'] = comp.competency_type.code
        comp_dict['indicators'] = [
            ind.to_dict(rules=['-competency']) # Сериализуем индикаторы без обратной ссылки
            for ind in sorted(comp.indicators, key=lambda i: i.code)
        ]
        competencies_data.append(comp_dict)


    # 3. Получаем существующие связи в матрице для этого АУП
    aup_data_ids = [d['aup_data_id'] for d in disciplines_list]
    existing_links_db = CompetencyMatrix.query.filter(
        CompetencyMatrix.aup_data_id.in_(aup_data_ids)
    ).all()
    existing_links_data = [link.to_dict(only=('aup_data_id', 'indicator_id')) for link in existing_links_db]

    # 4. Получаем предложения от NLP (заглушка)
    suggestions = [] # suggest_links_nlp(disciplines_list, competencies_data)

    return {
        "aup_info": aup_info.to_dict(), # Используем модель из maps.models
        "disciplines": disciplines_list,
        "competencies": competencies_data,
        "links": existing_links_data,
        "suggestions": suggestions
    }

def update_matrix_link(aup_data_id, indicator_id, create=True):
    """Создает или удаляет связь в таблице CompetencyMatrix."""
    # Проверяем существование записей
    aup_data_exists = db.session.query(AupData.id).filter_by(id=aup_data_id).first() is not None
    indicator_exists = db.session.query(Indicator.id).filter_by(id=indicator_id).first() is not None

    if not aup_data_exists or not indicator_exists:
        return False # Не найдены связанные сущности

    if create:
        # Проверяем, нет ли уже такой связи
        existing = CompetencyMatrix.query.filter_by(aup_data_id=aup_data_id, indicator_id=indicator_id).first()
        if not existing:
            link = CompetencyMatrix(aup_data_id=aup_data_id, indicator_id=indicator_id)
            db.session.add(link)
            db.session.commit()
            return True
        return True # Связь уже есть
    else: # delete
        link = CompetencyMatrix.query.filter_by(aup_data_id=aup_data_id, indicator_id=indicator_id).first()
        if link:
            db.session.delete(link)
            db.session.commit()
            return True
        return True # Связи и так не было

def create_competency(data):
     """Создает новую компетенцию."""
     # TODO: Добавить валидацию и получение competency_type_id
     comp_type = CompetencyType.query.filter_by(code=data.get('type_code', 'ПК')).first()
     if not comp_type:
         return None # Неверный тип

     competency = Competency(
         competency_type_id=comp_type.id,
         code=data['code'],
         name=data['name'],
         based_on_labor_function_id=data.get('based_on_tf_id') # Может быть None
         # TODO: Добавить связь с ФГОС, если это УК/ОПК
     )
     db.session.add(competency)
     db.session.commit()
     return competency


def parse_prof_standard_file(html_content_bytes):
    """
    Обертка для вызова парсера и сохранения результата в БД.
    Возвращает dict с результатом {"success": True/False, ...}
    """
    from .parsers import html_to_markdown_parser_enhanced, detect_encoding

    # 1. Определяем кодировку
    # Записываем во временный файл или используем BytesIO, если парсер поддерживает
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as temp_file:
        temp_file.write(html_content_bytes)
        temp_filepath = temp_file.name

    try:
        encoding = detect_encoding(temp_filepath) or 'windows-1251' # Запасной вариант

        # 2. Парсим в Markdown (пока только Markdown)
        # TODO: Адаптировать парсер, чтобы он возвращал СТРУКТУРУ данных, а не только Markdown
        markdown_text = html_to_markdown_parser_enhanced(
            temp_filepath,
            output_filepath=None, # Возвращаем текст, не пишем в файл
            default_encoding=encoding
        )

        if not markdown_text:
             return {"success": False, "error": "Парсер не вернул текст"}

        # 3. Извлекаем код и название ПС из Markdown (или лучше из HTML до конвертации)
        # TODO: Улучшить извлечение метаданных
        code_match = re.search(r'###\s+(\d{2}\.\d{3})', markdown_text) # Примерный поиск кода
        name_match = re.search(r'ПРОФЕССИОНАЛЬНЫЙ СТАНДАРТ\s*\n*(.*?)\n', markdown_text, re.IGNORECASE)
        prof_standard_code = code_match.group(1) if code_match else "UNKNOWN"
        prof_standard_name = name_match.group(1).strip() if name_match else "Название не найдено"

        # 4. Сохраняем/Обновляем ПС в БД
        prof_standard = ProfStandard.query.filter_by(code=prof_standard_code).first()
        if not prof_standard:
            prof_standard = ProfStandard(code=prof_standard_code, name=prof_standard_name, parsed_content=markdown_text)
            db.session.add(prof_standard)
        else:
            prof_standard.name = prof_standard_name # Обновляем имя и контент
            prof_standard.parsed_content = markdown_text
            prof_standard.updated_at = datetime.datetime.utcnow()

        # TODO: Реализовать парсинг ОТФ, ТФ, действий, знаний, умений из Markdown/HTML
        # и сохранение их в связанные таблицы

        db.session.commit()

        return {
            "success": True,
            "prof_standard_id": prof_standard.id,
            "code": prof_standard.code,
            "name": prof_standard.name,
            "markdown": markdown_text
        }

    except Exception as e:
        db.session.rollback() # Откатываем транзакцию в случае ошибки
        return {"success": False, "error": f"Ошибка при парсинге или сохранении: {str(e)}"}
    finally:
        # Удаляем временный файл
        if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
            os.remove(temp_filepath)

# ... другие функции бизнес-логики ...