package com.example.aitourism.entity;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * 酒店价格快照实体（t_hotel_price_snapshot）。
 *
 * <p>OTA 官方房价 API 均要求企业分销资质（个人开发者无法申请），
 * 因此采用「快照表」方案：每季度从主流 OTA 平台采集各热门城市
 * 经济/舒适/高档三档代表酒店价格落库，预算引擎查表取价，
 * UI 展示时携带来源与采集日期——与景点门票库同一方法论。
 */
@Data
public class HotelPriceSnapshot {

    private Long id;

    /** 城市名（不带「市」后缀） */
    private String cityName;

    /** 档次：economy / comfort / premium */
    private String tier;

    /** 该档次参考房价（元/晚） */
    private BigDecimal pricePerNight;

    /** 代表性酒店（用于展示快照来源） */
    private String sampleHotel;

    /** 快照来源口径，如「OTA公开报价整理」 */
    private String source;

    /** 采集日期（快照可溯源性的关键字段） */
    private LocalDate collectedDate;

    private LocalDateTime createdTime;
}
