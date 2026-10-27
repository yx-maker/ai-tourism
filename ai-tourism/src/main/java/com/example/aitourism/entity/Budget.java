package com.example.aitourism.entity;

import lombok.Data;
import java.time.LocalDateTime;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

@Data
public class Budget {
    private Long id;
    private String sessionId;
    private String userId;
    private BigDecimal totalBudget;
    private BigDecimal transportCost;
    private BigDecimal accommodationCost;
    private BigDecimal foodCost;
    private BigDecimal ticketCost;
    private BigDecimal otherCost;
    private Integer days;
    private String detailJson;
    private LocalDateTime createdTime;

    // ==================== 预算硬约束（预算反推规划） ====================

    /** 用户给定的总预算（元），null 表示未指定 */
    private BigDecimal userBudget;

    /** 预算达成状态：WITHIN_BUDGET / OVER_BUDGET / UNKNOWN */
    private String budgetStatus;

    /** 预算结余（元），负数表示超支 */
    private BigDecimal remainingBudget;

    /** 预算封套 JSON：分项上限与档次建议（预算反推结果） */
    private String envelopeJson;

    /** 出行方案 JSON：严格按预算生成的交通方式/住宿档次/天数节奏 */
    private String planJson;

    // 费用明细条目（不入库，序列化进 detailJson）
    private List<Map<String, Object>> detailItems;

    // 预算封套对象（不入库，序列化进 envelopeJson / planJson；不参与 JSON 响应）
    @com.fasterxml.jackson.annotation.JsonIgnore
    private com.example.aitourism.dto.budget.BudgetEnvelope envelope;
}
