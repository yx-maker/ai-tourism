package com.example.aitourism.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class Session {
    private Long id;
    private String sessionId;
    private String userName;
    private LocalDateTime createdTime;
    private LocalDateTime modifyTime;
    private String title;
    private String dailyRoutes;
    private String userId;

    /** 用户给定总预算（元），由 Python Agent 意图识别提取后回写；null 表示未指定 */
    private java.math.BigDecimal budgetAmount;

    /** 出发城市（用于大交通里程估算） */
    private String originCity;
}