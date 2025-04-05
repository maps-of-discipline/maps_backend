-- Minimal schema required for initial startup
CREATE TABLE IF NOT EXISTS d_blocks (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS d_control_type (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    shortname VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS d_ed_izmereniya (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS d_modules (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    color VARCHAR(8) NOT NULL DEFAULT '#5f60ec'
);

CREATE TABLE IF NOT EXISTS d_part (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS d_period (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS d_type_record (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS `groups` (
    id_group INTEGER PRIMARY KEY AUTO_INCREMENT,
    name_group VARCHAR(255) NOT NULL,
    color VARCHAR(8) NOT NULL,
    weight INTEGER NOT NULL DEFAULT 5
);

-- Add some minimal required data
INSERT INTO d_blocks (title) VALUES ('Базовая часть'), ('Вариативная часть');
INSERT INTO d_modules (title) VALUES ('Default Module');
INSERT INTO `groups` (name_group, color, weight) VALUES ('Default Group', '#000000', 5);