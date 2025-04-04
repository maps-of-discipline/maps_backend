# competencies_matrix/logic.py
from maps.models import db, AupData, SprDiscipline, AupInfo  # Импортирование существующих БД
from .models import (
    EducationalProgram, Competency, Indicator, CompetencyMatrix,
    ProfStandard, FgosVo, FgosRecommendedPs, EducationalProgramPs, EducationalProgramAup,
    CompetencyType, LaborFunction, GeneralizedLaborFunction, LaborAction, RequiredSkill, RequiredKnowledge, IndicatorPsLink
)
import re
import os
import datetime
import tempfile
from typing import Dict, List, Any, Optional, Tuple, Union
from .parsers import parse_uploaded_prof_standard  # Импортируем функцию из parsers.py

def get_educational_programs_list():
    """Возвращает список всех ОП."""
    return EducationalProgram.query.all()

def get_program_details(program_id):
    """Возвращает детали ОП, включая ФГОС, АУП, ПС."""
    program = EducationalProgram.query.get(program_id)
    if not program:
        return None
    
    # Получаем связанные данные
    program_data = program.to_dict()
    
    # Добавляем информацию о ФГОС
    if program.fgos_vo_id:
        program_data['fgos'] = program.fgos.to_dict()
    
    # Добавляем информацию о выбранных ПС
    program_data['selected_ps'] = []
    for link in EducationalProgramPs.query.filter_by(educational_program_id=program_id).all():
        ps_data = link.prof_standard.to_dict()
        ps_data['link_id'] = link.id
        program_data['selected_ps'].append(ps_data)
    
    # Добавляем информацию об АУП
    program_data['aups'] = []
    for link in EducationalProgramAup.query.filter_by(educational_program_id=program_id).all():
        aup_info = AupInfo.query.get(link.aup_id)
        if aup_info:
            aup_data = aup_info.to_dict()
            aup_data['link_id'] = link.id
            program_data['aups'].append(aup_data)
    
    return program_data

def get_matrix_for_aup(aup_id):
    """
    Возвращает данные для матрицы компетенций по указанному АУП.
    Включает:
    - Информацию об АУП
    - Список дисциплин
    - Список компетенций и их индикаторов
    - Существующие связи дисциплин с индикаторами
    - (Опционально) Предложения по связям
    """
    # 0. Получаем инфо об АУП
    aup_info = AupInfo.query.get(aup_id)
    if not aup_info:
        return None
    
    # Получаем ОП по этому АУП
    aup_program_link = EducationalProgramAup.query.filter_by(aup_id=aup_id).first()
    if not aup_program_link:
        return None
    
    program = EducationalProgram.query.get(aup_program_link.educational_program_id)
    
    # 1. Получаем список дисциплин для этого АУП
    aup_data_entries = AupData.query.filter_by(id_aup=aup_id).all()
    disciplines_list = [
        {
            "aup_data_id": entry.id, # ID из aup_data, нужен для связи в матрице
            "discipline_id": entry.id_discipline,
            "title": entry.unique_discipline.title if hasattr(entry, 'unique_discipline') else f"Дисциплина ID:{entry.id_discipline}",
            "semester": entry.semester
            # Можно добавить ZET, часы и т.д.
        } for entry in aup_data_entries if hasattr(entry, 'id_discipline')
    ]

    # 2. Получаем все компетенции (УК, ОПК, ПК) и их ИДК, связанные с этой ОП
    # УК/ОПК берем из ФГОС программы
    competencies = []
    if program and program.fgos_vo_id:
        fgos_competencies = Competency.query.join(CompetencyType).filter(
            Competency.fgos_vo_id == program.fgos_vo_id,
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
        comp_dict['type_code'] = comp.competency_type.code if hasattr(comp, 'competency_type') else "УК"
        comp_dict['indicators'] = [
            ind.to_dict(rules=['-competency']) # Сериализуем индикаторы без обратной ссылки
            for ind in sorted(comp.indicators, key=lambda i: i.code) if hasattr(comp, 'indicators')
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

def update_matrix_link(aup_data_id: int, indicator_id: int, create: bool = True) -> bool:
    """
    Создает или удаляет связь между дисциплиной (AupData) и индикатором компетенции.
    
    Args:
        aup_data_id: ID дисциплины в рамках АУП (из таблицы aup_data)
        indicator_id: ID индикатора компетенции
        create: True - создать связь, False - удалить связь
        
    Returns:
        bool: True если операция успешна, False если нет
    """
    # Проверяем существование дисциплины и индикатора
    aup_data_entry = AupData.query.get(aup_data_id)
    indicator = Indicator.query.get(indicator_id)
    
    if not aup_data_entry or not indicator:
        return False
    
    # Проверяем существование записи в матрице
    existing_link = CompetencyMatrix.query.filter_by(
        aup_data_id=aup_data_id,
        indicator_id=indicator_id
    ).first()
    
    if create:
        # Создаем связь, если ее еще нет
        if not existing_link:
            new_link = CompetencyMatrix(
                aup_data_id=aup_data_id,
                indicator_id=indicator_id,
                is_manual=True
            )
            db.session.add(new_link)
            db.session.commit()
        return True
    else:
        # Удаляем связь, если она существует
        if existing_link:
            db.session.delete(existing_link)
            db.session.commit()
        return True

def create_competency(data: Dict[str, Any]) -> Optional[Competency]:
    """
    Создает новую компетенцию (обычно ПК на основе ТФ).
    
    Args:
        data: Словарь с данными компетенции
        
    Returns:
        Competency: Созданная компетенция или None в случае ошибки
    """
    try:
        # Находим тип компетенции по коду
        comp_type = CompetencyType.query.filter_by(code=data['type_code']).first()
        if not comp_type:
            return None
        
        # Создаем компетенцию
        new_competency = Competency(
            competency_type_id=comp_type.id,
            code=data['code'],
            name=data['name'],
            description=data.get('description', None)
        )
        
        # Если это ПК на основе ТФ - добавляем связь
        if 'based_on_tf_id' in data and data['based_on_tf_id']:
            new_competency.based_on_labor_function_id = data['based_on_tf_id']
        
        # Если указан ФГОС - добавляем связь
        if 'fgos_vo_id' in data and data['fgos_vo_id']:
            new_competency.fgos_vo_id = data['fgos_vo_id']
        
        db.session.add(new_competency)
        db.session.commit()
        return new_competency
    except Exception as e:
        print(f"Ошибка при создании компетенции: {str(e)}")
        db.session.rollback()
        return None

def parse_prof_standard_file(file_data: bytes, filename: str) -> Optional[Dict[str, Any]]:
    """
    Парсинг файла профстандарта с использованием функции из parsers.py.
    
    Args:
        file_data: Байты загруженного файла
        filename: Имя файла
    
    Returns:
        Dict: Данные профстандарта или None в случае ошибки
    """
    try:
        # Используем функцию из модуля parsers
        return parse_uploaded_prof_standard(file_data, filename)
    except Exception as e:
        print(f"Ошибка при парсинге профстандарта: {str(e)}")
        return None

# Вспомогательные функции (для будущей имплементации)

def create_indicator(data: Dict[str, Any]) -> Optional[Indicator]:
    """
    Создает новый индикатор достижения компетенции (ИДК).
    
    Args:
        data: Словарь с данными индикатора
        
    Returns:
        Indicator: Созданный индикатор или None в случае ошибки
    """
    try:
        # Проверяем, что компетенция существует
        competency = Competency.query.get(data['competency_id'])
        if not competency:
            return None
        
        # Создаем индикатор
        new_indicator = Indicator(
            competency_id=data['competency_id'],
            code=data['code'],
            formulation=data['formulation'],
            source=data.get('source', None)
        )
        
        db.session.add(new_indicator)
        db.session.commit()
        
        # Если указаны связи с ТФ - добавляем их
        if 'labor_function_ids' in data and data['labor_function_ids']:
            for tf_id in data['labor_function_ids']:
                link = IndicatorPsLink(
                    indicator_id=new_indicator.id,
                    labor_function_id=tf_id,
                    is_manual=True
                )
                db.session.add(link)
            db.session.commit()
        
        return new_indicator
    except Exception as e:
        print(f"Ошибка при создании индикатора: {str(e)}")
        db.session.rollback()
        return None

def suggest_links_nlp(disciplines: List[Dict], indicators: List[Dict]) -> List[Dict]:
    """
    Получает предложения по связям "Дисциплина-ИДК" от NLP модуля.
    Это заглушка, которая будет заменена реальным вызовом к NLP.
    
    Args:
        disciplines: Список дисциплин с их данными
        indicators: Список ИДК с их данными
        
    Returns:
        List: Список предложенных связей вида [{'aup_data_id': ..., 'indicator_id': ..., 'score': ...}, ...]
    """
    # Заглушка - в реальности здесь будет вызов к NLP сервису
    # Просто возвращаем пару случайных связей
    import random
    
    if not disciplines or not indicators:
        return []
    
    result = []
    for _ in range(min(3, len(disciplines) * len(indicators))):
        d = random.choice(disciplines)
        i = random.choice(indicators)
        result.append({
            'aup_data_id': d['aup_data_id'],
            'indicator_id': i['id'],
            'score': round(random.random(), 2)
        })
    
    return result
