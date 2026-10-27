package com.example.aitourism.entity;

import lombok.Data;
import java.time.LocalDateTime;
import java.math.BigDecimal;

@Data
public class UserPreference {
    private Long id;
    private String userId;
    private BigDecimal budgetMin;
    private BigDecimal budgetMax;
    private String travelStyle;
    private String interests;
    private String pace;
    private String companion;
    private LocalDateTime createdTime;
    private LocalDateTime modifyTime;
}
