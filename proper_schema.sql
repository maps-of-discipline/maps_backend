-- Ключевые моменты этой схемы:
-- Централизация вокруг ОП: Таблица educational_programs связывает ФГОС, АУП и выбранные ПС.
-- Детализация ПС: Отдельные таблицы для хранения структуры ПС (ОТФ, ТФ, действия, знания, умения), что упрощает парсинг и запросы.
-- Унифицированные Компетенции/ИДК: Таблицы competencies и indicators хранят все типы, различаясь по competency_type_id. ИДК могут иметь описание источника.
-- Явная связь ИДК-ПС: Таблица indicator_ps_link позволяет точно указать, на каких элементах ПС основан ИДК (важно для ИПК).
-- Матрица через aup_data: Связь в competency_matrix идет через aup_data (дисциплина+семестр в АУП) и indicator_id, обеспечивая максимальную точность привязки.
-- Учет успеваемости: Сохранен с возможностью опциональной привязки оценки к конкретному ИДК (grades.indicator_id).
-- Уровни освоения: Добавлены опциональные таблицы для дескрипторов уровней (если эта функциональность будет реализовываться).
-- Внешние ключи и уникальность: Определены для поддержания целостности данных.

-- Что можно сделать дальше:
-- Заменить типы данных на более специфичные (например, ENUM для статусов). Это нужно сделать после утверждения схемы.
-- Добавить индексы для оптимизации запросов (например, по полям, которые часто используются в WHERE).

-- Настройка новой схемы БД
-- CREATE DATABASE kd_competencies CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Удаление старых таблиц (если нужно начать с чистого листа)
-- ОСТОРОЖНО! Это удалит данные! Раскомментируйте, только если уверены.
/*
SET FOREIGN_KEY_CHECKS = 0; -- Отключаем проверку внешних ключей
DROP TABLE IF EXISTS competency_matrix, educational_program_aup, educational_program_ps,
                 fgos_recommended_ps, educational_programs, fgos_vo,
                 indicator_ps_link, indicator_labor_action, indicator_skill, indicator_knowledge,
                 indicators, competencies, competency_types,
                 indicator_mastery_descriptors, mastery_levels,
                 labor_actions, required_skills, required_knowledge,
                 labor_functions, generalized_labor_functions, prof_standards,
                 topic_indicator, grades, grade_columns, grade_types, topics, rpd,
                 students, study_groups, spr_bells, tbl_aup, aup_data, spr_discipline,
                 user_has_role, roles, tbl_token, tbl_users;
SET FOREIGN_KEY_CHECKS = 1; -- Включаем проверку внешних ключей обратно
*/

-- ======================================================================
-- БЛОК: Образовательные Программы и Стандарты
-- ======================================================================

CREATE TABLE fgos_vo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL COMMENT 'Код направления подготовки (например, 09.03.01)',
    name TEXT NOT NULL COMMENT 'Наименование направления подготовки',
    level VARCHAR(50) NOT NULL COMMENT 'Уровень образования (например, бакалавриат, специалитет, магистратура, дистанционное и др.)',
    approval_order_number VARCHAR(100) COMMENT 'Номер приказа Минобрнауки об утверждении ФГОС',
    approval_order_date DATE COMMENT 'Дата приказа Минобрнауки',
    link TEXT COMMENT 'Ссылка на документ ФГОС (если есть)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `code_level` (code, level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Федеральные государственные образовательные стандарты ВО';

CREATE TABLE educational_programs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(500) NOT NULL COMMENT 'Название образовательной программы (включая профиль)',
    fgos_vo_id INT NOT NULL COMMENT 'Ссылка на ФГОС ВО, на котором основана ОП',
    enrollment_year INT COMMENT 'Год начала набора на ОП',
    learning_form VARCHAR(50) COMMENT 'Форма обучения (например, очная, заочная, дистанционная, смешанная и др.)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (fgos_vo_id) REFERENCES fgos_vo(id) ON DELETE RESTRICT -- Не удалять ФГОС, если есть связанные ОП
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Образовательные программы (ОП)';

CREATE TABLE prof_standards (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL COMMENT 'Код профстандарта (например, 06.001)',
    name TEXT NOT NULL COMMENT 'Наименование профстандарта',
    approval_order_number VARCHAR(100) COMMENT 'Номер приказа Минтруда об утверждении ПС',
    approval_order_date DATE COMMENT 'Дата приказа Минтруда',
    valid_from DATE COMMENT 'Дата начала действия ПС',
    valid_until DATE COMMENT 'Дата окончания действия ПС',
    link TEXT COMMENT 'Ссылка на документ профстандарта (например, classinform)',
    parsed_content MEDIUMTEXT COMMENT 'Содержимое стандарта (например, Markdown) для NLP',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Справочник профессиональных стандартов (ПС)';

CREATE TABLE fgos_recommended_ps (
    fgos_vo_id INT NOT NULL,
    prof_standard_id INT NOT NULL,
    PRIMARY KEY (fgos_vo_id, prof_standard_id),
    FOREIGN KEY (fgos_vo_id) REFERENCES fgos_vo(id) ON DELETE CASCADE,
    FOREIGN KEY (prof_standard_id) REFERENCES prof_standards(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Рекомендованные профстандарты для ФГОС ВО (M:N)';

CREATE TABLE educational_program_ps (
    educational_program_id INT NOT NULL,
    prof_standard_id INT NOT NULL,
    PRIMARY KEY (educational_program_id, prof_standard_id),
    FOREIGN KEY (educational_program_id) REFERENCES educational_programs(id) ON DELETE CASCADE,
    FOREIGN KEY (prof_standard_id) REFERENCES prof_standards(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Профстандарты, выбранные для ОП (M:N)';

-- ======================================================================
-- БЛОК: Структура Профессиональных Стандартов (Детализация)
-- ======================================================================

CREATE TABLE generalized_labor_functions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    prof_standard_id INT NOT NULL,
    code VARCHAR(20) COMMENT 'Код ОТФ',
    name TEXT NOT NULL COMMENT 'Наименование ОТФ',
    qualification_level INT COMMENT 'Уровень квалификации',
    FOREIGN KEY (prof_standard_id) REFERENCES prof_standards(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Обобщенные трудовые функции (ОТФ) из ПС';

CREATE TABLE labor_functions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    generalized_labor_function_id INT NOT NULL,
    code VARCHAR(20) COMMENT 'Код ТФ',
    name TEXT NOT NULL COMMENT 'Наименование ТФ',
    FOREIGN KEY (generalized_labor_function_id) REFERENCES generalized_labor_functions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Трудовые функции (ТФ) из ПС';

CREATE TABLE labor_actions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    labor_function_id INT NOT NULL,
    description TEXT NOT NULL COMMENT 'Описание трудового действия',
    FOREIGN KEY (labor_function_id) REFERENCES labor_functions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Трудовые действия в рамках ТФ';

CREATE TABLE required_skills (
    id INT AUTO_INCREMENT PRIMARY KEY,
    labor_function_id INT NOT NULL,
    description TEXT NOT NULL COMMENT 'Описание необходимого умения',
    FOREIGN KEY (labor_function_id) REFERENCES labor_functions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Необходимые умения для выполнения ТФ';

CREATE TABLE required_knowledge (
    id INT AUTO_INCREMENT PRIMARY KEY,
    labor_function_id INT NOT NULL,
    description TEXT NOT NULL COMMENT 'Описание необходимых знаний',
    FOREIGN KEY (labor_function_id) REFERENCES labor_functions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Необходимые знания для выполнения ТФ';

-- ======================================================================
-- БЛОК: Компетенции и Индикаторы (Унифицированный)
-- ======================================================================

CREATE TABLE competency_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL COMMENT 'Код типа (УК, ОПК, ПК)',
    name VARCHAR(255) NOT NULL COMMENT 'Наименование типа'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Справочник типов компетенций';

INSERT INTO competency_types (code, name) VALUES ('УК', 'Универсальная'), ('ОПК', 'Общепрофессиональная'), ('ПК', 'Профессиональная');

CREATE TABLE competencies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    competency_type_id INT NOT NULL COMMENT 'Ссылка на тип компетенции',
    code VARCHAR(20) NOT NULL COMMENT 'Код компетенции (УК-1, ОПК-3, ПК-2)',
    name TEXT NOT NULL COMMENT 'Формулировка компетенции',
    based_on_labor_function_id INT NULL COMMENT 'Ссылка на ТФ (для ПК)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `type_code` (competency_type_id, code),
    FOREIGN KEY (competency_type_id) REFERENCES competency_types(id),
    FOREIGN KEY (based_on_labor_function_id) REFERENCES labor_functions(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Компетенции (УК, ОПК, ПК)';

CREATE TABLE indicators (
    id INT AUTO_INCREMENT PRIMARY KEY,
    competency_id INT NOT NULL COMMENT 'Ссылка на родительскую компетенцию',
    code VARCHAR(30) NOT NULL COMMENT 'Код индикатора (ИУК-1.1, ИПК-2.3)',
    formulation TEXT NOT NULL COMMENT 'Формулировка индикатора',
    source_description VARCHAR(500) COMMENT 'Источник/основа формулировки (напр., Распоряжение 505-P, ПС 06.001 ТФ A/01.3)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `competency_code` (competency_id, code),
    FOREIGN KEY (competency_id) REFERENCES competencies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Индикаторы достижения компетенций (ИДК, включая ИУК, ИОПК, ИПК)';

CREATE TABLE indicator_ps_link (
    id INT AUTO_INCREMENT PRIMARY KEY, -- Добавлен ID для удобства
    indicator_id INT NOT NULL COMMENT 'Ссылка на ИДК',
    link_type ENUM('labor_action', 'skill', 'knowledge') NOT NULL COMMENT 'Тип связанного элемента ПС',
    element_id INT NOT NULL COMMENT 'ID связанного элемента (из соответствующей таблицы)',
    UNIQUE KEY `indicator_element` (indicator_id, link_type, element_id), -- Убрали ID из ключа
    FOREIGN KEY (indicator_id) REFERENCES indicators(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Связь ИПК с конкретными элементами ПС';

-- ======================================================================
-- БЛОК: Учебный план и Матрица
-- ======================================================================

CREATE TABLE spr_discipline (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(400) NOT NULL UNIQUE COMMENT 'Уникальное название дисциплины'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Центральный справочник дисциплин';

CREATE TABLE tbl_aup (
    id_aup INT AUTO_INCREMENT PRIMARY KEY,
    num_aup VARCHAR(255) NOT NULL UNIQUE COMMENT 'Номер/шифр АУП',
    year_beg INT COMMENT 'Год начала действия АУП',
    year_end INT COMMENT 'Год окончания действия АУП',
    qualification VARCHAR(255) COMMENT 'Квалификация',
    is_actual TINYINT(1) DEFAULT 1 COMMENT 'Признак актуальности АУП',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Академические Учебные Планы (АУП)';

CREATE TABLE educational_program_aup (
    educational_program_id INT NOT NULL,
    aup_id INT NOT NULL,
    PRIMARY KEY (educational_program_id, aup_id),
    FOREIGN KEY (educational_program_id) REFERENCES educational_programs(id) ON DELETE CASCADE,
    FOREIGN KEY (aup_id) REFERENCES tbl_aup(id_aup) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Связь образовательной программы с АУП (M:N)';

CREATE TABLE aup_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    aup_id INT NOT NULL COMMENT 'Ссылка на АУП',
    discipline_id INT NOT NULL COMMENT 'Ссылка на дисциплину из справочника',
    semester INT NOT NULL COMMENT 'Семестр, в котором читается дисциплина',
    zet INT COMMENT 'Трудоемкость в ЗЕТ',
    total_hours INT COMMENT 'Всего часов',
    lecture_hours INT COMMENT 'Часы лекций',
    practice_hours INT COMMENT 'Часы практик',
    lab_hours INT COMMENT 'Часы лабораторных',
    self_study_hours INT COMMENT 'Часы самостоятельной работы',
    control_type VARCHAR(50) COMMENT 'Вид контроля (Экзамен, Зачет, Диф.зачет, КП, КР)',
    FOREIGN KEY (aup_id) REFERENCES tbl_aup(id_aup) ON DELETE CASCADE,
    FOREIGN KEY (discipline_id) REFERENCES spr_discipline(id) ON DELETE RESTRICT,
    UNIQUE KEY `aup_discipline_semester` (aup_id, discipline_id, semester)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Структура АУП: дисциплины, часы, ЗЕТ по семестрам';

CREATE TABLE competency_matrix (
    id INT AUTO_INCREMENT PRIMARY KEY,
    aup_data_id INT NOT NULL COMMENT 'Ссылка на строку в структуре АУП (дисциплина+семестр)',
    indicator_id INT NOT NULL COMMENT 'Ссылка на ИДК',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (aup_data_id) REFERENCES aup_data(id) ON DELETE CASCADE,
    FOREIGN KEY (indicator_id) REFERENCES indicators(id) ON DELETE CASCADE,
    UNIQUE KEY `matrix_entry` (aup_data_id, indicator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Матрица компетенций: связь Дисциплина(АУП)-ИДК';

-- ======================================================================
-- БЛОК: Пользователи, Роли, Токены
-- ======================================================================

CREATE TABLE tbl_users (
    id_user INT AUTO_INCREMENT PRIMARY KEY,
    login VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100) UNIQUE,
    name VARCHAR(200),
    lk_id INT UNIQUE COMMENT 'ID пользователя в Личном Кабинете',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Пользователи системы';

CREATE TABLE roles (
    id_role INT AUTO_INCREMENT PRIMARY KEY,
    name_role VARCHAR(100) UNIQUE NOT NULL COMMENT 'Название роли (admin, teacher, student, methodologist)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Справочник ролей пользователей';

INSERT INTO roles (name_role) VALUES ('admin'), ('teacher'), ('student'), ('methodologist'), ('tutor'); -- Добавим роль тьютора

CREATE TABLE user_has_role (
    user_id INT NOT NULL,
    role_id INT NOT NULL,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES tbl_users(id_user) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id_role) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Связь пользователи-роли (M:N)';

CREATE TABLE tbl_token (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    refresh_token VARCHAR(512) NOT NULL,
    user_agent VARCHAR(256),
    expires_at DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES tbl_users(id_user) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Refresh-токены пользователей';

-- ======================================================================
-- БЛОК: Темы и Оценки (Адаптированный)
-- ======================================================================

CREATE TABLE study_groups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL UNIQUE COMMENT 'Название/шифр группы',
    aup_id INT COMMENT 'Ссылка на АУП, по которому учится группа',
    enrollment_year INT COMMENT 'Год поступления группы',
    FOREIGN KEY (aup_id) REFERENCES tbl_aup(id_aup) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Учебные группы';

CREATE TABLE students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(400) NOT NULL COMMENT 'ФИО студента',
    study_group_id INT,
    lk_id INT UNIQUE COMMENT 'ID студента в ЛК',
    status VARCHAR(50) DEFAULT 'active' COMMENT 'Статус студента (например: active, expelled, academic_leave, graduated и др.)',
    FOREIGN KEY (study_group_id) REFERENCES study_groups(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Студенты';

-- РПД - пока оставим минимальную версию для связи с темами
CREATE TABLE rpd (
    id INT AUTO_INCREMENT PRIMARY KEY,
    aup_id INT NOT NULL COMMENT 'Ссылка на АУП',
    discipline_id INT NOT NULL COMMENT 'Ссылка на дисциплину',
    -- Добавить поля метаданных РПД, если нужно (версия, автор, дата и т.д.)
    FOREIGN KEY (aup_id) REFERENCES tbl_aup(id_aup) ON DELETE CASCADE,
    FOREIGN KEY (discipline_id) REFERENCES spr_discipline(id) ON DELETE CASCADE,
    UNIQUE KEY `rpd_context` (aup_id, discipline_id) -- Одна РПД на дисциплину в АУП (можно усложнить версиями)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Рабочие программы дисциплин (РПД) - Метаданные';

CREATE TABLE topics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rpd_id INT NOT NULL COMMENT 'Ссылка на РПД',
    semester INT NOT NULL COMMENT 'Семестр',
    topic_name VARCHAR(400) NOT NULL COMMENT 'Название темы/контрольной точки',
    lesson_type VARCHAR(50) COMMENT 'Тип занятия/контроля (например: lecture, practice, lab, control, exam, online, other)',
    lesson_date DATETIME COMMENT 'Дата проведения занятия',
    task_description TEXT COMMENT 'Описание задания',
    task_deadline DATETIME COMMENT 'Срок сдачи задания',
    FOREIGN KEY (rpd_id) REFERENCES rpd(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Темы занятий, контрольные точки, задания в рамках РПД';

CREATE TABLE topic_indicator (
    topic_id INT NOT NULL,
    indicator_id INT NOT NULL,
    PRIMARY KEY (topic_id, indicator_id),
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
    FOREIGN KEY (indicator_id) REFERENCES indicators(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Связь: Тема/Задание <-> Формируемый/Оцениваемый ИДК (M:N)';

CREATE TABLE grade_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE COMMENT 'Название шкалы (5-балльная, 100-балльная, Зачет/Незачет)',
    is_binary TINYINT(1) DEFAULT 0 COMMENT 'Шкала бинарная (Зачет/Незачет)?',
    min_grade DECIMAL(5,2) COMMENT 'Минимальное значение',
    max_grade DECIMAL(5,2) COMMENT 'Максимальное значение',
    pass_threshold DECIMAL(5,2) COMMENT 'Порог для зачета'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Справочник типов оценок (шкал оценивания)';

CREATE TABLE grade_columns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    topic_id INT UNIQUE NOT NULL COMMENT 'Ссылка на тему/контрольную точку',
    grade_type_id INT NOT NULL COMMENT 'Используемая шкала оценивания',
    name VARCHAR(400) NOT NULL COMMENT 'Название столбца (часто дублирует тему)',
    weight DECIMAL(5,2) DEFAULT 1.0 COMMENT 'Вес столбца при расчете итоговой оценки',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
    FOREIGN KEY (grade_type_id) REFERENCES grade_types(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Столбцы оценок в журнале успеваемости (точки контроля)';

CREATE TABLE grades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL COMMENT 'Ссылка на студента',
    grade_column_id INT NOT NULL COMMENT 'Ссылка на столбец оценки',
    grade_value DECIMAL(5,2) COMMENT 'Числовое значение оценки',
    grade_text VARCHAR(50) COMMENT 'Текстовое значение (Зачет/Незачет, Н/Я)',
    comment TEXT COMMENT 'Комментарий преподавателя',
    graded_by_user_id INT COMMENT 'Кто выставил оценку',
    graded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    indicator_id INT NULL COMMENT 'ОПЦИОНАЛЬНО: Ссылка на ИДК, который оценивался',
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (grade_column_id) REFERENCES grade_columns(id) ON DELETE CASCADE,
    FOREIGN KEY (graded_by_user_id) REFERENCES tbl_users(id_user) ON DELETE SET NULL,
    FOREIGN KEY (indicator_id) REFERENCES indicators(id) ON DELETE SET NULL,
    UNIQUE KEY `student_column` (student_id, grade_column_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Оценки студентов по точкам контроля';

-- ======================================================================
-- БЛОК: Опционально - Уровни освоения ИДК
-- ======================================================================

CREATE TABLE mastery_levels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE COMMENT 'Название уровня (Базовый, Продвинутый, Высокий)',
    description TEXT COMMENT 'Описание уровня'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Справочник уровней освоения компетенций/ИДК';

CREATE TABLE indicator_mastery_descriptors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    indicator_id INT NOT NULL,
    mastery_level_id INT NOT NULL,
    description TEXT NOT NULL COMMENT 'Описание (ЗУН(В)) для уровня освоения ИДК',
    FOREIGN KEY (indicator_id) REFERENCES indicators(id) ON DELETE CASCADE,
    FOREIGN KEY (mastery_level_id) REFERENCES mastery_levels(id) ON DELETE CASCADE,
    UNIQUE KEY `indicator_level` (indicator_id, mastery_level_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Дескрипторы (ЗУН(В)) для уровней освоения ИДК';