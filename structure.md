/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19  Distrib 10.11.11-MariaDB, for debian-linux-gnu (x86_64)
--
-- Host: 127.0.0.1    Database: kd_competencies
-- ------------------------------------------------------
-- Server version	9.2.0

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Current Database: `kd_competencies`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `kd_competencies` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `kd_competencies`;

--
-- Table structure for table `ChangeLog`
--

DROP TABLE IF EXISTS `ChangeLog`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `ChangeLog` (
  `id` int NOT NULL AUTO_INCREMENT,
  `model` varchar(45) DEFAULT NULL,
  `row_id` int DEFAULT NULL,
  `field` varchar(45) DEFAULT NULL,
  `old` varchar(500) DEFAULT NULL,
  `new` varchar(500) DEFAULT NULL,
  `revision_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `revision_id` (`revision_id`),
  CONSTRAINT `ChangeLog_ibfk_1` FOREIGN KEY (`revision_id`) REFERENCES `Revision` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Mode`
--

DROP TABLE IF EXISTS `Mode`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Mode` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `action` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Permissions`
--

DROP TABLE IF EXISTS `Permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Permissions` (
  `role_id` int NOT NULL,
  `mode_id` int NOT NULL,
  KEY `mode_id` (`mode_id`),
  KEY `role_id` (`role_id`),
  CONSTRAINT `Permissions_ibfk_1` FOREIGN KEY (`mode_id`) REFERENCES `Mode` (`id`) ON DELETE CASCADE,
  CONSTRAINT `Permissions_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id_role`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Revision`
--

DROP TABLE IF EXISTS `Revision`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Revision` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) DEFAULT NULL,
  `date` datetime DEFAULT NULL,
  `isActual` tinyint(1) DEFAULT NULL,
  `user_id` int NOT NULL,
  `aup_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `aup_id` (`aup_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `Revision_ibfk_1` FOREIGN KEY (`aup_id`) REFERENCES `tbl_aup` (`id_aup`),
  CONSTRAINT `Revision_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `tbl_users` (`id_user`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `aup_data`
--

DROP TABLE IF EXISTS `aup_data`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `aup_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `id_aup` int NOT NULL,
  `id_block` int DEFAULT NULL,
  `shifr` varchar(30) NOT NULL,
  `id_part` int DEFAULT NULL,
  `id_module` int DEFAULT NULL,
  `id_group` int DEFAULT NULL,
  `id_type_record` int NOT NULL,
  `id_discipline` int DEFAULT NULL,
  `discipline` varchar(350) NOT NULL,
  `id_period` int NOT NULL,
  `num_row` int NOT NULL,
  `id_type_control` int NOT NULL,
  `amount` int NOT NULL,
  `id_edizm` int NOT NULL,
  `zet` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `id_aup` (`id_aup`),
  KEY `id_block` (`id_block`),
  KEY `id_discipline` (`id_discipline`),
  KEY `id_edizm` (`id_edizm`),
  KEY `id_part` (`id_part`),
  KEY `id_period` (`id_period`),
  KEY `id_type_control` (`id_type_control`),
  KEY `id_type_record` (`id_type_record`),
  KEY `id_group` (`id_group`),
  KEY `id_module` (`id_module`),
  CONSTRAINT `aup_data_ibfk_1` FOREIGN KEY (`id_aup`) REFERENCES `tbl_aup` (`id_aup`) ON DELETE CASCADE,
  CONSTRAINT `aup_data_ibfk_10` FOREIGN KEY (`id_type_record`) REFERENCES `d_type_record` (`id`),
  CONSTRAINT `aup_data_ibfk_11` FOREIGN KEY (`id_group`) REFERENCES `groups` (`id_group`) ON DELETE SET DEFAULT,
  CONSTRAINT `aup_data_ibfk_12` FOREIGN KEY (`id_module`) REFERENCES `d_modules` (`id`) ON DELETE SET DEFAULT,
  CONSTRAINT `aup_data_ibfk_2` FOREIGN KEY (`id_block`) REFERENCES `d_blocks` (`id`) ON DELETE SET NULL,
  CONSTRAINT `aup_data_ibfk_3` FOREIGN KEY (`id_discipline`) REFERENCES `spr_discipline` (`id`) ON DELETE SET NULL,
  CONSTRAINT `aup_data_ibfk_4` FOREIGN KEY (`id_edizm`) REFERENCES `d_ed_izmereniya` (`id`),
  CONSTRAINT `aup_data_ibfk_7` FOREIGN KEY (`id_part`) REFERENCES `d_part` (`id`) ON DELETE SET NULL,
  CONSTRAINT `aup_data_ibfk_8` FOREIGN KEY (`id_period`) REFERENCES `d_period` (`id`),
  CONSTRAINT `aup_data_ibfk_9` FOREIGN KEY (`id_type_control`) REFERENCES `d_control_type` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=504 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_competency`
--

DROP TABLE IF EXISTS `competencies_competency`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_competency` (
  `competency_type_id` int NOT NULL,
  `fgos_vo_id` int DEFAULT NULL,
  `based_on_labor_function_id` int DEFAULT NULL,
  `code` varchar(20) NOT NULL COMMENT 'Код компетенции (УК-1, ОПК-2, ПК-3...)',
  `name` text NOT NULL COMMENT 'Формулировка компетенции',
  `description` text COMMENT 'Дополнительное описание компетенции',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_competency_code_fgos` (`code`,`fgos_vo_id`),
  KEY `based_on_labor_function_id` (`based_on_labor_function_id`),
  KEY `competency_type_id` (`competency_type_id`),
  KEY `fgos_vo_id` (`fgos_vo_id`),
  CONSTRAINT `competencies_competency_ibfk_1` FOREIGN KEY (`based_on_labor_function_id`) REFERENCES `competencies_labor_function` (`id`),
  CONSTRAINT `competencies_competency_ibfk_2` FOREIGN KEY (`competency_type_id`) REFERENCES `competencies_competency_type` (`id`),
  CONSTRAINT `competencies_competency_ibfk_3` FOREIGN KEY (`fgos_vo_id`) REFERENCES `competencies_fgos_vo` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=203 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_competency_type`
--

DROP TABLE IF EXISTS `competencies_competency_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_competency_type` (
  `name` varchar(100) NOT NULL COMMENT 'Название типа компетенции',
  `code` varchar(10) NOT NULL COMMENT 'Код типа (УК, ОПК, ПК)',
  `description` text COMMENT 'Описание типа компетенции',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_educational_program`
--

DROP TABLE IF EXISTS `competencies_educational_program`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_educational_program` (
  `title` varchar(255) NOT NULL,
  `code` varchar(50) NOT NULL COMMENT 'Код направления, например 09.03.01',
  `profile` varchar(255) DEFAULT NULL,
  `qualification` varchar(50) DEFAULT NULL,
  `form_of_education` varchar(50) DEFAULT NULL,
  `fgos_vo_id` int DEFAULT NULL,
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `enrollment_year` int DEFAULT NULL COMMENT 'Год набора',
  PRIMARY KEY (`id`),
  KEY `fgos_vo_id` (`fgos_vo_id`),
  CONSTRAINT `competencies_educational_program_ibfk_1` FOREIGN KEY (`fgos_vo_id`) REFERENCES `competencies_fgos_vo` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_educational_program_aup`
--

DROP TABLE IF EXISTS `competencies_educational_program_aup`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_educational_program_aup` (
  `educational_program_id` int NOT NULL,
  `aup_id` int NOT NULL,
  `is_primary` tinyint(1) DEFAULT NULL COMMENT 'Является ли этот АУП основным для программы',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_educational_program_aup` (`educational_program_id`,`aup_id`),
  KEY `aup_id` (`aup_id`),
  CONSTRAINT `competencies_educational_program_aup_ibfk_1` FOREIGN KEY (`aup_id`) REFERENCES `tbl_aup` (`id_aup`),
  CONSTRAINT `competencies_educational_program_aup_ibfk_2` FOREIGN KEY (`educational_program_id`) REFERENCES `competencies_educational_program` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_educational_program_ps`
--

DROP TABLE IF EXISTS `competencies_educational_program_ps`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_educational_program_ps` (
  `educational_program_id` int NOT NULL,
  `prof_standard_id` int NOT NULL,
  `priority` int DEFAULT NULL COMMENT 'Приоритет ПС в рамках ОП',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_educational_program_ps` (`educational_program_id`,`prof_standard_id`),
  KEY `prof_standard_id` (`prof_standard_id`),
  CONSTRAINT `competencies_educational_program_ps_ibfk_1` FOREIGN KEY (`educational_program_id`) REFERENCES `competencies_educational_program` (`id`),
  CONSTRAINT `competencies_educational_program_ps_ibfk_2` FOREIGN KEY (`prof_standard_id`) REFERENCES `competencies_prof_standard` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_fgos_recommended_ps`
--

DROP TABLE IF EXISTS `competencies_fgos_recommended_ps`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_fgos_recommended_ps` (
  `fgos_vo_id` int NOT NULL,
  `prof_standard_id` int NOT NULL,
  `is_mandatory` tinyint(1) DEFAULT NULL COMMENT 'Обязательный ПС или рекомендованный',
  `description` varchar(255) DEFAULT NULL COMMENT 'Примечание к связи',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_fgos_ps` (`fgos_vo_id`,`prof_standard_id`),
  KEY `prof_standard_id` (`prof_standard_id`),
  CONSTRAINT `competencies_fgos_recommended_ps_ibfk_1` FOREIGN KEY (`fgos_vo_id`) REFERENCES `competencies_fgos_vo` (`id`),
  CONSTRAINT `competencies_fgos_recommended_ps_ibfk_2` FOREIGN KEY (`prof_standard_id`) REFERENCES `competencies_prof_standard` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_fgos_vo`
--

DROP TABLE IF EXISTS `competencies_fgos_vo`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_fgos_vo` (
  `number` varchar(50) NOT NULL COMMENT 'Номер приказа',
  `date` date NOT NULL COMMENT 'Дата утверждения',
  `direction_code` varchar(10) NOT NULL COMMENT 'Код направления, например 09.03.01',
  `direction_name` varchar(255) NOT NULL COMMENT 'Название направления',
  `education_level` varchar(50) NOT NULL COMMENT 'Уровень образования (бакалавриат/магистратура/аспирантура)',
  `generation` varchar(10) NOT NULL COMMENT 'Поколение ФГОС (3+, 3++)',
  `file_path` varchar(255) DEFAULT NULL COMMENT 'Путь к PDF файлу',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_generalized_labor_function`
--

DROP TABLE IF EXISTS `competencies_generalized_labor_function`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_generalized_labor_function` (
  `prof_standard_id` int NOT NULL,
  `code` varchar(10) NOT NULL COMMENT 'Код ОТФ, например A',
  `name` varchar(255) NOT NULL COMMENT 'Название ОТФ',
  `qualification_level` varchar(10) DEFAULT NULL COMMENT 'Уровень квалификации',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `prof_standard_id` (`prof_standard_id`),
  CONSTRAINT `competencies_generalized_labor_function_ibfk_1` FOREIGN KEY (`prof_standard_id`) REFERENCES `competencies_prof_standard` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_indicator`
--

DROP TABLE IF EXISTS `competencies_indicator`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_indicator` (
  `competency_id` int NOT NULL,
  `code` varchar(20) NOT NULL COMMENT 'Код индикатора (ИУК-1.1, ИОПК-2.3, ИПК-3.2...)',
  `formulation` text NOT NULL COMMENT 'Формулировка индикатора',
  `source` varchar(255) DEFAULT NULL COMMENT 'Источник (ФГОС, ПООП, ВУЗ, ПС...)',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_indicator_code_competency` (`code`,`competency_id`),
  KEY `competency_id` (`competency_id`),
  CONSTRAINT `competencies_indicator_ibfk_1` FOREIGN KEY (`competency_id`) REFERENCES `competencies_competency` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=212 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_indicator_ps_link`
--

DROP TABLE IF EXISTS `competencies_indicator_ps_link`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_indicator_ps_link` (
  `indicator_id` int NOT NULL,
  `labor_function_id` int NOT NULL,
  `relevance_score` float DEFAULT NULL COMMENT 'Оценка релевантности (от 0 до 1)',
  `is_manual` tinyint(1) DEFAULT NULL COMMENT 'Связь установлена вручную',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_indicator_tf` (`indicator_id`,`labor_function_id`),
  KEY `labor_function_id` (`labor_function_id`),
  CONSTRAINT `competencies_indicator_ps_link_ibfk_1` FOREIGN KEY (`indicator_id`) REFERENCES `competencies_indicator` (`id`),
  CONSTRAINT `competencies_indicator_ps_link_ibfk_2` FOREIGN KEY (`labor_function_id`) REFERENCES `competencies_labor_function` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_labor_action`
--

DROP TABLE IF EXISTS `competencies_labor_action`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_labor_action` (
  `labor_function_id` int NOT NULL,
  `description` text NOT NULL COMMENT 'Описание трудового действия',
  `order` int DEFAULT NULL COMMENT 'Порядок в списке',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `labor_function_id` (`labor_function_id`),
  CONSTRAINT `competencies_labor_action_ibfk_1` FOREIGN KEY (`labor_function_id`) REFERENCES `competencies_labor_function` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_labor_function`
--

DROP TABLE IF EXISTS `competencies_labor_function`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_labor_function` (
  `generalized_labor_function_id` int NOT NULL,
  `code` varchar(10) NOT NULL COMMENT 'Код ТФ, например A/01.6',
  `name` varchar(255) NOT NULL COMMENT 'Название ТФ',
  `qualification_level` varchar(10) DEFAULT NULL COMMENT 'Уровень квалификации',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `generalized_labor_function_id` (`generalized_labor_function_id`),
  CONSTRAINT `competencies_labor_function_ibfk_1` FOREIGN KEY (`generalized_labor_function_id`) REFERENCES `competencies_generalized_labor_function` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_matrix`
--

DROP TABLE IF EXISTS `competencies_matrix`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_matrix` (
  `aup_data_id` int NOT NULL,
  `indicator_id` int NOT NULL,
  `relevance_score` float DEFAULT NULL COMMENT 'Оценка релевантности (от 0 до 1)',
  `is_manual` tinyint(1) DEFAULT NULL COMMENT 'Связь установлена вручную',
  `created_by` int DEFAULT NULL COMMENT 'ID пользователя, создавшего связь',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matrix_aup_indicator` (`aup_data_id`,`indicator_id`),
  KEY `indicator_id` (`indicator_id`),
  CONSTRAINT `competencies_matrix_ibfk_1` FOREIGN KEY (`aup_data_id`) REFERENCES `aup_data` (`id`),
  CONSTRAINT `competencies_matrix_ibfk_2` FOREIGN KEY (`indicator_id`) REFERENCES `competencies_indicator` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=59 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_prof_standard`
--

DROP TABLE IF EXISTS `competencies_prof_standard`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_prof_standard` (
  `code` varchar(50) NOT NULL COMMENT 'Код профстандарта, например 06.001',
  `name` varchar(255) NOT NULL COMMENT 'Название профстандарта',
  `order_number` varchar(50) DEFAULT NULL COMMENT 'Номер приказа',
  `order_date` date DEFAULT NULL COMMENT 'Дата приказа',
  `registration_number` varchar(50) DEFAULT NULL COMMENT 'Рег. номер Минюста',
  `registration_date` date DEFAULT NULL COMMENT 'Дата регистрации в Минюсте',
  `parsed_content` text COMMENT 'Содержимое стандарта в Markdown',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_required_knowledge`
--

DROP TABLE IF EXISTS `competencies_required_knowledge`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_required_knowledge` (
  `labor_function_id` int NOT NULL,
  `description` text NOT NULL COMMENT 'Описание необходимого знания',
  `order` int DEFAULT NULL COMMENT 'Порядок в списке',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `labor_function_id` (`labor_function_id`),
  CONSTRAINT `competencies_required_knowledge_ibfk_1` FOREIGN KEY (`labor_function_id`) REFERENCES `competencies_labor_function` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `competencies_required_skill`
--

DROP TABLE IF EXISTS `competencies_required_skill`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `competencies_required_skill` (
  `labor_function_id` int NOT NULL,
  `description` text NOT NULL COMMENT 'Описание необходимого умения',
  `order` int DEFAULT NULL COMMENT 'Порядок в списке',
  `id` int NOT NULL AUTO_INCREMENT,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `labor_function_id` (`labor_function_id`),
  CONSTRAINT `competencies_required_skill_ibfk_1` FOREIGN KEY (`labor_function_id`) REFERENCES `competencies_labor_function` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `d_blocks`
--

DROP TABLE IF EXISTS `d_blocks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `d_blocks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `d_control_type`
--

DROP TABLE IF EXISTS `d_control_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `d_control_type` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `shortname` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `d_ed_izmereniya`
--

DROP TABLE IF EXISTS `d_ed_izmereniya`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `d_ed_izmereniya` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `d_modules`
--

DROP TABLE IF EXISTS `d_modules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `d_modules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `color` varchar(8) NOT NULL DEFAULT '#5f60ec',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `d_part`
--

DROP TABLE IF EXISTS `d_part`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `d_part` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `d_period`
--

DROP TABLE IF EXISTS `d_period`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `d_period` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `d_type_record`
--

DROP TABLE IF EXISTS `d_type_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `d_type_record` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `discipline_period_assoc`
--

DROP TABLE IF EXISTS `discipline_period_assoc`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `discipline_period_assoc` (
  `id` int NOT NULL AUTO_INCREMENT,
  `unification_discipline_id` int DEFAULT NULL,
  `period_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `period_id` (`period_id`),
  KEY `unification_discipline_id` (`unification_discipline_id`),
  CONSTRAINT `discipline_period_assoc_ibfk_1` FOREIGN KEY (`period_id`) REFERENCES `d_period` (`id`) ON DELETE CASCADE,
  CONSTRAINT `discipline_period_assoc_ibfk_2` FOREIGN KEY (`unification_discipline_id`) REFERENCES `unification_discipline` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `discipline_table`
--

DROP TABLE IF EXISTS `discipline_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `discipline_table` (
  `id` int NOT NULL AUTO_INCREMENT,
  `id_aup` int NOT NULL,
  `id_unique_discipline` int NOT NULL,
  `study_group_id` int NOT NULL,
  `semester` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `id_aup` (`id_aup`),
  KEY `id_unique_discipline` (`id_unique_discipline`),
  KEY `study_group_id` (`study_group_id`),
  CONSTRAINT `discipline_table_ibfk_1` FOREIGN KEY (`id_aup`) REFERENCES `tbl_aup` (`id_aup`),
  CONSTRAINT `discipline_table_ibfk_2` FOREIGN KEY (`id_unique_discipline`) REFERENCES `spr_discipline` (`id`),
  CONSTRAINT `discipline_table_ibfk_3` FOREIGN KEY (`study_group_id`) REFERENCES `study_group` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `faculty_discipline_period`
--

DROP TABLE IF EXISTS `faculty_discipline_period`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `faculty_discipline_period` (
  `discipline_period_id` int DEFAULT NULL,
  `faculty_id` int DEFAULT NULL,
  KEY `discipline_period_id` (`discipline_period_id`),
  KEY `faculty_id` (`faculty_id`),
  CONSTRAINT `faculty_discipline_period_ibfk_1` FOREIGN KEY (`discipline_period_id`) REFERENCES `discipline_period_assoc` (`id`) ON DELETE CASCADE,
  CONSTRAINT `faculty_discipline_period_ibfk_2` FOREIGN KEY (`faculty_id`) REFERENCES `spr_faculty` (`id_faculty`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `grade_column`
--

DROP TABLE IF EXISTS `grade_column`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `grade_column` (
  `id` int NOT NULL AUTO_INCREMENT,
  `discipline_table_id` int NOT NULL,
  `grade_type_id` int NOT NULL,
  `topic_id` int DEFAULT NULL,
  `hidden` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `discipline_table_id` (`discipline_table_id`),
  KEY `grade_type_id` (`grade_type_id`),
  KEY `topic_id` (`topic_id`),
  CONSTRAINT `grade_column_ibfk_1` FOREIGN KEY (`discipline_table_id`) REFERENCES `discipline_table` (`id`),
  CONSTRAINT `grade_column_ibfk_2` FOREIGN KEY (`grade_type_id`) REFERENCES `grade_type` (`id`) ON DELETE CASCADE,
  CONSTRAINT `grade_column_ibfk_3` FOREIGN KEY (`topic_id`) REFERENCES `topic` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `grade_table`
--

DROP TABLE IF EXISTS `grade_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `grade_table` (
  `id` int NOT NULL AUTO_INCREMENT,
  `id_aup` int NOT NULL,
  `id_unique_discipline` int NOT NULL,
  `semester` int NOT NULL,
  `study_group_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `id_aup` (`id_aup`),
  KEY `id_unique_discipline` (`id_unique_discipline`),
  KEY `study_group_id` (`study_group_id`),
  CONSTRAINT `grade_table_ibfk_1` FOREIGN KEY (`id_aup`) REFERENCES `tbl_aup` (`id_aup`),
  CONSTRAINT `grade_table_ibfk_2` FOREIGN KEY (`id_unique_discipline`) REFERENCES `spr_discipline` (`id`),
  CONSTRAINT `grade_table_ibfk_3` FOREIGN KEY (`study_group_id`) REFERENCES `study_group` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `grade_type`
--

DROP TABLE IF EXISTS `grade_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `grade_type` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `type` varchar(255) NOT NULL,
  `min_grade` int DEFAULT NULL,
  `max_grade` int DEFAULT NULL,
  `archived` tinyint(1) DEFAULT NULL,
  `binary` tinyint(1) DEFAULT NULL,
  `weight_grade` int DEFAULT NULL,
  `color` varchar(255) DEFAULT NULL,
  `is_custom` tinyint(1) DEFAULT NULL,
  `discipline_table_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `discipline_table_id` (`discipline_table_id`),
  CONSTRAINT `grade_type_ibfk_1` FOREIGN KEY (`discipline_table_id`) REFERENCES `discipline_table` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `grades`
--

DROP TABLE IF EXISTS `grades`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `grades` (
  `id` int NOT NULL AUTO_INCREMENT,
  `value` int DEFAULT NULL,
  `student_id` int NOT NULL,
  `grade_column_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `grade_column_id` (`grade_column_id`),
  KEY `student_id` (`student_id`),
  CONSTRAINT `grades_ibfk_1` FOREIGN KEY (`grade_column_id`) REFERENCES `grade_column` (`id`) ON DELETE CASCADE,
  CONSTRAINT `grades_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `groups`
--

DROP TABLE IF EXISTS `groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `groups` (
  `id_group` int NOT NULL AUTO_INCREMENT,
  `name_group` varchar(255) NOT NULL,
  `color` varchar(8) NOT NULL,
  `weight` int NOT NULL DEFAULT '5',
  PRIMARY KEY (`id_group`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `id_role` int NOT NULL AUTO_INCREMENT,
  `name_role` varchar(100) NOT NULL,
  PRIMARY KEY (`id_role`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_bells`
--

DROP TABLE IF EXISTS `spr_bells`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_bells` (
  `id` int NOT NULL AUTO_INCREMENT,
  `order` int NOT NULL,
  `name` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_branch`
--

DROP TABLE IF EXISTS `spr_branch`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_branch` (
  `id_branch` int NOT NULL AUTO_INCREMENT,
  `city` varchar(255) NOT NULL,
  `location` varchar(255) NOT NULL,
  PRIMARY KEY (`id_branch`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_degree_education`
--

DROP TABLE IF EXISTS `spr_degree_education`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_degree_education` (
  `id_degree` int NOT NULL AUTO_INCREMENT,
  `name_deg` varchar(255) NOT NULL,
  PRIMARY KEY (`id_degree`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_discipline`
--

DROP TABLE IF EXISTS `spr_discipline`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_discipline` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1004 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_faculty`
--

DROP TABLE IF EXISTS `spr_faculty`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_faculty` (
  `id_faculty` int NOT NULL AUTO_INCREMENT,
  `name_faculty` varchar(255) NOT NULL,
  `id_branch` int NOT NULL,
  `dean` varchar(255) DEFAULT NULL,
  `admin_only` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id_faculty`),
  KEY `id_branch` (`id_branch`),
  CONSTRAINT `spr_faculty_ibfk_1` FOREIGN KEY (`id_branch`) REFERENCES `spr_branch` (`id_branch`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_form_education`
--

DROP TABLE IF EXISTS `spr_form_education`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_form_education` (
  `id_form` int NOT NULL AUTO_INCREMENT,
  `form` varchar(255) NOT NULL,
  PRIMARY KEY (`id_form`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_name_op`
--

DROP TABLE IF EXISTS `spr_name_op`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_name_op` (
  `id_spec` int NOT NULL AUTO_INCREMENT,
  `program_code` varchar(255) NOT NULL,
  `num_profile` varchar(255) NOT NULL,
  `name_spec` varchar(255) NOT NULL,
  PRIMARY KEY (`id_spec`),
  KEY `program_code` (`program_code`),
  CONSTRAINT `spr_name_op_ibfk_1` FOREIGN KEY (`program_code`) REFERENCES `spr_okco` (`program_code`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_okco`
--

DROP TABLE IF EXISTS `spr_okco`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_okco` (
  `program_code` varchar(255) NOT NULL,
  `name_okco` varchar(255) NOT NULL,
  PRIMARY KEY (`program_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_place`
--

DROP TABLE IF EXISTS `spr_place`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_place` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `prefix` varchar(255) NOT NULL,
  `is_online` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_rop`
--

DROP TABLE IF EXISTS `spr_rop`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_rop` (
  `id_rop` int NOT NULL AUTO_INCREMENT,
  `last_name` varchar(255) NOT NULL,
  `first_name` varchar(255) NOT NULL,
  `middle_name` varchar(255) NOT NULL,
  `email` varchar(255) NOT NULL,
  `telephone` varchar(255) NOT NULL,
  PRIMARY KEY (`id_rop`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_standard_zet`
--

DROP TABLE IF EXISTS `spr_standard_zet`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_standard_zet` (
  `id_standard` int NOT NULL AUTO_INCREMENT,
  `type_standard` varchar(255) NOT NULL,
  PRIMARY KEY (`id_standard`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spr_volume_degree_zet`
--

DROP TABLE IF EXISTS `spr_volume_degree_zet`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `spr_volume_degree_zet` (
  `id_volume_deg` int NOT NULL AUTO_INCREMENT,
  `program_code` varchar(255) NOT NULL,
  `id_standard` int NOT NULL,
  `zet` int NOT NULL,
  `effective_date` date DEFAULT NULL,
  PRIMARY KEY (`id_volume_deg`),
  KEY `program_code` (`program_code`),
  CONSTRAINT `spr_volume_degree_zet_ibfk_1` FOREIGN KEY (`program_code`) REFERENCES `spr_okco` (`program_code`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `students`
--

DROP TABLE IF EXISTS `students`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `students` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(400) NOT NULL,
  `study_group_id` int NOT NULL,
  `lk_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `study_group_id` (`study_group_id`),
  CONSTRAINT `students_ibfk_1` FOREIGN KEY (`study_group_id`) REFERENCES `study_group` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `study_group`
--

DROP TABLE IF EXISTS `study_group`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `study_group` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `num_aup` varchar(255) NOT NULL,
  `tutor_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `tutor_id` (`tutor_id`),
  CONSTRAINT `study_group_ibfk_1` FOREIGN KEY (`tutor_id`) REFERENCES `tutors` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tbl_aup`
--

DROP TABLE IF EXISTS `tbl_aup`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tbl_aup` (
  `id_aup` int NOT NULL AUTO_INCREMENT,
  `file` varchar(255) NOT NULL,
  `num_aup` varchar(255) NOT NULL,
  `base` varchar(255) NOT NULL,
  `id_faculty` int NOT NULL,
  `id_rop` int NOT NULL,
  `type_educ` varchar(255) NOT NULL,
  `qualification` varchar(255) NOT NULL,
  `type_standard` varchar(255) NOT NULL,
  `id_department` int DEFAULT NULL,
  `period_educ` varchar(255) NOT NULL,
  `id_degree` int NOT NULL,
  `id_form` int NOT NULL,
  `years` int NOT NULL,
  `months` int DEFAULT NULL,
  `id_spec` int DEFAULT NULL,
  `year_beg` int NOT NULL,
  `year_end` int NOT NULL,
  `is_actual` tinyint(1) NOT NULL,
  PRIMARY KEY (`id_aup`),
  KEY `id_degree` (`id_degree`),
  KEY `id_department` (`id_department`),
  KEY `id_faculty` (`id_faculty`),
  KEY `id_form` (`id_form`),
  KEY `id_rop` (`id_rop`),
  KEY `id_spec` (`id_spec`),
  CONSTRAINT `tbl_aup_ibfk_1` FOREIGN KEY (`id_degree`) REFERENCES `spr_degree_education` (`id_degree`) ON DELETE CASCADE,
  CONSTRAINT `tbl_aup_ibfk_2` FOREIGN KEY (`id_department`) REFERENCES `tbl_department` (`id_department`) ON DELETE SET NULL,
  CONSTRAINT `tbl_aup_ibfk_3` FOREIGN KEY (`id_faculty`) REFERENCES `spr_faculty` (`id_faculty`) ON DELETE CASCADE,
  CONSTRAINT `tbl_aup_ibfk_4` FOREIGN KEY (`id_form`) REFERENCES `spr_form_education` (`id_form`) ON DELETE CASCADE,
  CONSTRAINT `tbl_aup_ibfk_5` FOREIGN KEY (`id_rop`) REFERENCES `spr_rop` (`id_rop`),
  CONSTRAINT `tbl_aup_ibfk_6` FOREIGN KEY (`id_spec`) REFERENCES `spr_name_op` (`id_spec`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=102 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tbl_department`
--

DROP TABLE IF EXISTS `tbl_department`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tbl_department` (
  `id_department` int NOT NULL AUTO_INCREMENT,
  `name_department` varchar(255) DEFAULT NULL,
  `faculty_id` int DEFAULT NULL,
  PRIMARY KEY (`id_department`),
  KEY `faculty_id` (`faculty_id`),
  CONSTRAINT `tbl_department_ibfk_1` FOREIGN KEY (`faculty_id`) REFERENCES `spr_faculty` (`id_faculty`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tbl_token`
--

DROP TABLE IF EXISTS `tbl_token`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tbl_token` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `refresh_token` varchar(256) NOT NULL,
  `user_agent` varchar(256) NOT NULL,
  `ttl` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `tbl_token_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `tbl_users` (`id_user`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=53 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tbl_users`
--

DROP TABLE IF EXISTS `tbl_users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tbl_users` (
  `id_user` int NOT NULL AUTO_INCREMENT,
  `login` varchar(100) NOT NULL,
  `name` varchar(200) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  `password_hash` varchar(200) NOT NULL,
  `auth_type` varchar(255) DEFAULT NULL,
  `approved_lk` tinyint(1) DEFAULT NULL,
  `request_approve_date` datetime DEFAULT NULL,
  `lk_id` int DEFAULT NULL,
  `department_id` int DEFAULT NULL,
  PRIMARY KEY (`id_user`),
  UNIQUE KEY `login` (`login`),
  UNIQUE KEY `password_hash` (`password_hash`),
  KEY `department_id` (`department_id`),
  CONSTRAINT `tbl_users_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `tbl_department` (`id_department`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `topic`
--

DROP TABLE IF EXISTS `topic`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `topic` (
  `id` int NOT NULL AUTO_INCREMENT,
  `discipline_table_id` int DEFAULT NULL,
  `topic` varchar(400) DEFAULT NULL,
  `chapter` varchar(400) DEFAULT NULL,
  `id_type_control` int DEFAULT NULL,
  `task_link` varchar(400) DEFAULT NULL,
  `task_link_name` varchar(255) DEFAULT NULL,
  `completed_task_link` varchar(255) DEFAULT NULL,
  `completed_task_link_name` varchar(255) DEFAULT NULL,
  `study_group_id` int NOT NULL,
  `date` datetime DEFAULT NULL,
  `lesson_order` int DEFAULT NULL,
  `spr_bells_id` int DEFAULT NULL,
  `date_task_finish` datetime DEFAULT NULL,
  `date_task_finish_include` tinyint(1) DEFAULT NULL,
  `spr_place_id` int DEFAULT NULL,
  `place_note` varchar(400) DEFAULT NULL,
  `note` varchar(400) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `discipline_table_id` (`discipline_table_id`),
  KEY `id_type_control` (`id_type_control`),
  KEY `spr_bells_id` (`spr_bells_id`),
  KEY `spr_place_id` (`spr_place_id`),
  KEY `study_group_id` (`study_group_id`),
  CONSTRAINT `topic_ibfk_1` FOREIGN KEY (`discipline_table_id`) REFERENCES `discipline_table` (`id`),
  CONSTRAINT `topic_ibfk_2` FOREIGN KEY (`id_type_control`) REFERENCES `d_control_type` (`id`),
  CONSTRAINT `topic_ibfk_3` FOREIGN KEY (`spr_bells_id`) REFERENCES `spr_bells` (`id`),
  CONSTRAINT `topic_ibfk_4` FOREIGN KEY (`spr_place_id`) REFERENCES `spr_place` (`id`),
  CONSTRAINT `topic_ibfk_5` FOREIGN KEY (`study_group_id`) REFERENCES `study_group` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tutors`
--

DROP TABLE IF EXISTS `tutors`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tutors` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(400) NOT NULL,
  `lk_id` int NOT NULL,
  `post` varchar(400) DEFAULT NULL,
  `id_department` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `id_department` (`id_department`),
  CONSTRAINT `tutors_ibfk_1` FOREIGN KEY (`id_department`) REFERENCES `tbl_department` (`id_department`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tutors_order`
--

DROP TABLE IF EXISTS `tutors_order`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tutors_order` (
  `id` int NOT NULL AUTO_INCREMENT,
  `faculty_id` int NOT NULL,
  `date` datetime DEFAULT NULL,
  `num_order` int NOT NULL,
  `spr_form_education_id` int DEFAULT NULL,
  `year` int NOT NULL,
  `executor` varchar(255) NOT NULL,
  `signer` varchar(255) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `faculty_id` (`faculty_id`),
  KEY `spr_form_education_id` (`spr_form_education_id`),
  CONSTRAINT `tutors_order_ibfk_1` FOREIGN KEY (`faculty_id`) REFERENCES `spr_faculty` (`id_faculty`),
  CONSTRAINT `tutors_order_ibfk_2` FOREIGN KEY (`spr_form_education_id`) REFERENCES `spr_form_education` (`id_form`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tutors_order_row`
--

DROP TABLE IF EXISTS `tutors_order_row`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tutors_order_row` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tutors_order_id` int NOT NULL,
  `department_id` int NOT NULL,
  `study_group_id` int NOT NULL,
  `tutor_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `department_id` (`department_id`),
  KEY `study_group_id` (`study_group_id`),
  KEY `tutor_id` (`tutor_id`),
  KEY `tutors_order_id` (`tutors_order_id`),
  CONSTRAINT `tutors_order_row_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `tbl_department` (`id_department`),
  CONSTRAINT `tutors_order_row_ibfk_2` FOREIGN KEY (`study_group_id`) REFERENCES `study_group` (`id`),
  CONSTRAINT `tutors_order_row_ibfk_3` FOREIGN KEY (`tutor_id`) REFERENCES `tutors` (`id`),
  CONSTRAINT `tutors_order_row_ibfk_4` FOREIGN KEY (`tutors_order_id`) REFERENCES `tutors_order` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `unification_discipline`
--

DROP TABLE IF EXISTS `unification_discipline`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `unification_discipline` (
  `id` int NOT NULL AUTO_INCREMENT,
  `discipline` varchar(255) DEFAULT NULL,
  `is_faculties_different` tinyint(1) DEFAULT NULL,
  `ugsn` varchar(255) DEFAULT NULL,
  `degree` varchar(255) DEFAULT NULL,
  `direction` tinyint(1) DEFAULT NULL,
  `semesters_count` int DEFAULT NULL,
  `amount` int DEFAULT NULL,
  `measure_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `measure_id` (`measure_id`),
  CONSTRAINT `unification_discipline_ibfk_1` FOREIGN KEY (`measure_id`) REFERENCES `d_ed_izmereniya` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `unification_load`
--

DROP TABLE IF EXISTS `unification_load`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `unification_load` (
  `id` int NOT NULL AUTO_INCREMENT,
  `education_form_id` int DEFAULT NULL,
  `discipline_period_assoc_id` int DEFAULT NULL,
  `lectures` float DEFAULT NULL,
  `seminars` float DEFAULT NULL,
  `srs` float DEFAULT NULL,
  `practices` float DEFAULT NULL,
  `control_type_id` int DEFAULT NULL,
  `zet` float DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `control_type_id` (`control_type_id`),
  KEY `discipline_period_assoc_id` (`discipline_period_assoc_id`),
  KEY `education_form_id` (`education_form_id`),
  CONSTRAINT `unification_load_ibfk_1` FOREIGN KEY (`control_type_id`) REFERENCES `d_control_type` (`id`),
  CONSTRAINT `unification_load_ibfk_2` FOREIGN KEY (`discipline_period_assoc_id`) REFERENCES `discipline_period_assoc` (`id`) ON DELETE CASCADE,
  CONSTRAINT `unification_load_ibfk_3` FOREIGN KEY (`education_form_id`) REFERENCES `spr_form_education` (`id_form`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `unification_okso_assoc`
--

DROP TABLE IF EXISTS `unification_okso_assoc`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `unification_okso_assoc` (
  `unification_id` int DEFAULT NULL,
  `okso_id` varchar(255) DEFAULT NULL,
  KEY `okso_id` (`okso_id`),
  KEY `unification_id` (`unification_id`),
  CONSTRAINT `unification_okso_assoc_ibfk_1` FOREIGN KEY (`okso_id`) REFERENCES `spr_okco` (`program_code`) ON DELETE CASCADE,
  CONSTRAINT `unification_okso_assoc_ibfk_2` FOREIGN KEY (`unification_id`) REFERENCES `unification_discipline` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_roles`
--

DROP TABLE IF EXISTS `user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_roles` (
  `role_id` int NOT NULL,
  `user_id` int NOT NULL,
  KEY `role_id` (`role_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `user_roles_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id_role`) ON DELETE CASCADE,
  CONSTRAINT `user_roles_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `tbl_users` (`id_user`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users_faculty`
--

DROP TABLE IF EXISTS `users_faculty`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `users_faculty` (
  `user_id` int NOT NULL,
  `faculty_id` int NOT NULL,
  KEY `faculty_id` (`faculty_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `users_faculty_ibfk_1` FOREIGN KEY (`faculty_id`) REFERENCES `spr_faculty` (`id_faculty`) ON DELETE CASCADE,
  CONSTRAINT `users_faculty_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `tbl_users` (`id_user`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-04-20 15:02:22
