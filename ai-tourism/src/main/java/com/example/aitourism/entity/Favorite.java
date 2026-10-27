package com.example.aitourism.entity;

import lombok.Data;
import java.time.LocalDateTime;

@Data
public class Favorite {
    private Long id;
    private String userId;
    private Long poiId;
    private String poiName;
    private String cityName;
    private LocalDateTime createdTime;
}
