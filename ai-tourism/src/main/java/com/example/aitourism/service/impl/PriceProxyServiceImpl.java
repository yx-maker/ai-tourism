package com.example.aitourism.service.impl;

import com.example.aitourism.entity.TrainPriceCache;
import com.example.aitourism.mapper.HotelPriceSnapshotMapper;
import com.example.aitourism.mapper.TrainPriceCacheMapper;
import com.example.aitourism.entity.HotelPriceSnapshot;
import com.example.aitourism.service.PriceProxyService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 真实价格代理服务实现。
 *
 * <h3>火车票（RealApi 层）</h3>
 * 票价查询按四层数据源逐级降级：
 * <ol>
 *   <li><b>本地实爬表</b>（classpath:price/train_price_local.json）：12306 官网实际抓取的
 *       15 城两两组合各席别最低价，离线可用、最高优先级</li>
 *   <li><b>t_train_price_cache</b>：近期真实 API 查询结果缓存（24h）</li>
 *   <li><b>第三方聚合 API</b>：实时查询，同步 12306 站到站各席别票价</li>
 *   <li>（本地表/缓存/API 均未命中时由预算引擎降级为系数估算）</li>
 * </ol>
 * 第三方 API 两种 provider：
 * <ul>
 *   <li>juhe（聚合数据·火车订票查询 id 817）：默认 https://apis.juhe.cn/fapigw/train/query</li>
 *   <li>jisu（极速数据）：默认 https://api.jisuapi.com/train/station2s</li>
 * </ul>
 * 两家返回结构不同且字段名可能调整，因此采用<b>通用递归解析器</b>
 * （见 {@link #parseQuotes(JsonNode)}）：按「席别语义」递归提取票价，
 * 兼容中文席别键名（二等座/硬卧…）与缩写键名（priceed/yw/wz…），
 * 对响应结构变化免疫；解析不到任何票价时视为失败，自动降级。
 *
 * <h3>酒店（Snapshot 层）</h3>
 * 直接查 t_hotel_price_snapshot 快照表（见 price_real_data.sql）。
 */
@Service
@Slf4j
public class PriceProxyServiceImpl implements PriceProxyService {

    private final TrainPriceCacheMapper trainPriceCacheMapper;
    private final HotelPriceSnapshotMapper hotelPriceSnapshotMapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /** 火车票 provider：juhe / jisu，留空表示不启用真实票价（降级系数估算） */
    @Value("${price.train.provider:}")
    private String trainProvider;

    /** 第三方 API Key（个人实名即可申请，见「真实价格数据源接入方案」文档） */
    @Value("${price.train.api-key:}")
    private String trainApiKey;

    /** 自定义 API 地址（留空按 provider 用默认地址） */
    @Value("${price.train.api-url:}")
    private String trainApiUrl;

    /** 缓存时长（小时），默认 24 */
    @Value("${price.train.cache-hours:24}")
    private int cacheHours;

    private static final String DEFAULT_JUHE_URL = "https://apis.juhe.cn/fapigw/train/query";
    private static final String DEFAULT_JISU_URL = "https://api.jisuapi.com/train/station2s";

    /** 本地真实票价表（12306 实爬，classpath:price/train_price_local.json），key = "城市A-城市B" */
    private static final String LOCAL_PRICE_RESOURCE = "/price/train_price_local.json";
    private static final String LOCAL_PRICE_PROVIDER = "local-12306";

    /** 本地真实车次历时表（12306 实爬，classpath:price/train_duration_local.json），
     *  key = "城市A-城市B"，value = {"高铁动车": {train_code, depart, arrive, lishi, minutes}, "普速": {...}} */
    private static final String LOCAL_DURATION_RESOURCE = "/price/train_duration_local.json";

    /**
     * 车次级绑定表（票价 + 历时同源，classpath:price/train_binding_local.json）。
     *
     * <p>格式：{"广州-长沙": {"高铁动车": {train_code, depart, arrive, lishi, minutes,
     * seats:{二等座:319, 一等座:454}}, "普速": {...}}}
     * 由 script/scrape/fetch_train_binding_http.py 抓取，是票价与时长唯一自洽的来源。
     */
    private static final String LOCAL_BINDING_RESOURCE = "/price/train_binding_local.json";

    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    /** 本地票价表缓存；classpath 资源缺失或解析失败时为空表（不影响后续层级） */
    private final Map<String, Map<String, BigDecimal>> localTrainPrices = loadLocalTrainPrices();

    /** 本地车次历时表缓存（可选资源；缺失时时长层降级为速度模型估算） */
    private final Map<String, Map<String, DurationQuote>> localTrainDurations = loadLocalTrainDurations();

    /** 车次级绑定表缓存：票价与历时同源，优先于「分开取」的两张旧表 */
    private final Map<String, Map<String, TrainOption>> localTrainOptions = loadLocalTrainOptions();

    /** 加载 classpath 下的 12306 实爬票价表（可选资源，格式 {"北京-上海": {"二等座": 338, ...}}） */
    private static Map<String, Map<String, BigDecimal>> loadLocalTrainPrices() {
        try (var in = PriceProxyServiceImpl.class.getResourceAsStream(LOCAL_PRICE_RESOURCE)) {
            if (in == null) {
                return Map.of();
            }
            JsonNode root = new ObjectMapper().readTree(in);
            Map<String, Map<String, BigDecimal>> table = new ConcurrentHashMap<>();
            root.fields().forEachRemaining(route -> {
                Map<String, BigDecimal> seats = new LinkedHashMap<>();
                route.getValue().fields().forEachRemaining(seat -> {
                    JsonNode v = seat.getValue();
                    if (v.isNumber()) {
                        BigDecimal val = v.decimalValue();
                        if (val.signum() > 0 && val.compareTo(BigDecimal.valueOf(5000)) <= 0) {
                            seats.put(seat.getKey(), val);
                        }
                    }
                });
                if (!seats.isEmpty()) {
                    table.put(route.getKey(), seats);
                }
            });
            return table;
        } catch (Exception e) {
            return Map.of();
        }
    }

    /** 加载 classpath 下的 12306 实爬车次历时表（可选资源） */
    private static Map<String, Map<String, DurationQuote>> loadLocalTrainDurations() {
        try (var in = PriceProxyServiceImpl.class.getResourceAsStream(LOCAL_DURATION_RESOURCE)) {
            if (in == null) {
                return Map.of();
            }
            JsonNode root = new ObjectMapper().readTree(in);
            Map<String, Map<String, DurationQuote>> table = new ConcurrentHashMap<>();
            root.fields().forEachRemaining(route -> {
                Map<String, DurationQuote> kinds = new LinkedHashMap<>();
                route.getValue().fields().forEachRemaining(kind -> {
                    JsonNode q = kind.getValue();
                    if (!q.isObject()) {
                        return;
                    }
                    JsonNode mins = q.get("minutes");
                    if (mins == null || !mins.isNumber() || mins.asInt() <= 0) {
                        return;
                    }
                    kinds.put(kind.getKey(), new DurationQuote(
                            kind.getKey(),
                            q.get("train_code") == null ? null : q.get("train_code").asText(),
                            q.get("depart") == null ? null : q.get("depart").asText(),
                            q.get("arrive") == null ? null : q.get("arrive").asText(),
                            q.get("lishi") == null ? null : q.get("lishi").asText(),
                            mins.asInt()));
                });
                if (!kinds.isEmpty()) {
                    table.put(route.getKey(), kinds);
                }
            });
            return table;
        } catch (Exception e) {
            return Map.of();
        }
    }

    /** 加载车次级绑定表（票价与历时同源） */
    private static Map<String, Map<String, TrainOption>> loadLocalTrainOptions() {
        try (var in = PriceProxyServiceImpl.class.getResourceAsStream(LOCAL_BINDING_RESOURCE)) {
            if (in == null) {
                return Map.of();
            }
            JsonNode root = new ObjectMapper().readTree(in);
            Map<String, Map<String, TrainOption>> table = new ConcurrentHashMap<>();
            root.fields().forEachRemaining(route -> {
                Map<String, TrainOption> kinds = new LinkedHashMap<>();
                route.getValue().fields().forEachRemaining(kindNode -> {
                    JsonNode q = kindNode.getValue();
                    if (!q.isObject()) {
                        return;
                    }
                    JsonNode mins = q.get("minutes");
                    if (mins == null || !mins.isNumber() || mins.asInt() <= 0) {
                        return;
                    }
                    Map<String, BigDecimal> seats = new LinkedHashMap<>();
                    JsonNode seatNode = q.get("seats");
                    if (seatNode != null && seatNode.isObject()) {
                        seatNode.fields().forEachRemaining(seat -> {
                            JsonNode v = seat.getValue();
                            if (v.isNumber() && v.decimalValue().signum() > 0) {
                                seats.put(seat.getKey(), v.decimalValue());
                            }
                        });
                    }
                    kinds.put(kindNode.getKey(), new TrainOption(
                            kindNode.getKey(),
                            q.get("train_code") == null ? null : q.get("train_code").asText(),
                            q.get("depart") == null ? null : q.get("depart").asText(),
                            q.get("arrive") == null ? null : q.get("arrive").asText(),
                            q.get("lishi") == null ? null : q.get("lishi").asText(),
                            mins.asInt(),
                            seats));
                });
                if (!kinds.isEmpty()) {
                    table.put(route.getKey(), kinds);
                }
            });
            return table;
        } catch (Exception e) {
            return Map.of();
        }
    }

    @Override
    public Map<String, TrainOption> trainOptions(String origin, String dest) {
        String from = normalizeCity(origin);
        String to = normalizeCity(dest);
        if (from == null || to == null || from.equals(to)) {
            return Map.of();
        }
        Map<String, TrainOption> opts = localTrainOptions.get(from + "-" + to);
        if (opts == null) {
            opts = localTrainOptions.get(to + "-" + from);
        }
        if (opts == null || opts.isEmpty()) {
            return Map.of();
        }
        log.info("[PRICE] 车次级报价命中: {}→{} {}", from, to, opts.keySet());
        return opts;
    }

    /** 本地车次级绑定表覆盖的线路数 */
    public int localTrainOptionRoutes() {
        return localTrainOptions.size();
    }

    /** 本地票价表覆盖的线路数（供监控/日志用） */
    public int localTrainPriceRoutes() {
        return localTrainPrices.size();
    }

    /** 本地车次历时表覆盖的线路数（供监控/日志用） */
    public int localTrainDurationRoutes() {
        return localTrainDurations.size();
    }

    public PriceProxyServiceImpl(TrainPriceCacheMapper trainPriceCacheMapper,
                                 HotelPriceSnapshotMapper hotelPriceSnapshotMapper) {
        this.trainPriceCacheMapper = trainPriceCacheMapper;
        this.hotelPriceSnapshotMapper = hotelPriceSnapshotMapper;
    }

    @Override
    public boolean trainApiEnabled() {
        return trainProvider != null && !trainProvider.isBlank()
                && trainApiKey != null && !trainApiKey.isBlank();
    }

    // ==================================================================================
    // 火车票真实票价
    // ==================================================================================

    @Override
    public List<SeatQuote> trainQuotes(String origin, String dest, String date) {
        String from = normalizeCity(origin);
        String to = normalizeCity(dest);
        if (from == null || to == null || from.equals(to) || date == null || date.isBlank()) {
            return List.of();
        }

        // 0) 车次级绑定表（离线真实数据，最高优先级）：每个席别都带所属车次，
        //    调用方据此取时长不会再跨车次错配。不依赖 trainApiEnabled。
        Map<String, TrainOption> bound = trainOptions(from, to);
        if (!bound.isEmpty()) {
            List<SeatQuote> boundQuotes = new java.util.ArrayList<>();
            bound.values().forEach(o -> o.seats().forEach((seat, price) ->
                    boundQuotes.add(new SeatQuote(seat, price, o.trainCode(), o.depart()))));
            if (!boundQuotes.isEmpty()) {
                log.info("[PRICE] 火车票价命中车次级绑定表: {}→{} 共{}个席别（票价与历时同源）",
                        from, to, boundQuotes.size());
                return boundQuotes;
            }
        }

        // 旧票价表（train_price_local.json）已停用：它按「城市对 + 席别」跨车次取最低价，
        // 席别可能来自不同车次（广州-长沙二等座 ¥122 出自 D 字头动集，历时 7~8 小时），
        // 与时长表拼在一起会得出「一百多块 2 小时到长沙」这种现实中不存在的组合。
        // 未收录车次级报价的线路，宁可降级为系数估算并标注「估算」，也不冒充真实数据。
        if (!localTrainPrices.isEmpty() && localTrainPrices.containsKey(from + "-" + to)) {
            log.info("[PRICE] {}→{} 仅有旧票价表（席别可能跨车次），已弃用，降级估算", from, to);
        }

        if (!trainApiEnabled()) {
            log.debug("[PRICE] 本地表未命中且未配置火车票 API（price.train.provider/api-key），跳过真实票价层");
            return List.of();
        }

        // 1) 缓存优先（24 小时内直接复用，节省 API 次数）
        try {
            LocalDateTime freshAfter = LocalDateTime.now().minusHours(Math.max(cacheHours, 1));
            List<TrainPriceCache> cached = trainPriceCacheMapper.findFresh(from, to, date, freshAfter);
            if (!cached.isEmpty()) {
                log.info("[PRICE] 火车票价命中缓存: {}→{} {} 共{}条", from, to, date, cached.size());
                return cached.stream()
                        .map(c -> new SeatQuote(c.getSeatType(), c.getPrice(), null, null))
                        .toList();
            }
        } catch (Exception e) {
            log.warn("[PRICE] 火车票价缓存读取失败（继续查 API）: {}", e.getMessage());
        }

        // 2) 调用真实 API
        List<SeatQuote> quotes;
        try {
            quotes = callTrainApi(from, to, date);
        } catch (Exception e) {
            log.warn("[PRICE] 火车票 API 调用失败（降级系数估算）: {}→{} {} {}", from, to, date, e.getMessage());
            return List.of();
        }
        if (quotes.isEmpty()) {
            log.info("[PRICE] 火车票 API 未返回有效票价（可能超出预售期/无车次），降级系数估算: {}→{} {}", from, to, date);
            return List.of();
        }

        // 3) 写入缓存（只存真实 API 返回的票价）
        try {
            for (SeatQuote q : quotes) {
                TrainPriceCache cache = new TrainPriceCache();
                cache.setOriginCity(from);
                cache.setDestCity(to);
                cache.setDepartDate(date);
                cache.setSeatType(q.seatType());
                cache.setPrice(q.price());
                cache.setProvider(trainProvider.toLowerCase());
                trainPriceCacheMapper.upsert(cache);
            }
        } catch (Exception e) {
            log.warn("[PRICE] 火车票价缓存写入失败（不影响本次结果）: {}", e.getMessage());
        }
        log.info("[PRICE] 火车票价真实查询成功: {}→{} {} 共{}个席别", from, to, date, quotes.size());
        return quotes;
    }

    /** 按 provider 调用外部 API 并解析 */
    private List<SeatQuote> callTrainApi(String from, String to, String date) throws Exception {
        String provider = trainProvider.trim().toLowerCase();
        String url;
        Map<String, String> params = new LinkedHashMap<>();
        if ("jisu".equals(provider)) {
            url = (trainApiUrl == null || trainApiUrl.isBlank()) ? DEFAULT_JISU_URL : trainApiUrl.trim();
            params.put("appkey", trainApiKey);
            params.put("start", from);
            params.put("end", to);
            params.put("date", date);
        } else {
            // 默认 juhe（聚合数据 817 火车订票查询）
            // 参数口径见阿里云市场文档 cmapi00071761：
            // search_type 必填（1=站点名称）；departure_station/arrival_station 必填；date 仅允许 15 天内
            url = (trainApiUrl == null || trainApiUrl.isBlank()) ? DEFAULT_JUHE_URL : trainApiUrl.trim();
            params.put("key", trainApiKey);
            params.put("search_type", "1");
            params.put("departure_station", from);
            params.put("arrival_station", to);
            params.put("date", date);
        }
        StringBuilder sb = new StringBuilder(url);
        if (!params.isEmpty()) {
            sb.append(url.contains("?") ? "&" : "?");
            boolean first = true;
            for (Map.Entry<String, String> e : params.entrySet()) {
                if (!first) sb.append("&");
                sb.append(URLEncoder.encode(e.getKey(), StandardCharsets.UTF_8))
                        .append("=")
                        .append(URLEncoder.encode(e.getValue(), StandardCharsets.UTF_8));
                first = false;
            }
        }
        HttpRequest request = HttpRequest.newBuilder(URI.create(sb.toString()))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();
        HttpResponse<String> response = HTTP.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        if (response.statusCode() != 200) {
            throw new IllegalStateException("HTTP " + response.statusCode());
        }
        JsonNode root = objectMapper.readTree(response.body());
        return parseQuotes(root);
    }

    /**
     * 通用递归解析器：递归遍历 JSON，从任何层级的对象节点中提取「席别 → 票价」。
     *
     * <p>兼容策略（对 provider 响应结构变化免疫）：
     * <ol>
     *   <li><b>席别文本值配对</b>：对象含席别文本字段（seat_name/seat_type，值如「二等座」）
     *       与价格字段（price/ticket_price）→ 直接配对提取。
     *       兼容聚合数据官方结构 prices:[{seat_name, price, num}]（num 为余票，不误提取为票价）</li>
     *   <li>键名含中文席别名（二等座/一等座/硬卧/软卧/硬座/商务座/无座/特等座/软座/高级软卧）且值为正数 → 提取</li>
     *   <li>键名为缩写（priceed/priceyd/priceyz/priceyw1/priceyw2/pricewz/priceswz/pricetz 或 ed/yd/yz/yw/rw/wz/swz/tz/zy）→ 按映射表提取</li>
     *   <li>金额合理区间 (0, 5000] 元，过滤余票数量等噪音</li>
     * </ol>
     */
    public List<SeatQuote> parseQuotes(JsonNode node) {
        List<SeatQuote> quotes = new ArrayList<>();
        collectQuotes(node, quotes, null, null);
        return quotes;
    }

    /**
     * 递归提取席别票价。
     *
     * @param parentTrainCode  父级对象携带的车次号（官方 prices 数组结构中 train_no 在外层，
     *                          prices[].seat_name/price 在内层，子对象无车次字段时继承父级）
     * @param parentDepartTime 父级对象携带的出发时间（同上）
     */
    private void collectQuotes(JsonNode node, List<SeatQuote> out,
                               String parentTrainCode, String parentDepartTime) {
        if (node == null) return;
        if (node.isObject()) {
            JsonNode obj = (JsonNode) node;
            String trainCode = firstText(obj, "train_no", "station_train_code", "trainno", "checi", "车次");
            if (trainCode == null) trainCode = parentTrainCode;
            String departTime = firstText(obj, "start_time", "depart_time", "starttime", "出发时间");
            if (departTime == null) departTime = parentDepartTime;
            final String ctxTrainCode = trainCode;
            final String ctxDepartTime = departTime;
            Map<String, BigDecimal> seatPrices = new LinkedHashMap<>();
            // 模式一：席别文本值 + price 数值配对（聚合数据官方结构 prices:[{seat_name, price, num}]）
            JsonNode seatNameNode = firstNode(obj, "seat_name", "seat_type", "seatType", "seatName", "席别");
            if (seatNameNode != null && seatNameNode.isTextual()) {
                String seat = mapSeatKey(seatNameNode.asText());
                if (seat != null) {
                    BigDecimal price = firstMoney(obj, "price", "ticket_price", "priceValue", "票价");
                    if (price != null && price.signum() > 0
                            && price.compareTo(BigDecimal.valueOf(5000)) <= 0) {
                        // num 为余票数量，不进入票价提取
                        seatPrices.putIfAbsent(seat, price);
                    }
                }
            }
            // 模式二：键名即席别（极速数据 priceed/priceyw1 风格、12306 ed/yw 风格）
            obj.fields().forEachRemaining(e -> {
                String key = e.getKey();
                JsonNode val = e.getValue();
                if (!val.isNumber() && !val.isTextual()) return;
                String seat = mapSeatKey(key);
                if (seat == null) return;
                try {
                    BigDecimal price = new BigDecimal(val.asText().trim());
                    if (price.compareTo(BigDecimal.ZERO) > 0 && price.compareTo(BigDecimal.valueOf(5000)) <= 0) {
                        seatPrices.putIfAbsent(seat, price);
                    }
                } catch (NumberFormatException ignored) {
                }
            });
            for (Map.Entry<String, BigDecimal> e : seatPrices.entrySet()) {
                out.add(new SeatQuote(e.getKey(), e.getValue(), ctxTrainCode, ctxDepartTime));
            }
            obj.forEach(child -> collectQuotes(child, out, ctxTrainCode, ctxDepartTime));
        } else if (node.isArray()) {
            node.forEach(child -> collectQuotes(child, out, parentTrainCode, parentDepartTime));
        }
    }

    /** 键名 → 席别名 映射；无法识别返回 null */
    static String mapSeatKey(String key) {
        if (key == null) return null;
        String k = key.toLowerCase();
        // 中文席别键名（如「二等座」「二等座票价」「price_二等座」）
        String[] chineseSeats = {"商务座", "高级软卧", "特等座", "一等座", "二等座", "硬座", "软座", "硬卧", "软卧", "无座"};
        for (String seat : chineseSeats) {
            if (key.contains(seat)) return seat;
        }
        // 缩写键名（极速数据风格 priceed/priceyw1，或 12306 风格 ed/yw/wz）
        if (k.contains("priceed") || k.equals("ed") || k.endsWith("_ed")) return "二等座";
        if (k.contains("priceyd") || k.equals("yd") || k.equals("zy") || k.endsWith("_yd")) return "一等座";
        if (k.contains("priceyz") || k.equals("yz") || k.endsWith("_yz")) return "硬座";
        if (k.contains("priceyw1") || k.equals("yw") || k.equals("yw1") || k.endsWith("_yw1")) return "硬卧";
        if (k.contains("priceyw2") || k.equals("yw2") || k.equals("rw") || k.endsWith("_yw2")) return "软卧";
        if (k.contains("pricewz") || k.equals("wz") || k.endsWith("_wz")) return "无座";
        if (k.contains("priceswz") || k.equals("swz") || k.endsWith("_swz")) return "商务座";
        if (k.contains("pricetz") || k.equals("tz") || k.endsWith("_tz")) return "特等座";
        if (k.contains("pricerz") || k.equals("rz") || k.endsWith("_rz")) return "软座";
        if (k.contains("pricegr") || k.equals("gr") || k.endsWith("_gr")) return "高级软卧";
        return null;
    }

    private static String firstText(JsonNode obj, String... keys) {
        for (String key : keys) {
            JsonNode v = obj.get(key);
            if (v != null && v.isTextual() && !v.asText().isBlank()) return v.asText();
        }
        return null;
    }

    /** 取对象中第一个存在的节点（不限类型） */
    private static JsonNode firstNode(JsonNode obj, String... keys) {
        for (String key : keys) {
            JsonNode v = obj.get(key);
            if (v != null && !v.isNull()) return v;
        }
        return null;
    }

    /** 取对象中第一个可解析为金额的字段 */
    private static BigDecimal firstMoney(JsonNode obj, String... keys) {
        for (String key : keys) {
            JsonNode v = obj.get(key);
            if (v == null || v.isNull()) continue;
            if (!v.isNumber() && !v.isTextual()) continue;
            try {
                return new BigDecimal(v.asText().trim());
            } catch (NumberFormatException ignored) {
            }
        }
        return null;
    }

    /** 城市名归一化：去「市」后缀，与 t_poi / 快照表口径一致 */
    static String normalizeCity(String city) {
        if (city == null) return null;
        String c = city.trim();
        if (c.endsWith("市")) c = c.substring(0, c.length() - 1);
        return c.isBlank() ? null : c;
    }

    // ==================================================================================
    // 交通时长（12306 实爬车次历时）
    // ==================================================================================

    @Override
    public Map<String, DurationQuote> trainDurations(String origin, String dest) {
        String from = normalizeCity(origin);
        String to = normalizeCity(dest);
        if (from == null || to == null || from.equals(to)) {
            return Map.of();
        }
        // 正向优先，反向回退（往返历时基本对称）
        Map<String, DurationQuote> kinds = localTrainDurations.get(from + "-" + to);
        if (kinds == null || kinds.isEmpty()) {
            kinds = localTrainDurations.get(to + "-" + from);
        }
        if (kinds == null || kinds.isEmpty()) {
            log.debug("[DURATION] 本地车次历时表未收录 {}→{}，降级为速度模型估算", from, to);
            return Map.of();
        }
        log.info("[DURATION] 车次历时命中本地实爬表: {}→{} {}", from, to, kinds.keySet());
        return kinds;
    }

    // ==================================================================================
    // 酒店快照
    // ==================================================================================

    @Override
    public HotelSnapshot hotelPrice(String city, String tier) {
        String c = normalizeCity(city);
        if (c == null || tier == null || tier.isBlank()) return null;
        try {
            HotelPriceSnapshot snap = hotelPriceSnapshotMapper.findByCityAndTier(c, tier.trim().toLowerCase());
            if (snap == null || snap.getPricePerNight() == null
                    || snap.getPricePerNight().compareTo(BigDecimal.ZERO) <= 0) {
                return null;
            }
            return new HotelSnapshot(snap.getPricePerNight(), snap.getSampleHotel(),
                    snap.getSource(), snap.getCollectedDate());
        } catch (Exception e) {
            log.warn("[PRICE] 酒店快照查询失败（降级档次默认价）: {} {} {}", c, tier, e.getMessage());
            return null;
        }
    }
}
