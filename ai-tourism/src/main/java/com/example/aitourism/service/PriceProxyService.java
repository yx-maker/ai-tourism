package com.example.aitourism.service;

import com.example.aitourism.entity.HotelPriceSnapshot;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

/**
 * 真实价格代理服务（预算系统「数据真实性分层」的第一级：RealApi / 第二级：Snapshot）。
 *
 * <p>设计原则：
 * <ul>
 *   <li><b>拿不到就不冒充</b>：未配置 API Key 或查询失败时返回空/null，
 *       由调用方降级到系数估算，费用明细中标注「系统估算」</li>
 *   <li><b>只缓存真实数据</b>：t_train_price_cache 只写真实 API 返回的票价</li>
 *   <li><b>快照可溯源</b>：酒店快照携带来源与采集日期</li>
 * </ul>
 */
public interface PriceProxyService {

    /** 火车票真实票价 API 是否已配置（provider + api-key 均非空） */
    boolean trainApiEnabled();

    /**
     * 查询站到站火车各席别真实票价（同步 12306）。
     *
     * @param origin 出发城市（如「广州」，自动去「市」后缀）
     * @param dest   到达城市（如「成都」）
     * @param date   出发日期 yyyy-MM-dd（需在 12306 预售期 14 天内）
     * @return 席别报价列表；未配置 Key / 查询失败 / 预售期外返回空列表
     */
    List<SeatQuote> trainQuotes(String origin, String dest, String date);

    /**
     * 查询城市某档次的酒店快照价。
     *
     * @param city 城市名
     * @param tier economy / comfort / premium
     * @return 快照价；无数据返回 null（调用方降级到档次默认价并标注估算）
     */
    HotelSnapshot hotelPrice(String city, String tier);

    /** 席别报价 */
    record SeatQuote(String seatType, BigDecimal price, String trainCode, String departTime) {}

    /** 酒店快照 */
    record HotelSnapshot(BigDecimal pricePerNight, String sampleHotel, String source, LocalDate collectedDate) {}
}
