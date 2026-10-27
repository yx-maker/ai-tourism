package com.example.aitourism.service;

import com.example.aitourism.entity.Budget;

import java.util.List;

public interface BudgetService {
    /**
     * 行程预算分析：优先用 LLM 结构化提取，规则引擎兜底，结果落库。
     * @param sessionId 会话ID
     * @param userId 用户ID
     * @param itineraryText AI 生成的行程文本
     * @return 预算分析结果
     */
    Budget analyze(String sessionId, String userId, String itineraryText);
    Budget getBySession(String sessionId);
    List<Budget> recent(String userId, Integer limit);
}
