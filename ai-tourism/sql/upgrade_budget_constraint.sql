-- =============================================================================
-- upgrade_budget_constraint.sql
-- 「预算硬约束规划」数据库升级脚本
-- 适用：ai-tourism（SpringBoot + MySQL 8.x）
-- 执行：mysql -uroot -p123456 < sql/upgrade_budget_constraint.sql
--
-- 背景：原预算模块是「先生成行程 → 事后估算费用」，用户给定预算不起约束作用。
--       本脚本为「预算反推规划」提供存储支撑：
--         1) t_ai_assistant_sessions 增加 budget_amount / origin_city（意图识别落库）
--         2) t_budget 增加 user_budget / budget_status / remaining_budget /
--            envelope_json / plan_json（封套 + 核验结果）
--         3) t_budget 增加 budget_status 索引，便于统计「预算达成率」
--
-- 本脚本幂等（可重复执行）。
-- =============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------------------------
-- 幂等加列工具过程：存在则跳过
-- -----------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS add_column_if_absent;
DELIMITER $$
CREATE PROCEDURE add_column_if_absent(
    IN p_table  VARCHAR(64),
    IN p_column VARCHAR(64),
    IN p_ddl    VARCHAR(512)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = p_table
          AND COLUMN_NAME  = p_column
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE `', p_table, '` ADD COLUMN ', p_ddl);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

-- -----------------------------------------------------------------------------
-- 1. 会话表：预算金额与出发地（由 Python Agent 意图识别提取后回调写入）
-- -----------------------------------------------------------------------------
CALL add_column_if_absent('t_ai_assistant_sessions', 'budget_amount',
    'budget_amount DECIMAL(12,2) NULL COMMENT ''用户给定总预算（元），NULL=未指定''');

CALL add_column_if_absent('t_ai_assistant_sessions', 'origin_city',
    'origin_city VARCHAR(64) NULL COMMENT ''出发城市（用于大交通里程估算）''');

-- -----------------------------------------------------------------------------
-- 2. 预算表：用户预算 / 达成状态 / 结余 / 封套 / 出行方案
-- -----------------------------------------------------------------------------
CALL add_column_if_absent('t_budget', 'user_budget',
    'user_budget DECIMAL(12,2) NULL COMMENT ''用户给定总预算（元），NULL=未指定''');

CALL add_column_if_absent('t_budget', 'budget_status',
    'budget_status VARCHAR(16) NOT NULL DEFAULT ''UNKNOWN'' COMMENT ''预算达成状态: WITHIN_BUDGET/OVER_BUDGET/UNKNOWN''');

CALL add_column_if_absent('t_budget', 'remaining_budget',
    'remaining_budget DECIMAL(12,2) NULL COMMENT ''预算结余（元），负数表示超支''');

CALL add_column_if_absent('t_budget', 'envelope_json',
    'envelope_json TEXT NULL COMMENT ''预算封套：分项上限与档次建议（预算反推结果）''');

CALL add_column_if_absent('t_budget', 'plan_json',
    'plan_json TEXT NULL COMMENT ''严格按预算生成的出行方案：天数/交通方式/住宿档次/每日节奏''');

-- -----------------------------------------------------------------------------
-- 3. 索引：按达成状态统计预算命中率（论文实验三：预算达成率对比）
-- -----------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS add_index_if_absent;
DELIMITER $$
CREATE PROCEDURE add_index_if_absent(
    IN p_table VARCHAR(64),
    IN p_index VARCHAR(64),
    IN p_ddl   VARCHAR(512)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = p_table
          AND INDEX_NAME   = p_index
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE `', p_table, '` ADD ', p_ddl);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

CALL add_index_if_absent('t_budget', 'idx_budget_status',
    'INDEX idx_budget_status (budget_status)');

DROP PROCEDURE IF EXISTS add_column_if_absent;
DROP PROCEDURE IF EXISTS add_index_if_absent;

SET FOREIGN_KEY_CHECKS = 1;

-- 校验
SELECT 't_budget columns' AS info;
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't_budget'
ORDER BY ORDINAL_POSITION;
