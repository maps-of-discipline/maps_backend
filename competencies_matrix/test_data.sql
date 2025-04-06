-- Предположим, мы тестируем матрицу для АУП с id_aup = 101 (этот ID должен существовать в вашей таблице tbl_aup из "Карт Дисциплин").

-- Вставляем базовые типы компетенций (если еще не сделано)
INSERT IGNORE INTO competencies_competency_type (id, code, name) VALUES
(1, 'УК', 'Универсальная'),
(2, 'ОПК', 'Общепрофессиональная'),
(3, 'ПК', 'Профессиональная');

-- Вставляем ФГОС для 09.03.01 Бакалавриат (пример)
INSERT IGNORE INTO competencies_fgos_vo (id, number, date, direction_code, direction_name, education_level, generation) VALUES
(1, '929', '2017-09-19', '09.03.01', 'Информатика и вычислительная техника', 'бакалавриат', '3++');

-- Вставляем Образовательную программу (пример)
INSERT IGNORE INTO competencies_educational_program (id, fgos_vo_id, name, code, profile, qualification, form_of_education, enrollment_year) VALUES
(1, 1, 'Веб-технологии (09.03.01)', '09.03.01', 'Веб-технологии', 'Бакалавр', 'очная', 2024);

-- Связываем ОП с АУП (id_aup=101 должен существовать в tbl_aup)
INSERT IGNORE INTO competencies_educational_program_aup (educational_program_id, aup_id, is_primary) VALUES
(1, 101, TRUE);

-- Вставляем примеры компетенций (УК-1, ОПК-1, ПК-1)
-- TODO: Добавьте поле fgos_vo_id в таблицу competencies! Пока вставляем NULL.
INSERT IGNORE INTO competencies_competency (id, competency_type_id, fgos_vo_id, code, name) VALUES
(1, 1, NULL, 'УК-1', 'Способен осуществлять поиск, критический анализ и синтез информации...'),
(2, 2, NULL, 'ОПК-1', 'Способен применять естественнонаучные и общеинженерные знания...'),
(3, 3, NULL, 'ПК-1', 'Способен выполнять работы по созданию (модификации) и сопровождению ИС...');

-- Вставляем примеры индикаторов (по одному для каждой компетенции)
INSERT IGNORE INTO competencies_indicator (id, competency_id, code, formulation, source_description) VALUES
(10, 1, 'ИУК-1.1', 'Анализирует задачу, выделяя ее базовые составляющие', 'Распоряжение 505-Р'),
(11, 2, 'ИОПК-1.1', 'Знает основы высшей математики...', 'ФГОС ВО 09.03.01'),
(12, 3, 'ИПК-1.1', 'Знает: методологию и технологии проектирования ИС...', 'ПС 06.015 / Опыт');

-- Вставляем пару дисциплин в справочник (если их нет)
INSERT IGNORE INTO spr_discipline (id, title) VALUES
(1001, 'Основы программирования'),
(1002, 'Базы данных');

-- Вставляем данные для АУП 101 (эти ID должны быть уникальны для aup_data)
-- Предположим, что aup_data.id = 501 и 502
INSERT IGNORE INTO aup_data (id, id_aup, id_discipline, semester, zet, total_hours, control_type) VALUES
(501, 101, 1001, 1, 4, 144, 'Экзамен'), -- Основы прог., 1 семестр
(502, 101, 1002, 1, 3, 108, 'Зачет');   -- Базы данных, 1 семестр

-- Вставляем ОДНУ тестовую связь в матрицу
-- Связываем "Основы программирования" (aup_data_id=501) с индикатором "ИОПК-1.1" (indicator_id=11)
INSERT IGNORE INTO competencies_matrix (aup_data_id, indicator_id, is_manual) VALUES
(501, 11, TRUE);