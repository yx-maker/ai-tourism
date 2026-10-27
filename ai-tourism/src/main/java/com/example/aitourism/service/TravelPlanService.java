package com.example.aitourism.service;

import com.example.aitourism.entity.TravelPlan;

import java.util.List;
import java.util.Map;

/**
 * 旅行计划服务（行程持久化，开题报告数据库设计「行程表」落地）。
 *
 * <p>核心能力：
 * <ul>
 *   <li>从会话保存计划：攻略全文 + 结构化路线 + 预算快照</li>
 *   <li>计划管理：列表 / 详情 / 归档删除</li>
 *   <li>编辑重算：乐观锁校验版本，行程内容变化时由服务端确定性重算预算</li>
 * </ul>
 */
public interface TravelPlanService {

    /** 从会话保存为旅行计划（幂等保护：同一会话重复保存会更新已有计划） */
    TravelPlan saveFromSession(String sessionId, String userId, String titleOverride);

    /** 我的计划列表（分页，按修改时间倒序） */
    Map<String, Object> list(String userId, Integer page, Integer pageSize);

    /** 计划详情（含归属校验） */
    TravelPlan detail(String planId, String userId);

    /**
     * 更新计划（乐观锁）。
     *
     * @param expectedVersion 前端持有的版本号，不匹配返回 409 错误
     * @param content         新的行程内容（变化时触发服务端预算重算）
     * @return 更新后的计划
     */
    TravelPlan update(String planId, String userId, Integer expectedVersion,
                      String title, Integer days, java.math.BigDecimal budgetAmount,
                      String content, String dailyRoutes);

    /** 归档（软删除）计划 */
    boolean archive(String planId, String userId);
}
