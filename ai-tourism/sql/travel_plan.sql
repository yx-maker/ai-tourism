-- =============================================================================
-- 旅行计划持久化（开题报告数据库设计中的「行程表 / 行程详情表」落地）
--
-- 解决的问题：原系统行程只存在于会话 JSON 中，刷新/换设备即丢失，
-- 用户无法管理「我的计划」，也无法在生成后调整行程并重新计算预算。
--
-- 设计要点：
--   1. content 保存攻略全文（markdown），daily_routes 保存结构化路线（地图渲染用）
--   2. budget_json 保存预算分析快照（五类分项 + 带价格来源的明细），与行程解耦
--   3. version 乐观锁：编辑保存时校验版本，冲突返回 409，防止并发覆盖
--   4. 编辑保存后由服务端确定性重算预算（BudgetService.analyze），不信任前端传来的金额
-- =============================================================================

use aitourism;

create table if not exists t_travel_plan
(
    id            bigint auto_increment               primary key,
    plan_id       varchar(64)                         not null comment '计划ID(对外唯一)',
    user_id       varchar(64)                         not null comment '归属用户ID',
    session_id    varchar(64)                         null comment '来源会话ID',
    title         varchar(128)                        not null comment '计划标题',
    dest_city     varchar(64)                         null comment '目的地城市',
    origin_city   varchar(64)                         null comment '出发城市',
    days          int                                 not null default 1 comment '行程天数',
    budget_amount decimal(10, 2)                      null comment '用户预算(元)',
    content       mediumtext                          null comment '行程攻略全文(markdown)',
    daily_routes  text                                null comment '路线JSON(每日景点坐标, 地图用)',
    budget_json   text                                null comment '预算分析快照(五类分项+明细+价格来源)',
    status        varchar(16)                         not null default 'ACTIVE' comment '状态: ACTIVE/ARCHIVED',
    version       int                                 not null default 0 comment '乐观锁版本号(每次更新+1)',
    created_time  datetime default CURRENT_TIMESTAMP  not null comment '创建时间',
    modify_time   datetime default CURRENT_TIMESTAMP  not null on update CURRENT_TIMESTAMP comment '更新时间',
    constraint uk_plan_id unique (plan_id),
    key idx_user_modify (user_id, modify_time)
) comment '旅行计划表(行程持久化)';
