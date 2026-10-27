package com.example.aitourism.entity;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 旅行计划实体（t_travel_plan）。
 *
 * <p>行程持久化：把会话中生成的攻略固化为可管理的「我的计划」，
 * 支持编辑后由服务端确定性重算预算（乐观锁防并发覆盖）。
 */
@Data
public class TravelPlan {

    private Long id;

    /** 计划ID（对外唯一，UUID） */
    private String planId;

    /** 归属用户ID */
    private String userId;

    /** 来源会话ID */
    private String sessionId;

    /** 计划标题 */
    private String title;

    /** 目的地城市 */
    private String destCity;

    /** 出发城市 */
    private String originCity;

    /** 行程天数 */
    private Integer days;

    /** 用户预算（元） */
    private BigDecimal budgetAmount;

    /** 行程攻略全文（markdown） */
    private String content;

    /** 路线 JSON（每日景点坐标，地图渲染用） */
    private String dailyRoutes;

    /** 预算分析快照（五类分项 + 带价格来源的明细） */
    private String budgetJson;

    /** 状态：ACTIVE / ARCHIVED */
    private String status;

    /** 乐观锁版本号（每次更新 +1） */
    private Integer version;

    private LocalDateTime createdTime;

    private LocalDateTime modifyTime;
}
