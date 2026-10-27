-- =============================================================================
-- upgrade_tripstar.sql
-- 对标 TripStar 的数据库升级脚本
-- 适用：ai-tourism（SpringBoot + MySQL 8.x）
-- 执行：mysql -uroot -p123456 < sql/upgrade_tripstar.sql
--
-- 本脚本幂等（可重复执行）：
--   1) 新增 用户偏好记忆库 t_user_preference_memory（权重 + 遗忘 + TOP-K 召回）
--   2) 新增 行程知识图谱缓存 t_trip_graph（城市-天数-景点-预算 节点/边）
--   3) t_poi 增加 景点预约提醒 字段（need_reservation / reservation_channel / reservation_note）
--   4) 为需预约景点填充预约渠道种子数据
-- =============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------------------------
-- 1. 用户偏好记忆库（升级项 A）
--    weight  = base + α × hit_count，并按 exp(-λ·Δt) 时间衰减
--    规划时按 weight DESC 取 TOP-K 且 weight ≥ θ 注入 Prompt
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS t_user_preference_memory (
  id            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id       VARCHAR(64)  NOT NULL                COMMENT '用户ID',
  pref_type     VARCHAR(32)  NOT NULL                COMMENT '偏好类型: budget/style/interest/pace/companion/diet/avoid',
  pref_key      VARCHAR(64)  NOT NULL                COMMENT '偏好键，如 interest',
  pref_value    VARCHAR(255) NOT NULL                COMMENT '偏好值，如 历史古迹',
  weight        DECIMAL(6,3) NOT NULL DEFAULT 1.000  COMMENT '权重(0~5)',
  hit_count     INT          NOT NULL DEFAULT 1      COMMENT '命中/提取次数',
  source        VARCHAR(32)  NOT NULL DEFAULT 'auto' COMMENT '来源: auto/manual',
  last_hit_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最近命中时间',
  created_time  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  modify_time   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_pref (user_id, pref_type, pref_key, pref_value),
  KEY idx_user_weight (user_id, weight)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户偏好记忆库';

-- -----------------------------------------------------------------------------
-- 2. 行程知识图谱缓存（升级项 C）
--    行程生成后由 KnowledgeGraphService 构建 {nodes, edges, categories} 并缓存，
--    前端 ECharts graph 通过 GET /trip/graph/{sessionId} 读取
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS t_trip_graph (
  id           BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
  session_id   VARCHAR(64) NOT NULL                COMMENT '会话ID',
  user_id      VARCHAR(64) NOT NULL                COMMENT '用户ID',
  city_name    VARCHAR(64)          DEFAULT NULL   COMMENT '城市(多城市时为逗号分隔)',
  graph_json   JSON                                 COMMENT '知识图谱 {nodes, edges, categories}',
  node_count   INT         NOT NULL DEFAULT 0      COMMENT '节点数',
  edge_count   INT         NOT NULL DEFAULT 0      COMMENT '边数',
  created_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  modify_time  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_session (session_id),
  KEY idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行程知识图谱缓存';

-- -----------------------------------------------------------------------------
-- 3. t_poi 增加景点预约提醒字段（升级项 D）
--    MySQL 8 的 ADD COLUMN 不支持 IF NOT EXISTS，这里用 INFORMATION_SCHEMA 守卫实现幂等
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
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = p_table AND COLUMN_NAME = p_column
  ) THEN
    SET @ddl = CONCAT('ALTER TABLE `', p_table, '` ADD COLUMN ', p_ddl);
    PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL add_column_if_absent('t_poi', 'need_reservation',
     'need_reservation TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''是否需提前预约''');
CALL add_column_if_absent('t_poi', 'reservation_channel',
     'reservation_channel VARCHAR(255) DEFAULT NULL COMMENT ''预约渠道''');
CALL add_column_if_absent('t_poi', 'reservation_note',
     'reservation_note VARCHAR(255) DEFAULT NULL COMMENT ''预约提示''');

DROP PROCEDURE IF EXISTS add_column_if_absent;

-- -----------------------------------------------------------------------------
-- 4. 预约渠道种子数据（仅覆盖已知需预约景点，按名称模糊匹配，可重复执行）
-- -----------------------------------------------------------------------------
UPDATE t_poi SET need_reservation = 1,
       reservation_channel = '故宫博物院官网 / 微信小程序「故宫博物院观众服务」',
       reservation_note = '需提前 1-7 天实名预约，周一闭馆'
 WHERE poi_name LIKE '%故宫%';

UPDATE t_poi SET need_reservation = 1,
       reservation_channel = '陕西历史博物馆官网 / 微信公众号',
       reservation_note = '免费不免票，需提前预约，节假日名额紧张'
 WHERE poi_name LIKE '%陕西历史博物馆%' OR poi_name LIKE '%陕历博%';

UPDATE t_poi SET need_reservation = 1,
       reservation_channel = '中国国家博物馆官网 / 微信小程序',
       reservation_note = '需提前 1-7 天实名预约，周一闭馆'
 WHERE poi_name LIKE '%国家博物馆%';

UPDATE t_poi SET need_reservation = 1,
       reservation_channel = '秦始皇兵马俑博物馆官网 / 微信公众号',
       reservation_note = '旺季建议提前 1-3 天预约'
 WHERE poi_name LIKE '%兵马俑%';

UPDATE t_poi SET need_reservation = 1,
       reservation_channel = '三星堆博物馆微信公众号',
       reservation_note = '需提前预约，节假日建议提前 3 天'
 WHERE poi_name LIKE '%三星堆%';

UPDATE t_poi SET need_reservation = 1,
       reservation_channel = '布达拉宫官网 / 微信公众号',
       reservation_note = '需提前 1-7 天预约，限流严格'
 WHERE poi_name LIKE '%布达拉宫%';

UPDATE t_poi SET need_reservation = 1,
       reservation_channel = '莫高窟参观预约网（官网 / 微信小程序）',
       reservation_note = '旺季需提前 1 个月预约，A 类票紧俏'
 WHERE poi_name LIKE '%莫高窟%';

-- -----------------------------------------------------------------------------
-- 5. 校验
-- -----------------------------------------------------------------------------
SELECT 't_user_preference_memory' AS table_name, COUNT(*) AS rows_cnt FROM t_user_preference_memory
UNION ALL SELECT 't_trip_graph', COUNT(*) FROM t_trip_graph
UNION ALL SELECT 't_poi(需预约)', COUNT(*) FROM t_poi WHERE need_reservation = 1;

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================================
-- 回滚（如需）：
--   DROP TABLE IF EXISTS t_user_preference_memory;
--   DROP TABLE IF EXISTS t_trip_graph;
--   ALTER TABLE t_poi DROP COLUMN need_reservation, DROP COLUMN reservation_channel, DROP COLUMN reservation_note;
-- =============================================================================
