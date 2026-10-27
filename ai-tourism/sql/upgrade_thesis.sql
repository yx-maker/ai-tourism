-- 毕业论文改造：新增收藏表 / 用户偏好表 / 预算分析表，t_poi 增加门票价格字段
use aitourism;

-- 1. 景点表增加门票价格字段（景点管理模块：门票价格）
ALTER TABLE t_poi ADD COLUMN ticket_price DECIMAL(10,2) NOT NULL DEFAULT 0 COMMENT '门票价格（元）' AFTER poi_rankInChina;

-- 2. 收藏表（用户收藏景点）
CREATE TABLE IF NOT EXISTS t_favorite (
    id bigint auto_increment primary key,
    user_id varchar(64) not null comment '用户ID',
    poi_id bigint not null comment '景点ID',
    poi_name varchar(255) not null comment '景点名称',
    city_name varchar(255) null comment '城市名称',
    created_time datetime default CURRENT_TIMESTAMP not null comment '收藏时间',
    constraint uk_user_poi unique (user_id, poi_id)
) comment '用户收藏表';

-- 3. 用户偏好表（个性化推荐数据支撑）
CREATE TABLE IF NOT EXISTS t_user_preference (
    id bigint auto_increment primary key,
    user_id varchar(64) not null comment '用户ID',
    budget_min decimal(10,2) default 0 comment '预算下限（元）',
    budget_max decimal(10,2) default 0 comment '预算上限（元）',
    travel_style varchar(255) null comment '出行风格：休闲/紧凑/奢华/穷游',
    interests varchar(255) null comment '兴趣标签：历史古迹/自然风光/美食/购物/文艺/亲子',
    pace varchar(32) null comment '行程节奏：轻松/适中/紧凑',
    companion varchar(64) null comment '同行人：独自/情侣/家庭/朋友/团队',
    created_time datetime default CURRENT_TIMESTAMP not null,
    modify_time datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP,
    constraint uk_user_pref unique (user_id)
) comment '用户偏好表';

-- 4. 预算分析表（预算分析模块）
CREATE TABLE IF NOT EXISTS t_budget (
    id bigint auto_increment primary key,
    session_id varchar(64) not null comment '会话ID',
    user_id varchar(64) not null comment '用户ID',
    total_budget decimal(12,2) default 0 comment '总预算（元）',
    transport_cost decimal(10,2) default 0 comment '交通费用（元）',
    accommodation_cost decimal(10,2) default 0 comment '住宿费用（元）',
    food_cost decimal(10,2) default 0 comment '餐饮费用（元）',
    ticket_cost decimal(10,2) default 0 comment '门票费用（元）',
    other_cost decimal(10,2) default 0 comment '其他费用（元）',
    days int default 0 comment '行程天数',
    detail_json text null comment '每日预算明细JSON',
    created_time datetime default CURRENT_TIMESTAMP not null,
    constraint uk_session_budget unique (session_id)
) comment '行程预算分析表';

-- 为收藏表和预算表建立索引
CREATE INDEX idx_favorite_user ON t_favorite(user_id);
CREATE INDEX idx_budget_user ON t_budget(user_id);

show tables;
