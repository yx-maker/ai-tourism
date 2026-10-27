package com.example.aitourism.entity;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 火车票价缓存实体（t_train_price_cache）。
 *
 * <p>论文「数据真实性分层」设计的一部分：本表<b>只缓存真实 API（聚合数据/极速数据，
 * 同步 12306）返回的票价</b>，不存任何模型估算值。无 API Key 时本表为空，
 * 预算引擎自动降级到系数估算并在费用明细中标注「系统估算」。
 */
@Data
public class TrainPriceCache {

    private Long id;

    /** 出发城市 */
    private String originCity;

    /** 到达城市 */
    private String destCity;

    /** 出发日期 yyyy-MM-dd（12306 预售期 14 天内才查得到） */
    private String departDate;

    /** 席别：二等座 / 一等座 / 硬卧 / 硬座 / 商务座 / 无座 等 */
    private String seatType;

    /** 单程真实票价（元） */
    private BigDecimal price;

    /** 数据提供方：juhe / jisu */
    private String provider;

    /** 抓取时间（缓存 24 小时过期） */
    private LocalDateTime fetchedAt;
}
