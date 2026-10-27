package com.example.aitourism.service.impl;

import com.example.aitourism.service.PriceProxyService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * 火车票价通用解析器测试 —— 第三方聚合 API 响应结构的兼容性证明。
 *
 * <p>背景：聚合数据（juhe）与极速数据（jisu）的响应结构不同、字段名也可能调整，
 * 解析器采用「按席别语义递归提取」策略而非硬编码字段路径。
 * 本测试用多种典型响应结构验证兼容性（含聚合数据官方 fapigw 的 prices 数组结构）。
 */
class PriceProxyServiceParseTest {

    private final PriceProxyServiceImpl service = new PriceProxyServiceImpl(null, null);
    private final ObjectMapper om = new ObjectMapper();

    @Test
    @DisplayName("juhe 风格（ed/yd/yz 缩写键）→ 正确提取各席别票价")
    void shouldParseJuheStyleResponse() throws Exception {
        String json = """
                {"resultcode":"200","reason":"success","result":{"list":[
                  {"station_train_code":"G87","start_time":"08:12","ed":"619.0","yd":"1011.0","yz":"300.0"}
                ]}}
                """;
        List<PriceProxyService.SeatQuote> quotes = service.parseQuotes(om.readTree(json));

        assertTrue(quotes.stream().anyMatch(q -> "二等座".equals(q.seatType())
                && q.price().compareTo(new java.math.BigDecimal("619.0")) == 0), "应提取二等座 619 元");
        assertTrue(quotes.stream().anyMatch(q -> "一等座".equals(q.seatType())), "应提取一等座");
        assertTrue(quotes.stream().anyMatch(q -> "硬座".equals(q.seatType())), "应提取硬座");
        assertEquals("G87", quotes.get(0).trainCode(), "应提取车次号");
    }

    @Test
    @DisplayName("jisu 风格（priceed/priceyw1 前缀键）→ 正确提取各席别票价")
    void shouldParseJisuStyleResponse() throws Exception {
        String json = """
                {"status":0,"msg":"ok","result":{"list":[
                  {"trainno":"D856","priceed":"285","priceyd":"457","priceyw1":"499","pricewz":"285"}
                ]}}
                """;
        List<PriceProxyService.SeatQuote> quotes = service.parseQuotes(om.readTree(json));

        assertTrue(quotes.stream().anyMatch(q -> "二等座".equals(q.seatType())
                && q.price().intValue() == 285));
        assertTrue(quotes.stream().anyMatch(q -> "硬卧".equals(q.seatType())
                && q.price().intValue() == 499));
        assertTrue(quotes.stream().anyMatch(q -> "无座".equals(q.seatType())));
    }

    @Test
    @DisplayName("中文键名风格（二等座/硬卧）→ 正确提取，空值跳过")
    void shouldParseChineseKeyResponse() throws Exception {
        String json = """
                {"result":[{"车次":"K1140","出发时间":"09:30","商务座":"","二等座":"","硬卧":"398","硬座":"108"}]}
                """;
        List<PriceProxyService.SeatQuote> quotes = service.parseQuotes(om.readTree(json));

        assertEquals(2, quotes.size(), "空值席位应被跳过，只剩硬卧/硬座");
        assertTrue(quotes.stream().allMatch(q -> q.price().intValue() > 0));
        assertTrue(quotes.stream().anyMatch(q -> "硬卧".equals(q.seatType()) && q.price().intValue() == 398));
        assertTrue(quotes.stream().anyMatch(q -> "硬座".equals(q.seatType()) && q.price().intValue() == 108));
    }

    @Test
    @DisplayName("余票数量等非价格字段不应被误提取为票价")
    void shouldNotParseRemainingTicketCountsAsPrices() throws Exception {
        // 旧版接口用 *_num 表示余票数量（如 ed_num= "有"），不应进入票价
        String json = """
                {"result":{"list":[{"ed_num":"有","yw_num":"12","wz_num":"无","ed":"523"}]}}
                """;
        List<PriceProxyService.SeatQuote> quotes = service.parseQuotes(om.readTree(json));

        assertEquals(1, quotes.size(), "只有 ed=523 是票价，实际=" + quotes);
        assertEquals("二等座", quotes.get(0).seatType());
    }

    @Test
    @DisplayName("聚合数据官方结构 prices:[{seat_name, price, num}] → 席别文本值正确配对票价")
    void shouldParseJuheOfficialPricesArray() throws Exception {
        // 官方 fapigw/train/query 响应结构（阿里云市场文档 cmapi00071761）
        String json = """
                {"reason":"success","error_code":0,"result":{"lists":[
                  {"train_no":"G25","departure_station":"北京南","arrival_station":"苏州北",
                   "depart_time":"18:04","arrival_time":"22:32","duration":"04:28",
                   "enable_booking":"Y","train_flags":"复兴号",
                   "prices":[
                     {"seat_name":"二等座","price":"553.0","num":"3"},
                     {"seat_name":"一等座","price":"933.0","num":"有"},
                     {"seat_name":"商务座","price":"1853.0","num":"11"}
                   ]}
                ]}}
                """;
        List<PriceProxyService.SeatQuote> quotes = service.parseQuotes(om.readTree(json));

        assertEquals(3, quotes.size(), "应提取 3 个席别，实际=" + quotes);
        assertTrue(quotes.stream().anyMatch(q -> "二等座".equals(q.seatType())
                && q.price().compareTo(new java.math.BigDecimal("553.0")) == 0));
        assertTrue(quotes.stream().anyMatch(q -> "一等座".equals(q.seatType())
                && q.price().intValue() == 933));
        assertTrue(quotes.stream().anyMatch(q -> "商务座".equals(q.seatType())
                && q.price().intValue() == 1853));
        assertEquals("G25", quotes.get(0).trainCode(), "应提取车次号");
        assertEquals("18:04", quotes.get(0).departTime(), "应提取出发时间");
        // num（余票）不得被误提取为票价：总条数=3 而非 6
        assertTrue(quotes.stream().noneMatch(q -> q.price().intValue() == 3),
                "余票数量 3 不应被当作票价");
    }

    @Test
    @DisplayName("官方结构边界：price 缺失/为 0 时跳过，不产出无效报价")
    void shouldSkipInvalidPriceEntries() throws Exception {
        String json = """
                {"result":{"lists":[
                  {"train_no":"G101","depart_time":"07:00",
                   "prices":[
                     {"seat_name":"二等座","price":"","num":"无"},
                     {"seat_name":"一等座","price":"0","num":"2"},
                     {"seat_name":"硬座","num":"12"},
                     {"seat_name":"商务座","price":"1748","num":"5"}
                   ]}
                ]}}
                """;
        List<PriceProxyService.SeatQuote> quotes = service.parseQuotes(om.readTree(json));

        assertEquals(1, quotes.size(), "只有商务座 1748 有效，实际=" + quotes);
        assertEquals("商务座", quotes.get(0).seatType());
        assertEquals(1748, quotes.get(0).price().intValue());
    }

    @Test
    @DisplayName("席别键名映射覆盖常见缩写")
    void shouldMapSeatKeys() {
        assertEquals("二等座", PriceProxyServiceImpl.mapSeatKey("priceed"));
        assertEquals("一等座", PriceProxyServiceImpl.mapSeatKey("priceyd"));
        assertEquals("硬座", PriceProxyServiceImpl.mapSeatKey("priceyz"));
        assertEquals("硬卧", PriceProxyServiceImpl.mapSeatKey("priceyw1"));
        assertEquals("软卧", PriceProxyServiceImpl.mapSeatKey("priceyw2"));
        assertEquals("商务座", PriceProxyServiceImpl.mapSeatKey("priceswz"));
        assertEquals("无座", PriceProxyServiceImpl.mapSeatKey("pricewz"));
        assertEquals("二等座", PriceProxyServiceImpl.mapSeatKey("二等座票价"));
        assertNull(PriceProxyServiceImpl.mapSeatKey("start_time"));
        assertNull(PriceProxyServiceImpl.mapSeatKey("train_no"));
    }

    @Test
    @DisplayName("城市名归一化：去掉「市」后缀")
    void shouldNormalizeCity() {
        assertEquals("成都", PriceProxyServiceImpl.normalizeCity("成都市"));
        assertEquals("成都", PriceProxyServiceImpl.normalizeCity(" 成都 "));
        assertNull(PriceProxyServiceImpl.normalizeCity(null));
    }

    @Test
    @DisplayName("未配置 API Key → trainApiEnabled=false，不发起外部调用")
    void shouldBeDisabledWithoutKey() {
        // provider/api-key 均未注入（@Value 默认空串）
        assertFalse(service.trainApiEnabled());
        // 本地实爬表未覆盖的线路（且 API 未启用）→ 返回空列表，由调用方降级
        assertTrue(service.trainQuotes("攀枝花", "绵阳", "2026-10-22").isEmpty(),
                "无任何数据源命中时应返回空列表");
    }

    @Test
    @DisplayName("本地 12306 实爬票价表（最高优先级层）→ 未启用 API 也能返回真实票价")
    void shouldReturnLocalScrapedPrices() {
        // classpath:price/train_price_local.json 由 12306 实爬生成（15 城两两组合）
        assertTrue(service.localTrainPriceRoutes() >= 80,
                "本地票价表应覆盖 85 对线路（双向 170 键）");

        // API 未启用，但本地表命中 → 直接返回真实票价，无需外部调用
        List<PriceProxyService.SeatQuote> quotes = service.trainQuotes("北京", "上海", "2026-11-06");
        assertFalse(quotes.isEmpty(), "京沪线应命中本地票价表");
        assertTrue(quotes.stream().anyMatch(q -> "二等座".equals(q.seatType())
                && q.price().intValue() >= 300 && q.price().intValue() <= 600),
                "京沪二等座应在合理区间（实爬浮动价 338 左右）");
        assertTrue(quotes.stream().anyMatch(q -> "商务座".equals(q.seatType())
                && q.price().intValue() >= 1500));

        // 反向线路票价对称，同样命中
        List<PriceProxyService.SeatQuote> reverse = service.trainQuotes("上海", "北京", "2026-11-06");
        assertFalse(reverse.isEmpty(), "反向线路（上海→北京）也应命中本地票价表");

        // 同城 / 无效参数 → 空
        assertTrue(service.trainQuotes("北京", "北京", "2026-11-06").isEmpty());
        assertTrue(service.trainQuotes("北京", "上海", null).isEmpty());
    }
}
