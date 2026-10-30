package com.example.aitourism.service;

import com.example.aitourism.entity.HotelPriceSnapshot;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

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

    /**
     * 查询城市对的真实交通时长（12306 实爬车次历时，按类型取最快一趟）。
     *
     * <p>数据源：classpath:price/train_duration_local.json（离线真实数据，
     * 由 script/scrape/fetch_train_duration_http.py 抓取）。
     * 未收录的城市对返回空 map，由调用方降级到速度模型估算并标注「估算」。
     *
     * @param origin 出发城市
     * @param dest   到达城市
     * @return 类别 → 最快车次历时（可能为空 map，绝不为 null）
     */
    Map<String, DurationQuote> trainDurations(String origin, String dest);

    /**
     * 查询城市对的「车次级」报价：同一趟车的各席别票价 + 该车官方历时。
     *
     * <p>为什么必须车次级：票价与时长若分开取，会拼出现实中不存在的组合——
     * 例如广州-长沙「二等座 ¥122」其实是 D 字头动集（历时 7~8 小时）的价格，
     * 而「最快高铁 1 小时 57 分」来自 G6018（二等座 ¥319），两者一拼就成了
     * 「一百多块 2 小时到长沙」。车次级绑定后，选了哪趟车的席别，时长就一定是那趟车的。
     *
     * @param origin 出发城市
     * @param dest   到达城市
     * @return 类别（高铁动车 / 普速）→ 代表车次；未收录返回空 map（绝不为 null）
     */
    Map<String, TrainOption> trainOptions(String origin, String dest);

    /** 席别报价 */
    record SeatQuote(String seatType, BigDecimal price, String trainCode, String departTime) {}

    /**
     * 一趟车的完整报价：席别价格与官方历时同源。
     *
     * @param kind      高铁动车 / 普速
     * @param trainCode 车次号
     * @param depart    出发时刻
     * @param arrive    到达时刻
     * @param lishi     官方历时 HH:mm
     * @param minutes   历时分钟
     * @param seats     席别 → 单程票价
     */
    record TrainOption(String kind, String trainCode, String depart, String arrive,
                       String lishi, int minutes, Map<String, BigDecimal> seats) {}

    /** 酒店快照 */
    record HotelSnapshot(BigDecimal pricePerNight, String sampleHotel, String source, LocalDate collectedDate) {}

    /**
     * 某类车次的最快一趟真实历时。
     *
     * @param kind      高铁动车 / 普速
     * @param trainCode 车次号（如 G2942）
     * @param depart    出发时刻 HH:mm
     * @param arrive    到达时刻 HH:mm
     * @param lishi     12306 官方历时 HH:mm
     * @param minutes   折合分钟
     */
    record DurationQuote(String kind, String trainCode, String depart, String arrive,
                         String lishi, int minutes) {}
}
