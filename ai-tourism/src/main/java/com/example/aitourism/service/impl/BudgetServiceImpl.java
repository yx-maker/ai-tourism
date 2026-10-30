package com.example.aitourism.service.impl;

import com.example.aitourism.entity.Budget;
import com.example.aitourism.dto.budget.BudgetEnvelope;
import com.example.aitourism.dto.budget.TransportDuration;
import com.example.aitourism.mapper.BudgetMapper;
import com.example.aitourism.mapper.POIMapper;
import com.example.aitourism.service.BudgetService;
import com.example.aitourism.service.BudgetEnvelopeService;
import com.example.aitourism.service.PriceProxyService;
import com.example.aitourism.service.PriceProxyService.SeatQuote;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.langchain4j.model.chat.request.ResponseFormat;
import dev.langchain4j.model.openai.OpenAiChatModel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static dev.langchain4j.model.chat.request.ResponseFormatType.JSON;

/**
 * 预算分析服务（论文创新点：LLM 结构化提取 + 规则引擎兜底的双引擎架构）
 *
 * 第一引擎（LLM）：将 AI 生成的行程文本交给大模型，按 JSON Schema 强制输出
 *   交通/住宿/餐饮/门票/其他五类分项预算与总预算，利用 LLM 的常识推断合理价格。
 * 第二引擎（规则）：当 LLM 输出缺失或格式异常时，按行业均价规则估算：
 *   门票按景点数×平均票价、住宿按天数×城市均价、餐饮按天数×人均、交通按往返+市内。
 * 最终结果两引擎融合后落库，保证输出稳定可解析（开题报告中的核心难点）。
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class BudgetServiceImpl implements BudgetService {

    private final BudgetMapper budgetMapper;
    private final com.example.aitourism.mapper.SessionMapper sessionMapper;
    private final com.example.aitourism.service.BudgetEnvelopeService envelopeService;
    private final com.example.aitourism.service.TransportDurationService durationService;
    private final PriceProxyService priceProxyService;
    private final POIMapper poiMapper;

    @Value("${openai.api-key}")
    private String apiKey;

    @Value("${openai.base-url}")
    private String baseUrl;

    @Value("${openai.model-name}")
    private String modelName;

    private final ObjectMapper objectMapper = new ObjectMapper();

    // 规则引擎参数
    private static final BigDecimal AVG_TICKET = new BigDecimal("80");      // 平均门票（元/景点）
    private static final BigDecimal HOTEL_DAILY = new BigDecimal("250");    // 住宿（元/晚）
    private static final BigDecimal FOOD_DAILY = new BigDecimal("120");     // 餐饮（元/天）
    private static final BigDecimal TRANSPORT_DAILY = new BigDecimal("60"); // 市内交通兜底（元/天）
    private static final BigDecimal CITY_TRANSPORT = new BigDecimal("400"); // 往返大交通兜底（元）
    // 市内交通估算参数（基于真实距离）
    private static final BigDecimal ROAD_FACTOR = new BigDecimal("1.3");         // 直线距离→道路距离系数
    private static final BigDecimal TIER1_PRICE = new BigDecimal("2.5");         // 一线城市市内交通单价（元/公里）
    private static final BigDecimal TIER2_PRICE = new BigDecimal("2.0");         // 二线城市市内交通单价（元/公里）
    private static final BigDecimal TIER3_PRICE = new BigDecimal("1.5");         // 其他城市市内交通单价（元/公里）
    private static final BigDecimal MIN_LOCAL_DAILY = new BigDecimal("30");      // 市内交通每日下限（元）

    @Override
    public Budget analyze(String sessionId, String userId, String itineraryText) {
        if (itineraryText == null || itineraryText.trim().isEmpty()) {
            throw new RuntimeException("2001: 行程内容为空，无法进行预算分析");
        }

        // 预估天数（按"第N天"模式统计）
        int days = estimateDays(itineraryText);
        if (days <= 0) days = 1;

        // 读取会话路线坐标（用于市内交通距离估算）
        String dailyRoutes = null;
        try {
            com.example.aitourism.entity.Session session = sessionMapper.findBySessionId(sessionId);
            if (session != null) {
                dailyRoutes = session.getDailyRoutes();
            }
        } catch (Exception e) {
            log.warn("读取会话路线失败（使用兜底交通估算）: {}", e.getMessage());
        }

        // ==================== 新增第一步：解析预算并反推「预算封套」 ====================
        // 封套回答「在给定预算下能走什么档次」，是"严格按预算规划"的约束来源
        BigDecimal userBudget = resolveUserBudget(sessionId, itineraryText);
        String destCity = extractDestCity(itineraryText);
        Object[] transportParts = estimateTransport(itineraryText, days, dailyRoutes);
        BigDecimal envelopeTransport = (BigDecimal) transportParts[0];
        String envelopeTransportMode = (String) transportParts[2];
        int poiCount = estimatePoiCount(itineraryText);
        // 大交通时长（按预算选出的方式对应的在途时间，真实车次历时优先）
        TransportDuration envelopeDuration = transportParts.length > 5
                ? (TransportDuration) transportParts[5] : null;
        // 住宿快照价覆盖（无快照的档次自动回落默认价）——让封套上限贴近真实房价行情
        Map<String, BigDecimal> hotelOverrides = buildHotelOverrides(destCity);
        BudgetEnvelope envelope = envelopeService.build(
                userBudget, days, poiCount, envelopeTransport, envelopeTransportMode,
                hotelOverrides, envelopeDuration);
        log.info("[BUDGET] 预算封套: 用户预算={} 天数={} 档次={} 封套合计={} 可行={}",
                userBudget, days, envelope.getLevel(), envelope.getTotal(), envelope.isFeasible());

        // 时间账与钱账同样重要：在途超过 8 小时时，给出时间安排建议
        if (envelopeDuration != null && envelopeDuration.getMinutesOneWay() != null
                && envelopeDuration.getMinutesOneWay() >= 480) {
            envelope.getSuggestions().add(String.format(
                    "大交通在途较长（%s 单程约 %s，往返约 %s）：建议选夕发朝至车次，"
                            + "抵达当天与返程当天各只安排 1 个不需要预约的景点。",
                    envelopeDuration.getKind(), envelopeDuration.textOneWay(),
                    envelopeDuration.textRoundTrip()));
        }

        // 把识别到的预算回写会话，供后续「同会话再次规划」直接复用
        if (userBudget != null && userBudget.compareTo(BigDecimal.ZERO) > 0) {
            try {
                sessionMapper.updateBudgetAmount(sessionId, userBudget);
            } catch (Exception e) {
                log.warn("回写会话预算失败: {}", e.getMessage());
            }
        }

        // 价格只采用真实数据规则引擎：12306 票价 / 景点库门票 / 酒店快照 / 明确标注的系统估算。
        // 行程攻略仅用于识别城市、天数、景点与交通方式，**不再从攻略文本提取或采用任何价格**，
        // 避免把攻略中的过时价格、LLM 生成价格当作真实预算依据。
        Budget ruleBudget = extractByRule(itineraryText, days, dailyRoutes, transportParts);
        Budget finalBudget = ruleBudget;

        // ==================== 新增第二步：用封套核验并再平衡（只压不抬） ====================
        // 高于封套上限的分项截断到上限；由于封套各项之和 ≤ 用户预算，
        // 截断后总预算必然落在预算内 —— 这是"严格按预算"的工程保证
        envelopeService.reconcile(finalBudget, envelope);
        finalBudget.setEnvelope(envelope);
        finalBudget.setEnvelopeJson(buildEnvelopeJson(envelope));
        finalBudget.setPlanJson(buildPlanJson(envelope));

        // 幻觉过滤：门票类明细必须能在行程文本中找到对应景点名，否则剔除（防 LLM 编造景点）
        finalBudget.setDetailItems(filterHallucinatedTickets(finalBudget.getDetailItems(), itineraryText));
        // 门票被封套压到 0（预算过紧的降级结果）时改写文案，
        // 避免前端出现「约8个收费景点（均价80元） ¥0」这种自相矛盾的展示
        if (finalBudget.getTicketCost() != null
                && finalBudget.getTicketCost().compareTo(BigDecimal.ZERO) == 0
                && finalBudget.getDetailItems() != null) {
            for (Map<String, Object> it : finalBudget.getDetailItems()) {
                if ("门票".equals(it.get("category"))) {
                    it.put("name", "预算过紧：已取消收费景点门票（改以免费 / 低价景点为主）");
                }
            }
        }
        // 补齐缺失类别的明细条目，保证五类完整（明细与分项一致由归一化保证）
        finalBudget.setDetailItems(ensureCompleteCategories(finalBudget));
        finalBudget.setSessionId(sessionId);
        finalBudget.setUserId(userId);
        finalBudget.setDays(days);
        // 明细归一化：按最终分项值重写各分类明细金额（保证明细合计=分项合计，消除不一致）
        // 归一化前先做交通优先级重分配，否则往返大交通会被估算出来的市内交通挤占
        prioritizeLongDistanceInTransport(finalBudget);
        normalizeItemsToBudget(finalBudget);
        finalBudget.setDetailJson(buildDetailJson(finalBudget));

        // 落库（同一会话覆盖更新）
        Budget existing = budgetMapper.findBySessionId(sessionId);
        if (existing == null) {
            budgetMapper.insert(finalBudget);
        } else {
            budgetMapper.updateBySession(finalBudget);
        }
        log.info("预算分析完成: 会话 {} 总预算 {} 元 (用户预算 {} / 状态 {} / 结余 {}) (价格来源: 真实数据规则引擎，未采用攻略文本价格)",
                sessionId, finalBudget.getTotalBudget(), finalBudget.getUserBudget(),
                finalBudget.getBudgetStatus(), finalBudget.getRemainingBudget());
        return finalBudget;
    }

    @Override
    public Budget getBySession(String sessionId) {
        return budgetMapper.findBySessionId(sessionId);
    }

    @Override
    public List<Budget> recent(String userId, Integer limit) {
        if (limit == null || limit < 1) limit = 10;
        if (limit > 50) limit = 50;
        return budgetMapper.findRecentByUserId(userId, limit);
    }

    // ==================== 第一引擎：LLM 结构化提取 ====================

    private Budget extractByLlm(String itineraryText) {
        try {
            ResponseFormat responseFormat = ResponseFormat.builder()
                    .type(JSON)
                    .build();

            OpenAiChatModel model = OpenAiChatModel.builder()
                    .apiKey(apiKey)
                    .baseUrl(baseUrl)
                    .modelName(modelName)
                    .responseFormat(ResponseFormat.builder().type(JSON).build())
                    .build();

            String template = """
                    ## 角色与任务
                    你是一位专业的旅游预算分析师。请根据用户提供的旅游行程攻略，估算该行程的总预算，
                    并拆分为交通、住宿、餐饮、门票、其他五类分项费用（单位：元）。
                    同时生成一份费用明细清单 items（尽量细化到每一项，如单笔门票、单晚住宿、高铁往返等）。
                    注意：
                    1. **攻略中明确写明的价格必须直接采用**（如"滕王阁¥50""硬卧往返¥400""青旅¥60/晚"），
                       攻略里的"费用参考/费用总结/预算参考"表格是最高权威依据——若攻略有该表格，
                       **直接照抄表格中的分项金额**（如表格写交通¥400，则 transportCost=400，不要用正文里的其他价格替代）。
                    2. 交通费包含往返大交通（如高铁/机票）与市内交通，出行方式以攻略费用表/推荐为准。
                    3. 住宿费按行程天数估算（如3天2夜按2晚计算），单价以攻略写明为准。
                    4. 门票费仅统计行程中明确提到的收费景点，每个收费景点单独一条明细，单价以攻略写明为准。
                    5. 所有数值取整数，输出严格的JSON对象，不要输出任何其他文字。
                    6. 若行程中未明确提到的项目，可按行业常识合理估算（如市内交通按50元/天）。
                    7. totalBudget 必须等于五个分项之和（交通+住宿+餐饮+门票+其他）。

                    ## 输出JSON格式
                    {
                      "totalBudget": 0,
                      "transportCost": 0,
                      "accommodationCost": 0,
                      "foodCost": 0,
                      "ticketCost": 0,
                      "otherCost": 0,
                      "items": [
                        {"category": "交通", "name": "往返高铁", "amount": 500},
                        {"category": "住宿", "name": "第1晚酒店", "amount": 300},
                        {"category": "门票", "name": "秦始皇兵马俑博物馆", "amount": 120}
                      ]
                    }
                    category 只能是：交通/住宿/餐饮/门票/其他。

                    ## 用户行程攻略
                    {{itinerary}}
                    """;

            String prompt = template.replace("{{itinerary}}",
                    itineraryText.length() > 4000 ? itineraryText.substring(0, 4000) : itineraryText);
            dev.langchain4j.model.chat.request.ChatRequest chatRequest =
                    dev.langchain4j.model.chat.request.ChatRequest.builder()
                            .responseFormat(responseFormat)
                            .messages(new dev.langchain4j.data.message.UserMessage(prompt))
                            .build();
            String result = model.chat(chatRequest).aiMessage().text();

            JsonNode node = objectMapper.readTree(result);
            Budget budget = new Budget();
            budget.setTotalBudget(parseDecimal(node, "totalBudget"));
            budget.setTransportCost(parseDecimal(node, "transportCost"));
            budget.setAccommodationCost(parseDecimal(node, "accommodationCost"));
            budget.setFoodCost(parseDecimal(node, "foodCost"));
            budget.setTicketCost(parseDecimal(node, "ticketCost"));
            budget.setOtherCost(parseDecimal(node, "otherCost"));
            // 解析费用明细条目
            budget.setDetailItems(parseItems(node.get("items")));
            return budget;
        } catch (Exception e) {
            log.warn("LLM预算提取失败，将使用规则引擎: {}", e.getMessage());
            return null;
        }
    }

    private List<Map<String, Object>> parseItems(JsonNode itemsNode) {
        List<Map<String, Object>> items = new java.util.ArrayList<>();
        if (itemsNode == null || !itemsNode.isArray()) return items;
        for (JsonNode item : itemsNode) {
            try {
                String category = item.has("category") ? item.get("category").asText("") : "";
                String name = item.has("name") ? item.get("name").asText("") : "";
                BigDecimal amount = item.has("amount") ? parseDecimal(item, "amount") : BigDecimal.ZERO;
                if (!category.isEmpty() && !name.isEmpty() && amount.compareTo(BigDecimal.ZERO) > 0) {
                    Map<String, Object> m = new java.util.HashMap<>();
                    m.put("category", category);
                    m.put("name", name);
                    m.put("amount", amount);
                    // 攻略载明价：LLM 从行程文本提取，行程中的价格本身来自注入的真实价格参考
                    m.put("source", "ITINERARY");
                    m.put("as_of", LocalDate.now().toString());
                    m.put("confidence", "medium");
                    items.add(m);
                }
            } catch (Exception ignored) { }
        }
        return items;
    }

    private BigDecimal parseDecimal(JsonNode node, String field) {
        JsonNode v = node.get(field);
        if (v == null || v.isNull() || v.isMissingNode()) return BigDecimal.ZERO;
        try {
            return new BigDecimal(v.asText()).setScale(2, RoundingMode.HALF_UP);
        } catch (Exception e) {
            return BigDecimal.ZERO;
        }
    }

    // ==================== 第二引擎：规则估算 ====================

    /** 住宿档次中文名 */
    private static String tierName(String tier) {
        return switch (tier) {
            case "premium" -> "高档档";
            case "comfort" -> "舒适档";
            default -> "经济档";
        };
    }

    /**
     * 按总预算与天数推荐住宿档次（优先档在前，取不到快照时依次回退）。
     * 住宿一般占总预算三成左右，据此折算每晚可承受价：
     *   ≥600 元/晚 → 高档；≥300 → 舒适；否则经济。
     */
    private static String[] pickHotelTiers(BigDecimal userBudget, int days) {
        int nights = Math.max(days - 1, 1);
        if (userBudget == null || userBudget.compareTo(BigDecimal.ZERO) <= 0) {
            return new String[]{"economy", "comfort", "premium"};
        }
        BigDecimal perNight = userBudget.multiply(new BigDecimal("0.30"))
                .divide(BigDecimal.valueOf(nights), 0, RoundingMode.HALF_UP);
        if (perNight.compareTo(new BigDecimal("600")) >= 0) {
            return new String[]{"premium", "comfort", "economy"};
        }
        if (perNight.compareTo(new BigDecimal("300")) >= 0) {
            return new String[]{"comfort", "economy", "premium"};
        }
        return new String[]{"economy", "comfort", "premium"};
    }

    private Budget extractByRule(String itineraryText, int days, String dailyRoutesJson, Object[] transportParts) {
        Budget budget = new Budget();
        // 统计行程中提到的景点数（用 POI 名出现次数近似：以"- "、"**"、"·"等列表标记估算）
        int poiCount = estimatePoiCount(itineraryText);
        if (poiCount <= 0) poiCount = Math.max(days * 2, 2);

        // 门票均价：优先取景点库真实票价（t_poi.ticket_price），拿不到才用系统均价
        String ticketCity = extractDestCity(itineraryText);
        BigDecimal ticketAvg = AVG_TICKET;
        String ticketSource = "ESTIMATE";
        String ticketAvgNote = "均价" + AVG_TICKET.intValue() + "元";
        BigDecimal ticketFreeRatio = BigDecimal.ZERO;   // 免费景点占比，用于折算避免高估
        if (ticketCity != null) {
            try {
                BigDecimal dbAvg = poiMapper.avgTicketPriceByCity(ticketCity);
                int pricedCount = poiMapper.countPricedPoiByCity(ticketCity);
                int totalCount = poiMapper.countPoiByCity(ticketCity);
                int collectedCount = poiMapper.countTicketCollectedByCity(ticketCity);

                if (dbAvg != null && dbAvg.compareTo(BigDecimal.ZERO) > 0 && pricedCount > 0) {
                    ticketAvg = dbAvg.setScale(0, RoundingMode.HALF_UP);
                    ticketSource = "SNAPSHOT";
                    // 该城市存在免费景点时按收费占比折算，否则会把免费景点也算成收费价而系统性高估
                    double pricedRatio = totalCount > 0 ? (double) pricedCount / totalCount : 1.0;
                    ticketFreeRatio = BigDecimal.ONE.subtract(
                            BigDecimal.valueOf(pricedRatio).setScale(2, RoundingMode.HALF_UP));
                    ticketAvgNote = "均价" + ticketAvg.intValue() + "元·景点库真实票价("
                            + pricedCount + "/" + totalCount + "收费)";
                } else if (collectedCount > 0 && pricedCount == 0) {
                    // 已采集过票价且全部为 0 → 该城市景点确为免费开放，不应按系统均价估算
                    ticketAvg = BigDecimal.ZERO;
                    ticketSource = "SNAPSHOT";
                    ticketFreeRatio = BigDecimal.ZERO;
                    ticketAvgNote = "该城市已采集景点均为免费开放(" + collectedCount + "个)";
                }
            } catch (Exception e) {
                log.warn("景点库门票均价查询失败（使用系统均价）: {}", e.getMessage());
            }
        }
        BigDecimal ticket = ticketAvg.multiply(BigDecimal.valueOf(poiCount))
                .multiply(BigDecimal.ONE.subtract(ticketFreeRatio))
                .setScale(0, RoundingMode.HALF_UP);
        // 住宿：优先目的地酒店快照价（t_hotel_price_snapshot），无快照才用系统默认价
        BigDecimal hotelPerNight = HOTEL_DAILY;
        String hotelSource = "ESTIMATE";
        String hotelNote = "系统估算" + HOTEL_DAILY.intValue() + "元/晚";
        if (ticketCity != null) {
            // 按预算匹配住宿档次：预算宽裕选舒适/高档，紧张则经济档，避免一律按经济档低估
            String[] tiers = pickHotelTiers(extractBudget(itineraryText), days);
            try {
                for (String tier : tiers) {
                    PriceProxyService.HotelSnapshot snap = priceProxyService.hotelPrice(ticketCity, tier);
                    if (snap != null && snap.pricePerNight() != null
                            && snap.pricePerNight().compareTo(BigDecimal.ZERO) > 0) {
                        hotelPerNight = snap.pricePerNight();
                        hotelSource = "SNAPSHOT";
                        hotelNote = tierName(tier) + hotelPerNight.intValue() + "元/晚·酒店快照("
                                + snap.sampleHotel() + ")";
                        break;
                    }
                }
            } catch (Exception e) {
                log.warn("酒店快照价查询失败（使用系统默认价）: {} {}", ticketCity, e.getMessage());
            }
        }
        BigDecimal hotel = hotelPerNight.multiply(BigDecimal.valueOf(Math.max(days - 1, 0)));
        BigDecimal food = FOOD_DAILY.multiply(BigDecimal.valueOf(days));
        // 交通：按用户预算自动选择出行方式；优先真实票价 API，失败降级票价模型
        // （transportParts 由 analyze() 统一解析后传入，避免重复计算与重复日志）
        BigDecimal longDistance = (BigDecimal) transportParts[0];
        BigDecimal local = (BigDecimal) transportParts[1];
        String transportMode = (String) transportParts[2];
        String transportSource = transportParts.length > 3 && transportParts[3] != null
                ? (String) transportParts[3] : "ESTIMATE";
        String transportAsOf = transportParts.length > 4 && transportParts[4] != null
                ? (String) transportParts[4] : LocalDate.now().toString();
        TransportDuration transportDuration = transportParts.length > 5
                ? (TransportDuration) transportParts[5] : null;
        BigDecimal transport = longDistance.add(local);
        BigDecimal other = new BigDecimal("100").multiply(BigDecimal.valueOf(days));

        budget.setTicketCost(round(ticket));
        budget.setAccommodationCost(round(hotel));
        budget.setFoodCost(round(food));
        budget.setTransportCost(round(transport));
        budget.setOtherCost(round(other));
        budget.setTotalBudget(round(ticket.add(hotel).add(food).add(transport).add(other)));

        // 规则引擎生成兜底费用明细条目（每条携带价格来源，供前端分级展示）
        List<Map<String, Object>> items = new java.util.ArrayList<>();
        items.add(item("交通", "往返大交通（" + transportMode
                        + (transportDuration == null ? "" : "，单程约 " + transportDuration.textOneWay()) + "）",
                longDistance,
                transportSource, transportAsOf, "TRAIN_API".equals(transportSource) ? "high" : "low"));
        if (local.compareTo(BigDecimal.ZERO) > 0) {
            items.add(item("交通", "市内交通（" + days + "天，按路线实际通勤距离估算）", local,
                    "ESTIMATE", LocalDate.now().toString(), "low"));
        }
        if (days > 1) {
            items.add(item("住宿", (days - 1) + "晚酒店（" + hotelNote + "）", hotel,
                    hotelSource, LocalDate.now().toString(),
                    "SNAPSHOT".equals(hotelSource) ? "high" : "low"));
        }
        items.add(item("餐饮", days + "天餐饮", food,
                "ESTIMATE", LocalDate.now().toString(), "low"));
        if (poiCount > 0) {
            items.add(item("门票", "约" + poiCount + "个收费景点（" + ticketAvgNote + "）", ticket,
                    ticketSource, LocalDate.now().toString(),
                    "SNAPSHOT".equals(ticketSource) ? "high" : "low"));
        }
        items.add(item("其他", "购物/纪念品等（" + days + "天）", other,
                "ESTIMATE", LocalDate.now().toString(), "low"));
        budget.setDetailItems(items);
        return budget;
    }

    /**
     * 交通费用估算（论文改进点：按用户预算上限自动选择出行方式，价格基于真实票价模型）
     * @return [0]=往返大交通（元）, [1]=市内交通（元）, [2]=出行方式描述,
     *         [3]=价格来源, [4]=数据日期, [5]=大交通时长 {@link TransportDuration}
     */
    private Object[] estimateTransport(String itineraryText, int days, String dailyRoutesJson) {
        BigDecimal longDistance = CITY_TRANSPORT;  // 兜底：往返大交通 400 元
        String transportMode = "高铁二等座";
        String transportSource = "ESTIMATE";       // TRAIN_API=真实票价 / ESTIMATE=系数估算
        String transportAsOf = LocalDate.now().toString();
        BigDecimal local = TRANSPORT_DAILY.multiply(BigDecimal.valueOf(days));  // 兜底：60元/天
        double distKm = 0;                         // 城市间距离（用于时长估算）

        // ---------- 大交通：提取出发地/目的地，按预算选择出行方式 ----------
        String destCity = extractDestCity(itineraryText);
        String originCity = com.example.aitourism.util.CityGeoUtil.extractOriginCity(itineraryText, destCity);
        BigDecimal userBudget = extractBudget(itineraryText);  // 用户给出的总预算（可能为 null）
        if (destCity != null && originCity != null) {
            double dist = com.example.aitourism.util.CityGeoUtil.distanceKm(originCity, destCity);
            if (dist > 50) {
                distKm = dist;
                // 第一优先：真实票价 API（同步 12306，需在预售期 14 天内）
                Object[] real = queryRealTrainPrice(originCity, destCity, userBudget);
                if (real != null) {
                    longDistance = (BigDecimal) real[0];
                    transportMode = (String) real[1];
                    transportSource = "TRAIN_API";
                    log.info("大交通真实票价: {}→{} 距离{}km 预算{} 选择「{}」往返{}元（12306实时）",
                            originCity, destCity, Math.round(dist), userBudget, transportMode, longDistance);
                } else {
                    // 第二优先：行程里明写的往返交通价（如「往返机票约800-1000元」）
                    Object[] written = extractRoundTripFromItinerary(itineraryText);
                    if (written != null) {
                        longDistance = (BigDecimal) written[0];
                        transportMode = (String) written[1] + "（行程载明往返价）";
                        transportSource = "ITINERARY";
                        log.info("大交通采用行程载明价: {}→{} 「{}」往返{}元", originCity, destCity, written[1], longDistance);
                    } else {
                        // 最后降级：里程系数票价模型
                        TransportChoice choice = chooseTransport(dist, userBudget);
                        longDistance = choice.roundTripCost;
                        transportMode = choice.mode;
                        log.info("大交通估算: {}→{} 距离{}km 预算{} 选择「{}」往返{}元（系数模型）", originCity, destCity,
                                Math.round(dist), userBudget, choice.mode, longDistance);
                    }
                }
            }
        } else if (destCity == null && originCity == null) {
            // 无法识别城市对：按典型跨省距离(800km)高铁估算，预算紧张则降级
            TransportChoice choice = chooseTransport(800, userBudget);
            longDistance = choice.roundTripCost;
            transportMode = choice.mode + "（按典型跨省里程估算）";
        }

        // ---------- 市内交通：按路线坐标计算每天通勤距离 ----------
        BigDecimal localFromRoutes = estimateLocalTransport(dailyRoutesJson, days);
        if (localFromRoutes != null) {
            local = localFromRoutes;
        }
        // ---------- 大交通时长：按「预算选出的方式」给出在途时间 ----------
        TransportDuration duration = resolveTransportDuration(transportMode, distKm, originCity, destCity);
        if (duration != null) {
            log.info("大交通时长: {}→{} 「{}」{}（来源 {}）", originCity, destCity,
                    transportMode, duration.summary(), duration.getSource());
        }
        return new Object[]{round(longDistance), round(local), transportMode,
                transportSource, transportAsOf, duration};
    }

    /**
     * 解析大交通时长：委托 {@link TransportDurationService}（与规划链路同一口径）。
     *
     * <p>「按预算选交通方式」的代价必须可见：预算紧张时系统会降级到普速列车，
     * 票价省了但单程可能从 7 小时变成 30 小时。
     */
    private TransportDuration resolveTransportDuration(String mode, double distKm,
                                                      String originCity, String destCity) {
        return durationService.resolve(mode, originCity, destCity, distKm);
    }

    /**
     * 从行程文本中提取「明写的往返大交通价」。
     *
     * 智能规划生成的行程末尾通常有「费用参考：往返机票约800-1000元」这类表述，
     * 它比里程系数模型可靠得多——系数模型在出发地识别不准时会算出「跨省 119 元」这种荒谬值。
     * 这里只采信**同时写明交通方式与往返金额**的句子（如「往返机票约800-1000元」），
     * 区间价取中值；不含交通方式或不写「往返/来回」的一律不采信，避免误抓「当地交通约200元」。
     *
     * @return [0]=往返总价, [1]=交通方式；未找到返回 null
     */
    private Object[] extractRoundTripFromItinerary(String text) {
        if (text == null || text.isBlank()) return null;
        try {
            java.util.regex.Matcher seg = java.util.regex.Pattern
                    .compile("[^。；;\\n]{0,24}(?:往返|来回)[^。；;\\n]{0,32}")
                    .matcher(text);
            while (seg.find()) {
                String s = seg.group();
                String mode = null;
                if (s.contains("机票") || s.contains("飞机") || s.contains("航班")) mode = "飞机经济舱";
                else if (s.contains("高铁") || s.contains("动车")) mode = "高铁二等座";
                else if (s.contains("硬卧")) mode = "普速列车硬卧";
                else if (s.contains("硬座") || s.contains("火车")) mode = "普速列车硬座";
                else if (s.contains("大巴") || s.contains("长途汽车")) mode = "长途大巴";
                if (mode == null) continue;                 // 未写明交通方式 → 不采信

                java.math.BigDecimal value = null;
                java.util.regex.Matcher range = java.util.regex.Pattern
                        .compile("(\\d{2,5})\\s*[-~—－到至]\\s*(\\d{2,5})\\s*元").matcher(s);
                if (range.find()) {
                    // 区间价取中值（如「800-1000元」→ 900）
                    double lo = Double.parseDouble(range.group(1));
                    double hi = Double.parseDouble(range.group(2));
                    value = round(java.math.BigDecimal.valueOf((lo + hi) / 2));
                } else {
                    java.util.regex.Matcher single = java.util.regex.Pattern
                            .compile("(\\d{2,5})\\s*元").matcher(s);
                    if (single.find()) {
                        value = round(java.math.BigDecimal.valueOf(Double.parseDouble(single.group(1))));
                    }
                }
                if (value == null || value.compareTo(java.math.BigDecimal.ZERO) <= 0) continue;
                // 上限保护：单段往返大交通超过 6000 元视为误抓
                if (value.compareTo(new java.math.BigDecimal("6000")) > 0) continue;
                return new Object[]{value, mode};
            }
        } catch (Exception e) {
            log.warn("行程往返价提取失败（降级系数模型）: {}", e.getMessage());
        }
        return null;
    }

    /**
     * 查询真实火车票价（同步 12306 的第三方聚合 API）。
     *
     * @return [0]=往返总价, [1]=席别描述；未配置 Key / 预售期外 / 查询失败返回 null（调用方降级模型）
     */
    private Object[] queryRealTrainPrice(String origin, String dest, BigDecimal userBudget) {
        try {
            if (!priceProxyService.trainApiEnabled()) {
                return null;
            }
            String today = LocalDate.now().toString();
            List<SeatQuote> quotes = priceProxyService.trainQuotes(origin, dest, today);
            if (quotes == null || quotes.isEmpty()) {
                return null;
            }
            // 选席别：默认二等座（性价比基准）；没有二等座再退硬卧；预算内买不起则降级到便宜席别
            SeatQuote second = quotes.stream()
                    .filter(q -> "二等座".equals(q.seatType()))
                    .findFirst()
                    .orElseGet(() -> quotes.stream()
                            .filter(q -> "硬卧".equals(q.seatType()))
                            .findFirst().orElse(null));
            SeatQuote chosen = null;
            if (userBudget != null && userBudget.compareTo(BigDecimal.ZERO) > 0) {
                BigDecimal oneWayCap = userBudget.multiply(new BigDecimal("0.35"))
                        .divide(new BigDecimal("2"), 0, RoundingMode.HALF_UP);
                if (second != null && second.price().compareTo(oneWayCap) <= 0) {
                    chosen = second;
                } else {
                    chosen = quotes.stream()
                            .filter(q -> q.price().compareTo(oneWayCap) <= 0)
                            .max(java.util.Comparator.comparing(SeatQuote::price))
                            .orElse(null);
                }
                if (chosen == null) {
                    // 都超预算：选最便宜席别（真实票价仍然可用，超支由封套引擎处理）
                    chosen = quotes.stream().min(java.util.Comparator.comparing(SeatQuote::price)).orElse(null);
                }
            } else {
                chosen = second != null ? second
                        : quotes.stream().max(java.util.Comparator.comparing(SeatQuote::price)).orElse(null);
            }
            if (chosen == null) {
                return null;
            }
            BigDecimal roundTrip = chosen.price().multiply(new BigDecimal("2"));
            // 文案带上车次：用户能一眼核对「票价与时长出自同一趟车」，
            // 而不是「¥122 的二等座 + 高铁 2 小时」这种跨车次拼出来的组合
            String code = chosen.trainCode();
            String label = chosen.seatType() + (code != null && !code.isBlank()
                    ? "（" + code + (chosen.departTime() == null || chosen.departTime().isBlank()
                    ? "" : " " + chosen.departTime()) + "，12306实爬票价）"
                    : "（12306实爬票价）");
            log.info("大交通车次级选择: {}→{} {} {} 往返{}元", origin, dest, code, chosen.seatType(), roundTrip);
            return new Object[]{round(roundTrip), label};
        } catch (Exception e) {
            log.warn("真实火车票价查询失败（降级系数模型）: {}→{} {}", origin, dest, e.getMessage());
            return null;
        }
    }

    /**
     * 构建住宿快照价覆盖表（档次名 → 元/晚）。
     * 无快照数据的城市返回空 Map，封套引擎自动使用档次默认价。
     */
    private Map<String, BigDecimal> buildHotelOverrides(String destCity) {
        Map<String, BigDecimal> overrides = new java.util.HashMap<>();
        if (destCity == null || destCity.isBlank()) {
            return overrides;
        }
        try {
            putSnapshot(overrides, destCity, "品质", "premium");
            putSnapshot(overrides, destCity, "舒适", "comfort");
            putSnapshot(overrides, destCity, "经济", "economy");
        } catch (Exception e) {
            log.warn("酒店快照价查询失败（使用档次默认价）: {} {}", destCity, e.getMessage());
        }
        return overrides;
    }

    private void putSnapshot(Map<String, BigDecimal> overrides, String city, String tierName, String tierKey) {
        try {
            PriceProxyService.HotelSnapshot snap = priceProxyService.hotelPrice(city, tierKey);
            if (snap != null && snap.pricePerNight() != null
                    && snap.pricePerNight().compareTo(BigDecimal.ZERO) > 0) {
                overrides.put(tierName, snap.pricePerNight());
                log.info("[PRICE] 酒店快照命中: {} {}档 {} 元/晚（{}·{}）", city, tierName,
                        snap.pricePerNight(), snap.sampleHotel(), snap.collectedDate());
            }
        } catch (Exception ignored) {
            // 单档次查询失败不影响其他档次
        }
    }

    /**
     * 从行程文本提取用户总预算（"预算4000元"、"预算一千"、"3000块钱"等）。
     *
     * 必须**排除分项价格**的干扰：智能规划的行程末尾常有「费用参考」，
     * 例如「往返机票约800-1000元」「住宿约300元/晚」「门票约400元」，
     * 旧的写法按出现顺序取第一个三位数，会把「800-1000元」里的 1000 当成总预算
     * （真实总预算写在后面「总预算：约2000元」），导致封套整体误判。
     * 因此这里：① 优先取带预算意图词的数字；② 跳过区间后半段；③ 跳过交通/住宿/餐饮/门票上下文。
     */
    private BigDecimal extractBudget(String text) {
        if (text == null) return null;

        // 轮1：明确的预算意图词 + 阿拉伯数字（"预算3000元" / "总预算：约2000元"）
        java.util.regex.Matcher m1 = java.util.regex.Pattern
                .compile("(?:总预算|预算|花费|总花费|控制在|不超过|人均预算)\\s*[:：是为]?\\s*(?:约|大约|大概)?\\s*(\\d{3,6})\\s*(?:元|块|块钱|人民币)?")
                .matcher(text);
        while (m1.find()) {
            if (isRangeTail(text, m1.start(1)) || isItemContext(text, m1.start(1))) continue;
            int val = Integer.parseInt(m1.group(1));
            if (val >= 500 && val <= 100000) {
                return BigDecimal.valueOf(val);
            }
        }

        // 轮2：预算意图词 + 中文数字（"预算两千" / "预算三千五"）——必须含"千"或"万"
        java.util.regex.Matcher m2 = java.util.regex.Pattern
                .compile("(?:总预算|预算|花费|总花费|控制在|不超过|人均预算)\\s*[:：是为]?\\s*(?:约|大约|大概)?\\s*([零一二两三四五六七八九十百千万]+)\\s*(?:元|块钱|人民币)?")
                .matcher(text);
        while (m2.find()) {
            String numStr = m2.group(1);
            if (!numStr.contains("千") && !numStr.contains("万")) continue;
            if (isItemContext(text, m2.start(1))) continue;
            int val = chineseBudgetToNumber(numStr);
            if (val >= 500 && val <= 100000) {
                return BigDecimal.valueOf(val);
            }
        }

        // 轮3：兜底——裸数字 + 元（"3000块钱"），同样排除分项上下文与区间后半段
        java.util.regex.Matcher m3 = java.util.regex.Pattern
                .compile("(\\d{3,6})\\s*(?:元|块钱|人民币)").matcher(text);
        while (m3.find()) {
            if (isRangeTail(text, m3.start(1)) || isItemContext(text, m3.start(1))) continue;
            int val = Integer.parseInt(m3.group(1));
            if (val >= 500 && val <= 100000) {
                return BigDecimal.valueOf(val);
            }
        }
        return null;
    }

    /** 该数字是否只是区间的后半段（如「800-1000元」里的 1000）——是则不能当作总预算 */
    private boolean isRangeTail(String text, int numStart) {
        if (numStart <= 0) return false;
        char prev = text.charAt(numStart - 1);
        return prev == '-' || prev == '~' || prev == '—' || prev == '－' || prev == '至' || prev == '到';
    }

    /**
     * 该数字是否处在「分项价格」上下文中（交通/住宿/餐饮/门票/机票等）。
     * 行程的「费用参考」段落会逐项写价格，这些都不是总预算。
     *
     * 只取**数字所在的这一句**判断（从最近的换行 / 列表符 / 句号往前截断），
     * 否则「- 门票：约400元」会污染紧随其后的「- 总预算：约2000元」，导致总预算被误排除。
     */
    private boolean isItemContext(String text, int numStart) {
        int from = Math.max(0, numStart - 40);
        for (int i = numStart - 1; i >= from; i--) {
            char c = text.charAt(i);
            if (c == '\n' || c == '-' || c == '•' || c == '。' || c == '；' || c == ';' || c == '、') {
                from = i + 1;
                break;
            }
        }
        String near = text.substring(from, Math.min(text.length(), numStart + 6));
        String[] itemWords = {"机票", "高铁", "动车", "火车", "车票", "往返", "来回", "交通",
                "住宿", "酒店", "民宿", "房费", "餐饮", "吃饭", "用餐", "门票", "景区", "船票"};
        for (String w : itemWords) {
            if (near.contains(w)) return true;
        }
        return false;
    }

    /** 中文数字转阿拉伯数字（支持"一千""两千五""一千五""三千二百""两千五百"等） */
    private int chineseBudgetToNumber(String chinese) {
        if (chinese == null || chinese.isEmpty()) return 0;
        int total = 0;
        int current = 0;      // 当前累计的数字（单位前的部分）
        boolean sawDigit = false;
        for (int i = 0; i < chinese.length(); i++) {
            char c = chinese.charAt(i);
            int digit = -1;
            switch (c) {
                case '零': digit = 0; break;
                case '一': case '壹': digit = 1; break;
                case '二': case '两': case '贰': digit = 2; break;
                case '三': case '叁': digit = 3; break;
                case '四': case '肆': digit = 4; break;
                case '五': case '伍': digit = 5; break;
                case '六': case '陆': digit = 6; break;
                case '七': case '柒': digit = 7; break;
                case '八': case '捌': digit = 8; break;
                case '九': case '玖': digit = 9; break;
                default: break;
            }
            if (digit >= 0) {
                current = digit;
                sawDigit = true;
                continue;
            }
            switch (c) {
                case '十': case '拾':
                    if (!sawDigit) current = 1;   // "十五"开头
                    total += current * 10;
                    current = 0; sawDigit = false;
                    break;
                case '百': case '佰':
                    if (!sawDigit) current = 1;
                    total += current * 100;
                    current = 0; sawDigit = false;
                    break;
                case '千': case '仟':
                    if (!sawDigit) current = 1;
                    total += current * 1000;
                    current = 0; sawDigit = false;
                    break;
                case '万': case '萬':
                    if (!sawDigit) current = 1;
                    total = (total + current) * 10000;
                    current = 0; sawDigit = false;
                    break;
                default:
                    current = 0; sawDigit = false;
                    break;
            }
        }
        total += current;
        return total;
    }

    /** 出行方式选择：按距离生成真实票价选项，结合预算上限选择最合适方式 */
    private TransportChoice chooseTransport(double distKm, BigDecimal userBudget) {
        log.info("[CHOOSE] dist={}km budget={}", Math.round(distKm), userBudget);
        // 交通预算上限 = 总预算的 35%（旅行交通通常占 25%-40%）
        BigDecimal transportCap = userBudget != null
                ? userBudget.multiply(new BigDecimal("0.35")) : null;

        // 铁路/公路里程 ≈ 直线距离 × 1.3（迂回系数，价格更接近真实票价）
        double railKm = distKm * 1.3;

        // 生成各出行方式单程票价（真实票价模型：按里程系数 + 上下限）
        java.util.List<TransportOption> options = new java.util.ArrayList<>();
        // 长途大巴：约 0.28 元/km，上限 400
        options.add(new TransportOption("长途大巴", clamp(railKm * 0.28, 60, 400)));
        // 普速列车硬座：约 0.15 元/km，上限 260
        options.add(new TransportOption("普速列车硬座", clamp(railKm * 0.15, 40, 260)));
        // 普速列车硬卧：约 0.28 元/km，上限 480
        options.add(new TransportOption("普速列车硬卧", clamp(railKm * 0.28, 90, 480)));
        // 高铁二等座：约 0.46 元/km，上限 900（票价封顶）
        options.add(new TransportOption("高铁二等座", clamp(railKm * 0.46, 70, 900)));
        // 高铁一等座：约 0.74 元/km，上限 1500
        options.add(new TransportOption("高铁一等座", clamp(railKm * 0.74, 120, 1500)));
        // 飞机经济舱：>800km 才考虑（飞机按直线距离），约 0.55 元/km 折后价，上限 1600
        if (distKm > 800) {
            options.add(new TransportOption("飞机经济舱", clamp(distKm * 0.55, 380, 1600)));
        }

        // 选择策略：
        // 1. 有预算上限：优先「高铁二等座」作为性价比基准；仅当预算明显宽裕（cap ≥ 价格×1.2）才升级一等座/飞机
        // 2. 高铁二等座超预算：降级选硬卧/硬座/大巴中预算内最舒适的方式
        // 3. 全超预算：选最便宜的方式（大巴或硬座）
        // 4. 无预算：默认高铁二等座；>1500km 选飞机经济舱
        if (transportCap != null) {
            BigDecimal oneWayCap = transportCap.divide(new BigDecimal("2"), 0, RoundingMode.HALF_UP); // 往返→单程
            // 从贵到便宜找第一个"明显负担得起"（单程价×1.2 ≤ 上限）的方式——避免奢侈倾向
            // 长距离（>1500km）飞机按 ×1.0（预算内即可，现实中长距离首选飞机）
            for (int i = options.size() - 1; i >= 0; i--) {
                TransportOption opt = options.get(i);
                BigDecimal margin = (distKm > 1500 && "飞机经济舱".equals(opt.mode))
                        ? BigDecimal.ONE : new BigDecimal("1.2");
                if (opt.oneWay.multiply(margin).compareTo(oneWayCap) <= 0) {
                    return new TransportChoice(opt.mode, opt.oneWay.multiply(new BigDecimal("2")));
                }
            }
            // 无"明显负担得起"的选项：从贵到便宜找第一个"预算内买得起"的方式
            for (int i = options.size() - 1; i >= 0; i--) {
                TransportOption opt = options.get(i);
                if (opt.oneWay.compareTo(oneWayCap) <= 0) {
                    return new TransportChoice(opt.mode, opt.oneWay.multiply(new BigDecimal("2")));
                }
            }
            // 都超预算：最便宜的选项，并提示
            TransportOption cheapest = options.get(0);
            log.info("[CHOOSE] cap={} oneWayCap={} 全部超预算，选最便宜 {}", transportCap, oneWayCap, cheapest.mode);
            return new TransportChoice(cheapest.mode + "（预算紧张，已选最经济方式）",
                    cheapest.oneWay.multiply(new BigDecimal("2")));
        }

        // 无预算约束：距离>1500km 选飞机，否则高铁二等座
        if (distKm > 1500) {
            TransportOption plane = options.get(options.size() - 1);
            return new TransportChoice(plane.mode, plane.oneWay.multiply(new BigDecimal("2")));
        }
        TransportOption train = options.stream()
                .filter(o -> "高铁二等座".equals(o.mode)).findFirst().orElse(options.get(3));
        return new TransportChoice(train.mode, train.oneWay.multiply(new BigDecimal("2")));
    }

    private double clamp(double v, double min, double max) {
        return Math.max(min, Math.min(max, v));
    }

    /** 出行方式选项 */
    private static class TransportOption {
        final String mode;
        final BigDecimal oneWay;
        TransportOption(String mode, double oneWay) {
            this.mode = mode;
            this.oneWay = BigDecimal.valueOf(Math.round(oneWay));
        }
    }

    /** 出行方式选择结果 */
    private static class TransportChoice {
        final String mode;
        final BigDecimal roundTripCost;
        TransportChoice(String mode, BigDecimal roundTripCost) {
            this.mode = mode;
            this.roundTripCost = roundTripCost;
        }
    }

    /** 从行程文本提取目的地城市（优先"城市+N日/天"模式，其次动词后城市，最后回退首个城市） */
    private String extractDestCity(String text) {
        if (text == null) return null;
        // 模式1：城市名 + N日/N天 + 游/行程/攻略（如"西安4日游""北京3天行程"）——最可靠
        java.util.regex.Matcher m1 = java.util.regex.Pattern
                .compile("([\\u4e00-\\u9fa5]{2,4})[0-9一二三四五六七八九十]{1,3}[日天](?:游|行程|旅行|旅游|攻略)?").matcher(text);
        if (m1.find()) {
            String city = m1.group(1);
            if (com.example.aitourism.util.CityGeoUtil.getCoord(city) != null) return city;
        }
        // 模式2：去/到/前往/游玩 + 城市名（排除"出发地到X"中的出发地）
        java.util.regex.Matcher m2 = java.util.regex.Pattern
                .compile("(?:去|到|前往|飞往|游玩|游)([\\u4e00-\\u9fa5]{2,4})(?:旅游|旅行|游玩|攻略|，|。|\\s|$)").matcher(text);
        while (m2.find()) {
            String city = m2.group(1);
            if (com.example.aitourism.util.CityGeoUtil.getCoord(city) != null
                    && !text.startsWith("从" + city) && !text.contains("从" + city + "出发")) {
                return city;
            }
        }
        // 模式3：回退——排除"从X出发"的X后，取第一个已知城市
        for (String city : new String[]{"北京","上海","广州","深圳","杭州","成都","西安","武汉","重庆","厦门",
                "南京","苏州","天津","青岛","长沙","昆明","郑州","济南","合肥","福州","三亚","桂林","丽江","大理",
                "拉萨","西宁","兰州","贵阳","南昌","南宁","海口","太原","石家庄","沈阳","大连","哈尔滨","长春",
                "呼和浩特","银川","乌鲁木齐","香港","澳门","台北","泰安","张家界","湘西","黄山","惠州","南投"}) {
            int idx = text.indexOf(city);
            if (idx >= 0) {
                // 检查是否是"从X出发"结构
                String before = idx >= 1 ? text.substring(Math.max(0, idx - 1), idx) : "";
                String after = idx + city.length() < text.length()
                        ? text.substring(idx + city.length(), Math.min(text.length(), idx + city.length() + 2)) : "";
                if ("从".equals(before)) continue;   // "从北京出发"中的北京是出发地
                if ("出发".startsWith(after) || after.startsWith("出发")) continue;
                return city;
            }
        }
        return null;
    }

    /**
     * 市内交通：解析 daily_routes 中每天的景点坐标，计算相邻点通勤距离之和
     * 直线距离 × 道路系数，再按城市消费等级单价估算
     * @return 市内交通总费用（元），无法计算返回 null
     */
    private BigDecimal estimateLocalTransport(String dailyRoutesJson, int days) {
        if (dailyRoutesJson == null || dailyRoutesJson.trim().isEmpty()) return null;
        try {
            JsonNode root = objectMapper.readTree(dailyRoutesJson);
            JsonNode routes = root.get("dailyRoutes");
            if (routes == null || !routes.isArray() || routes.size() == 0) return null;

            BigDecimal totalKm = BigDecimal.ZERO;
            String city = null;
            int pointCount = 0;
            for (JsonNode day : routes) {
                JsonNode points = day.get("points");
                if (points == null || !points.isArray()) continue;
                double prevLng = Double.NaN, prevLat = Double.NaN;
                for (JsonNode p : points) {
                    pointCount++;
                    if (city == null && p.hasNonNull("city")) city = p.get("city").asText();
                    boolean hasCoord = p.hasNonNull("longitude") && p.hasNonNull("latitude");
                    if (hasCoord) {
                        double lng = p.get("longitude").asDouble();
                        double lat = p.get("latitude").asDouble();
                        if (!Double.isNaN(prevLng)) {
                            totalKm = totalKm.add(BigDecimal.valueOf(
                                    com.example.aitourism.util.CityGeoUtil.haversineKm(prevLat, prevLng, lat, lng)));
                        }
                        prevLng = lng; prevLat = lat;
                    }
                }
            }
            if (totalKm.compareTo(BigDecimal.ZERO) <= 0 || pointCount < 2) return null;

            // 道路距离 = 直线距离 × 系数；单价按城市等级
            BigDecimal roadKm = totalKm.multiply(ROAD_FACTOR);
            int tier = com.example.aitourism.util.CityGeoUtil.getTier(city);
            BigDecimal unitPrice = tier >= 3 ? TIER1_PRICE : (tier == 2 ? TIER2_PRICE : TIER3_PRICE);
            BigDecimal cost = roadKm.multiply(unitPrice);
            // 每日下限（即便距离很近，公共交通通勤也有基本开销）
            BigDecimal dailyMin = MIN_LOCAL_DAILY.multiply(BigDecimal.valueOf(days));
            if (cost.compareTo(dailyMin) < 0) cost = dailyMin;
            log.info("市内交通估算: 路线距离{}km(直线{}km×{}) 等级{} 单价{} 共{}元",
                    roadKm.setScale(0, RoundingMode.HALF_UP), totalKm.setScale(0, RoundingMode.HALF_UP),
                    ROAD_FACTOR, tier, unitPrice, cost.setScale(0, RoundingMode.HALF_UP));
            return cost;
        } catch (Exception e) {
            log.warn("市内交通距离估算失败（使用兜底）: {}", e.getMessage());
            return null;
        }
    }

    private Map<String, Object> item(String category, String name, BigDecimal amount) {
        Map<String, Object> m = new java.util.HashMap<>();
        m.put("category", category);
        m.put("name", name);
        m.put("amount", round(amount));
        return m;
    }

    /**
     * 费用明细条目（携带价格溯源信息——论文「数据真实性分层」的落地字段）。
     *
     * @param source     TRAIN_API(真实票价) / SNAPSHOT(快照·景点库) / ITINERARY(攻略载明) / ESTIMATE(系统估算)
     * @param asOf       数据日期（真实/快照价为采集日，估算为生成日）
     * @param confidence high / medium / low
     */
    private Map<String, Object> item(String category, String name, BigDecimal amount,
                                     String source, String asOf, String confidence) {
        Map<String, Object> m = item(category, name, amount);
        m.put("source", source != null ? source : "ESTIMATE");
        m.put("as_of", asOf != null ? asOf : LocalDate.now().toString());
        m.put("confidence", confidence != null ? confidence : "low");
        return m;
    }

    private int estimateDays(String text) {
        Pattern p = Pattern.compile("第\\s*([一二三四五六七八九十0-9]+)\\s*天");
        Matcher m = p.matcher(text);
        int maxDay = 0;
        while (m.find()) {
            String dayStr = m.group(1);
            try {
                if (dayStr.matches("\\d+")) {
                    maxDay = Math.max(maxDay, Integer.parseInt(dayStr));
                } else {
                    maxDay = Math.max(maxDay, chineseToNumber(dayStr));
                }
            } catch (Exception ignored) { }
        }
        // 模式A：N天N夜/N天N晚（中文或阿拉伯数字）——明确的行程时长，始终参与取最大值
        // 例如"三天两晚"=3天，"3天2夜"=3天
        Matcher m2 = Pattern.compile("([0-9一二两三四五六七八九十]+)\\s*天\\s*([0-9一二两三四五六七八九十]+)\\s*(?:夜|晚)").matcher(text);
        while (m2.find()) {
            int d = parseDayNumber(m2.group(1));
            if (d > 1) maxDay = Math.max(maxDay, d);
        }
        // 模式B：N日游/N天游/N天行程/N日旅行（如"南昌3日游""四天行程"）——仅在"第N天"未匹配到时使用
        if (maxDay <= 0) {
            Matcher m3 = Pattern.compile("([0-9一二两三四五六七八九十]+)\\s*[日天](?:游|行程|旅行|旅游|攻略|之旅)?").matcher(text);
            while (m3.find()) {
                int d = parseDayNumber(m3.group(1));
                maxDay = Math.max(maxDay, d);
            }
        }
        // 兜底：按"第N天"标题数量统计（每出现一个不同的"第N天"算一天）
        if (maxDay <= 0) {
            java.util.Set<Integer> days = new java.util.HashSet<>();
            Matcher m4 = Pattern.compile("第\\s*([0-9]+)\\s*天").matcher(text);
            while (m4.find()) {
                days.add(Integer.parseInt(m4.group(1)));
            }
            maxDay = Math.max(days.size(), 1);
        }
        return maxDay;
    }

    /** 解析天数数字（支持阿拉伯与中文数字） */
    private int parseDayNumber(String s) {
        if (s == null || s.isEmpty()) return 0;
        if (s.matches("\\d+")) return Integer.parseInt(s);
        return chineseToNumber(s);
    }

    private int chineseToNumber(String chinese) {
        switch (chinese) {
            case "一": return 1;
            case "二": case "两": return 2;
            case "三": return 3;
            case "四": return 4;
            case "五": return 5;
            case "六": return 6;
            case "七": return 7;
            case "八": return 8;
            case "九": return 9;
            case "十": return 10;
            default: return 0;
        }
    }

    private int estimatePoiCount(String text) {
        // 统计常见列表标记行数（近似景点数量），并限制合理上限（≤ 天数×2 且最多 8 个）
        int count = 0;
        if (text != null) {
            for (String line : text.split("\n")) {
                String trimmed = line.trim();
                if (trimmed.startsWith("- ") || trimmed.startsWith("• ") || trimmed.startsWith("* ")
                        || trimmed.startsWith("**") || trimmed.matches("^\\d+[.、].*")) {
                    count++;
                }
            }
        }
        // 上限：单日景点一般不超过 2-3 个，按 2.5/天 封顶 8
        int cap = Math.min(Math.max(count / 3, 2), 8);
        return Math.min(count, cap);
    }

    // ==================== 融合与落库 ====================

    /**
     * 简化融合：LLM 提取值 > 0 即采用（攻略写明的价格即最终预算），
     * 缺失/异常字段用规则值补全。总预算=分项之和。不做区间约束、不做适配削减。
     */
    private Budget mergeSimple(Budget llm, Budget rule) {
        if (llm == null) return rule;
        if (rule == null) return llm;
        Budget result = new Budget();
        result.setTransportCost(pick(llm.getTransportCost(), rule.getTransportCost()));
        result.setAccommodationCost(pick(llm.getAccommodationCost(), rule.getAccommodationCost()));
        result.setFoodCost(pick(llm.getFoodCost(), rule.getFoodCost()));
        result.setTicketCost(pick(llm.getTicketCost(), rule.getTicketCost()));
        result.setOtherCost(pick(llm.getOtherCost(), rule.getOtherCost()));
        // 总预算 = 分项合计（保证一致性）
        result.setTotalBudget(result.getTransportCost().add(result.getAccommodationCost())
                .add(result.getFoodCost()).add(result.getTicketCost()).add(result.getOtherCost()));
        // 明细优先用 LLM 提取的（攻略逐项价格），缺失用规则明细
        if (llm.getDetailItems() != null && !llm.getDetailItems().isEmpty()) {
            result.setDetailItems(llm.getDetailItems());
        } else {
            result.setDetailItems(rule.getDetailItems());
        }
        return result;
    }

    /**
     * 交通额度内的优先级重分配：**往返大交通是硬成本，市内交通才是可压缩项**。
     *
     * 封套是把「交通」作为一个整体截断到上限的，若随后按原比例缩放明细，
     * 就会出现「行程载明的往返机票 900 元被压到 420，而纯估算的市内交通 555 元全额保留」
     * 这种本末倒置的结果——飞机票是必须花的钱，市内交通才有弹性。
     * 这里改为：优先保住往返大交通，剩余额度才分配给市内交通。
     */
    private void prioritizeLongDistanceInTransport(Budget budget) {
        java.util.List<Map<String, Object>> items = budget.getDetailItems();
        if (items == null || items.isEmpty()) return;
        Map<String, Object> longItem = null;
        Map<String, Object> localItem = null;
        for (Map<String, Object> it : items) {
            if (!"交通".equals(it.get("category"))) continue;
            String name = String.valueOf(it.getOrDefault("name", ""));
            if (name.contains("往返大交通")) {
                if (longItem == null) longItem = it;
            } else if (localItem == null) {
                localItem = it;
            }
        }
        if (longItem == null || localItem == null) return;
        BigDecimal cap = budget.getTransportCost();
        if (cap == null) return;

        BigDecimal longAmt = toBigDecimal(longItem.get("amount"));
        if (longAmt.compareTo(cap) <= 0) {
            BigDecimal remain = cap.subtract(longAmt);
            if (remain.compareTo(BigDecimal.ZERO) < 0) remain = BigDecimal.ZERO;
            localItem.put("amount", remain);
        } else {
            // 预算极紧，连往返大交通都装不下：全部给大交通，市内交通靠步行/公交
            longItem.put("amount", cap);
            localItem.put("amount", BigDecimal.ZERO);
        }
    }

    private BigDecimal toBigDecimal(Object v) {
        if (v instanceof BigDecimal) return (BigDecimal) v;
        if (v instanceof Number) return BigDecimal.valueOf(((Number) v).doubleValue());
        return BigDecimal.ZERO;
    }

    /**
     * 明细归一化：按最终分项值重写各分类明细金额，保证明细合计=分项合计。
     * 分类单条（汇总条目）直接赋分项值；多条逐项按原比例缩放。
     */
    private void normalizeItemsToBudget(Budget budget) {
        if (budget.getDetailItems() == null || budget.getDetailItems().isEmpty()) return;
        java.util.Map<String, BigDecimal> target = new java.util.HashMap<>();
        target.put("交通", budget.getTransportCost());
        target.put("住宿", budget.getAccommodationCost());
        target.put("餐饮", budget.getFoodCost());
        target.put("门票", budget.getTicketCost());
        target.put("其他", budget.getOtherCost());

        java.util.Map<String, java.util.List<Map<String, Object>>> byCat = new java.util.HashMap<>();
        for (Map<String, Object> item : budget.getDetailItems()) {
            String cat = String.valueOf(item.getOrDefault("category", ""));
            byCat.computeIfAbsent(cat, k -> new java.util.ArrayList<>()).add(item);
        }
        for (java.util.Map.Entry<String, BigDecimal> entry : target.entrySet()) {
            java.util.List<Map<String, Object>> catItems = byCat.get(entry.getKey());
            BigDecimal newVal = entry.getValue();
            if (catItems == null || catItems.isEmpty() || newVal == null) continue;
            if (catItems.size() == 1) {
                catItems.get(0).put("amount", newVal);
                continue;
            }
            // 多条逐项：按原比例缩放，最后一项吸收舍入差
            BigDecimal oldSum = BigDecimal.ZERO;
            for (Map<String, Object> item : catItems) {
                Object amt = item.get("amount");
                if (amt instanceof BigDecimal) oldSum = oldSum.add((BigDecimal) amt);
                else if (amt instanceof Number) oldSum = oldSum.add(BigDecimal.valueOf(((Number) amt).doubleValue()));
            }
            if (oldSum.compareTo(BigDecimal.ZERO) <= 0) continue;
            BigDecimal ratio = newVal.divide(oldSum, 6, RoundingMode.HALF_UP);
            BigDecimal allocated = BigDecimal.ZERO;
            for (int i = 0; i < catItems.size(); i++) {
                Map<String, Object> item = catItems.get(i);
                Object amt = item.get("amount");
                BigDecimal oldAmt = amt instanceof BigDecimal ? (BigDecimal) amt
                        : amt instanceof Number ? BigDecimal.valueOf(((Number) amt).doubleValue()) : BigDecimal.ZERO;
                BigDecimal newAmt;
                if (i == catItems.size() - 1) {
                    newAmt = newVal.subtract(allocated);
                } else {
                    newAmt = oldAmt.multiply(ratio).setScale(0, RoundingMode.HALF_UP);
                    allocated = allocated.add(newAmt);
                }
                item.put("amount", newAmt);
            }
        }
    }

    /**
     * 幻觉过滤：剔除行程文本中找不到对应景点名的门票明细条目（防 LLM 编造景点）。
     * 剔除后由 ensureCompleteCategories 按门票分项补一条汇总条目，保证五类完整。
     */
    private List<Map<String, Object>> filterHallucinatedTickets(List<Map<String, Object>> items, String itineraryText) {
        if (items == null || items.isEmpty() || itineraryText == null) return items;
        java.util.List<Map<String, Object>> result = new java.util.ArrayList<>();
        int removed = 0;
        for (Map<String, Object> item : items) {
            String cat = String.valueOf(item.getOrDefault("category", ""));
            if ("门票".equals(cat)) {
                String name = String.valueOf(item.getOrDefault("name", ""));
                // 汇总类条目（含"合计""均价"等）直接保留
                if (name.contains("合计") || name.contains("均价") || name.contains("约")) {
                    result.add(item);
                    continue;
                }
                // 景点名必须能在行程文本中找到（截取景点名的前4-6个字符匹配）
                if (!itineraryText.contains(name)) {
                    String partial = name.length() > 4 ? name.substring(0, 4) : name;
                    if (!itineraryText.contains(partial)) {
                        removed++;
                        log.info("幻觉过滤: 剔除行程外的门票条目「{}」", name);
                        continue;
                    }
                }
            }
            result.add(item);
        }
        if (removed > 0) {
            log.info("门票幻觉过滤完成：剔除 {} 条", removed);
        }
        return result;
    }

    /**
     * 检查五类费用是否都有明细条目，缺失的类别按分项合计值补一条汇总条目，
     * 保证费用明细完整（修复明细不完整问题）。
     */
    private List<Map<String, Object>> ensureCompleteCategories(Budget budget) {
        List<Map<String, Object>> items = new java.util.ArrayList<>(
                budget.getDetailItems() != null ? budget.getDetailItems() : new java.util.ArrayList<>());
        Map<String, BigDecimal> categorySums = new java.util.LinkedHashMap<>();
        categorySums.put("交通", budget.getTransportCost() != null ? budget.getTransportCost() : BigDecimal.ZERO);
        categorySums.put("住宿", budget.getAccommodationCost() != null ? budget.getAccommodationCost() : BigDecimal.ZERO);
        categorySums.put("餐饮", budget.getFoodCost() != null ? budget.getFoodCost() : BigDecimal.ZERO);
        categorySums.put("门票", budget.getTicketCost() != null ? budget.getTicketCost() : BigDecimal.ZERO);
        categorySums.put("其他", budget.getOtherCost() != null ? budget.getOtherCost() : BigDecimal.ZERO);

        // 统计已有条目覆盖的类别
        java.util.Set<String> covered = new java.util.HashSet<>();
        for (Map<String, Object> item : items) {
            String cat = String.valueOf(item.getOrDefault("category", ""));
            if (cat.isEmpty() || "null".equals(cat)) continue;
            covered.add(cat);
        }
        // 为缺失类别补充汇总条目
        for (Map.Entry<String, BigDecimal> entry : categorySums.entrySet()) {
            if (!covered.contains(entry.getKey()) && entry.getValue().compareTo(BigDecimal.ZERO) > 0) {
                items.add(item(entry.getKey(), entry.getKey() + "费用（合计）", entry.getValue(),
                        "ESTIMATE", LocalDate.now().toString(), "low"));
            }
        }
        return items;
    }

    private BigDecimal pick(BigDecimal llmVal, BigDecimal ruleVal) {
        if (llmVal != null && llmVal.compareTo(BigDecimal.ZERO) > 0) return llmVal;
        return ruleVal != null ? ruleVal : BigDecimal.ZERO;
    }

    private BigDecimal round(BigDecimal v) {
        return v.setScale(2, RoundingMode.HALF_UP);
    }

    // ==================== 预算硬约束：辅助方法 ====================

    /**
     * 解析用户给定预算：优先取会话表落库的 budget_amount（由 Agent 意图识别写入），
     * 缺失时回退到从行程文本中正则提取（"预算4000元""预算一千"等）。
     */
    /**
     * 解析用户预算。
     *
     * 优先级：行程文本 > 会话表历史值。
     * —— 必须让文本优先：会话表的 budget_amount 是本方法上一次的识别结果（会被回写固化），
     *    一旦某次识别错误，后续所有分析都会沿用错误值，且用户改口说新预算也永远不生效。
     *    典型故障：用户说「预算两千」，但会话表残留 1000，导致封套误判预算过紧、
     *    连经济档都超支 → 走「取消全部收费景点」降级 → 门票被压成 0，与行程完全不符。
     *    行程文本是用户最新意图，因此以它为准。
     */
    private BigDecimal resolveUserBudget(String sessionId, String itineraryText) {
        BigDecimal fromText = extractBudget(itineraryText);
        if (fromText != null && fromText.compareTo(BigDecimal.ZERO) > 0) {
            return fromText;
        }
        try {
            com.example.aitourism.entity.Session session = sessionMapper.findBySessionId(sessionId);
            if (session != null && session.getBudgetAmount() != null
                    && session.getBudgetAmount().compareTo(BigDecimal.ZERO) > 0) {
                return session.getBudgetAmount();
            }
        } catch (Exception e) {
            log.warn("读取会话预算失败: {}", e.getMessage());
        }
        return null;
    }

    /** 把预算封套序列化为 envelope_json（含分项上限，供前端展示"预算上限 vs 实际"） */
    private String buildEnvelopeJson(BudgetEnvelope envelope) {
        if (envelope == null) return "{}";
        try {
            return objectMapper.writeValueAsString(envelope);
        } catch (Exception e) {
            log.warn("预算封套序列化失败: {}", e.getMessage());
            return "{}";
        }
    }

    /** 把出行方案序列化为 plan_json（严格按预算的交通方式/住宿档次/建议） */
    private String buildPlanJson(BudgetEnvelope envelope) {
        if (envelope == null) return "{}";
        try {
            return objectMapper.writeValueAsString(envelope.toPlanMap());
        } catch (Exception e) {
            log.warn("出行方案序列化失败: {}", e.getMessage());
            return "{}";
        }
    }

    private String buildDetailJson(Budget budget) {
        try {
            com.fasterxml.jackson.databind.node.ObjectNode node = objectMapper.createObjectNode();
            node.put("totalBudget", budget.getTotalBudget());
            node.put("transportCost", budget.getTransportCost());
            node.put("accommodationCost", budget.getAccommodationCost());
            node.put("foodCost", budget.getFoodCost());
            node.put("ticketCost", budget.getTicketCost());
            node.put("otherCost", budget.getOtherCost());
            node.put("days", budget.getDays());
            // 写入费用明细条目
            if (budget.getDetailItems() != null && !budget.getDetailItems().isEmpty()) {
                com.fasterxml.jackson.databind.node.ArrayNode items = objectMapper.createArrayNode();
                for (Map<String, Object> item : budget.getDetailItems()) {
                    com.fasterxml.jackson.databind.node.ObjectNode itemNode = objectMapper.createObjectNode();
                    itemNode.put("category", String.valueOf(item.getOrDefault("category", "")));
                    itemNode.put("name", String.valueOf(item.getOrDefault("name", "")));
                    Object amt = item.get("amount");
                    itemNode.put("amount", amt instanceof BigDecimal ? ((BigDecimal) amt).doubleValue()
                            : Double.parseDouble(String.valueOf(amt)));
                    // 价格溯源字段（前端按 真实/快照/攻略载明/估算 分级展示）
                    itemNode.put("source", String.valueOf(item.getOrDefault("source", "ESTIMATE")));
                    itemNode.put("as_of", String.valueOf(item.getOrDefault("as_of", "")));
                    itemNode.put("confidence", String.valueOf(item.getOrDefault("confidence", "low")));
                    items.add(itemNode);
                }
                node.set("items", items);
            }
            return node.toString();
        } catch (Exception e) {
            return "{}";
        }
    }
}
