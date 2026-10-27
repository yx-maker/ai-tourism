package com.example.aitourism.service.impl;

import com.example.aitourism.dto.budget.BudgetEnvelope;
import com.example.aitourism.entity.UserPreference;
import com.example.aitourism.mapper.POIMapper;
import com.example.aitourism.service.BudgetEnvelopeService;
import com.example.aitourism.service.PlanningContextService;
import com.example.aitourism.service.PriceProxyService;
import com.example.aitourism.service.UserPreferenceService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.langchain4j.model.chat.request.ResponseFormat;
import dev.langchain4j.model.openai.OpenAiChatModel;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static dev.langchain4j.model.chat.request.ResponseFormatType.JSON;

/**
 * 规划上下文服务实现。
 *
 * <p>所有外部取价都走 {@link PriceProxyService} 的三级降级链，
 * 任何一环失败都只影响对应参考行，不会阻断规划。
 */
@Service
@Slf4j
public class PlanningContextServiceImpl implements PlanningContextService {

    private final PriceProxyService priceProxyService;
    private final POIMapper poiMapper;
    private final BudgetEnvelopeService envelopeService;
    private final UserPreferenceService userPreferenceService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Value("${openai.api-key}")
    private String apiKey;

    @Value("${openai.base-url}")
    private String baseUrl;

    @Value("${openai.model-name}")
    private String modelName;

    public PlanningContextServiceImpl(PriceProxyService priceProxyService,
                                      POIMapper poiMapper,
                                      BudgetEnvelopeService envelopeService,
                                      UserPreferenceService userPreferenceService) {
        this.priceProxyService = priceProxyService;
        this.poiMapper = poiMapper;
        this.envelopeService = envelopeService;
        this.userPreferenceService = userPreferenceService;
    }

    // ==================================================================================
    // 一、构建注入上下文
    // ==================================================================================

    @Override
    public String buildContext(String userId, String userMessage) {
        if (userMessage == null || userMessage.isBlank()) {
            return "";
        }
        try {
            StringBuilder ctx = new StringBuilder();

            // ---- 1) 用户偏好记忆（开题报告：用户偏好表） ----
            String prefBlock = buildPreferenceBlock(userId);
            if (!prefBlock.isEmpty()) {
                ctx.append(prefBlock).append("\n\n");
            }

            // ---- 2) 解析需求（城市 / 天数 / 预算） ----
            String destCity = extractDestCity(userMessage);
            String originCity = com.example.aitourism.util.CityGeoUtil.extractOriginCity(userMessage, destCity);
            int days = extractDays(userMessage);
            BigDecimal budget = extractBudget(userMessage);

            // ---- 3) 真实价格参考（三级降级取价） ----
            if (destCity != null) {
                ctx.append(buildPriceBlock(originCity, destCity, days, budget));
            }

            // ---- 4) 预算硬约束（复用档次阶梯封套引擎） ----
            if (budget != null && destCity != null && days > 0) {
                String budgetBlock = buildBudgetBlock(originCity, destCity, days, budget);
                if (!budgetBlock.isEmpty()) {
                    ctx.append(budgetBlock);
                }
            }
            return ctx.toString().trim();
        } catch (Exception e) {
            // 上下文构建失败不能阻断对话
            log.warn("[CONTEXT] 规划上下文构建失败（本次不注入）: {}", e.getMessage());
            return "";
        }
    }

    /** 用户偏好块：仅当存在有效偏好时注入 */
    private String buildPreferenceBlock(String userId) {
        try {
            UserPreference pref = userPreferenceService.get(userId);
            if (pref == null) return "";
            StringBuilder sb = new StringBuilder("## 用户历史偏好（来自用户偏好设置，供个性化参考，不要生硬复述）\n");
            boolean any = false;
            if (pref.getTravelStyle() != null && !pref.getTravelStyle().isBlank()) {
                sb.append("- 旅行风格：").append(pref.getTravelStyle()).append("\n");
                any = true;
            }
            if (pref.getInterests() != null && !pref.getInterests().isBlank()) {
                sb.append("- 兴趣偏好：").append(pref.getInterests()).append("\n");
                any = true;
            }
            if (pref.getPace() != null && !pref.getPace().isBlank()) {
                sb.append("- 行程节奏：").append(pref.getPace()).append("\n");
                any = true;
            }
            if (pref.getCompanion() != null && !pref.getCompanion().isBlank()) {
                sb.append("- 同行人群：").append(pref.getCompanion()).append("\n");
                any = true;
            }
            if (pref.getBudgetMin() != null || pref.getBudgetMax() != null) {
                String min = pref.getBudgetMin() != null ? pref.getBudgetMin().toPlainString() : "不限";
                String max = pref.getBudgetMax() != null ? pref.getBudgetMax().toPlainString() : "不限";
                sb.append("- 常用预算区间：").append(min).append(" ~ ").append(max).append(" 元\n");
                any = true;
            }
            return any ? sb.toString() : "";
        } catch (Exception e) {
            log.debug("[CONTEXT] 偏好读取失败（忽略）: {}", e.getMessage());
            return "";
        }
    }

    /** 真实价格参考块（三级降级：真实 API → 快照 → 估算） */
    private String buildPriceBlock(String originCity, String destCity, int days, BigDecimal budget) {
        StringBuilder sb = new StringBuilder();
        sb.append("## 真实价格参考（来源可信，费用表请优先采用；拿不到真实价格的项会标注「系统估算」）\n");
        boolean anyReal = false;

        // 往返大交通
        BigDecimal transport = null;
        String transportLabel = null;
        String routeDesc = (originCity != null ? originCity + "→" + destCity : "往返" + destCity);
        if (originCity != null && priceProxyService.trainApiEnabled()) {
            List<PriceProxyService.SeatQuote> quotes =
                    priceProxyService.trainQuotes(originCity, destCity, LocalDate.now().toString());
            if (!quotes.isEmpty()) {
                PriceProxyService.SeatQuote pick = pickSeat(quotes, budget);
                transport = pick.price().multiply(BigDecimal.valueOf(2));
                transportLabel = pick.seatType();
                sb.append(String.format("- 往返大交通：%s %s 单程约 ¥%s（真实票价·12306同步聚合API，%s）%n",
                        routeDesc, pick.seatType(), pick.price().toPlainString(), LocalDate.now()));
                anyReal = true;
            }
        }
        if (transport == null) {
            // 系数模型兜底（与 BudgetServiceImpl.chooseTransport 同口径）
            double dist = originCity != null
                    ? com.example.aitourism.util.CityGeoUtil.distanceKm(originCity, destCity) : -1;
            if (dist > 50) {
                double railKm = dist * 1.3;
                double oneWay = Math.max(70, Math.min(railKm * 0.46, 900));
                transport = BigDecimal.valueOf(Math.round(oneWay * 2));
                transportLabel = "高铁二等座";
                sb.append(String.format("- 往返大交通：%s 约 %s km，高铁二等座往返约 ¥%s（系统估算·里程系数模型）%n",
                        routeDesc, Math.round(dist), transport.toPlainString()));
            }
        }

        // 住宿快照（三档）
        Map<String, BigDecimal> hotelOverrides = new HashMap<>();
        String[][] tiers = {{"经济", "economy"}, {"舒适", "comfort"}, {"品质", "premium"}};
        for (String[] t : tiers) {
            PriceProxyService.HotelSnapshot snap = priceProxyService.hotelPrice(destCity, t[1]);
            if (snap != null) {
                hotelOverrides.put(t[0], snap.pricePerNight());
                sb.append(String.format("- 住宿参考：%s %s型酒店约 ¥%s/晚（快照价·%s，%s）%n",
                        destCity, t[0], snap.pricePerNight().toPlainString(),
                        snap.sampleHotel(), snap.collectedDate()));
                anyReal = true;
            }
        }

        // 景点门票（景点库真实票价）
        try {
            BigDecimal avg = poiMapper.avgTicketPriceByCity(destCity);
            int cnt = poiMapper.countPricedPoiByCity(destCity);
            if (avg != null && avg.compareTo(BigDecimal.ZERO) > 0 && cnt > 0) {
                sb.append(String.format("- 景点门票：%s 收费景点平均约 ¥%s/个（景点库真实票价，%d个景点）%n",
                        destCity, avg.setScale(0, RoundingMode.HALF_UP).toPlainString(), cnt));
                anyReal = true;
            }
        } catch (Exception ignored) {
        }

        if (!anyReal) {
            // 一条真实数据都没有：不注入价格块，避免纯估算噪音
            return "";
        }
        return sb.toString();
    }

    /** 预算硬约束块（复用 BudgetEnvelopeService 档次阶梯引擎） */
    private String buildBudgetBlock(String originCity, String destCity, int days, BigDecimal budget) {
        // 大交通：真实票价优先，否则系数模型
        BigDecimal transport;
        String mode;
        if (originCity != null && priceProxyService.trainApiEnabled()) {
            List<PriceProxyService.SeatQuote> quotes =
                    priceProxyService.trainQuotes(originCity, destCity, LocalDate.now().toString());
            if (!quotes.isEmpty()) {
                PriceProxyService.SeatQuote pick = pickSeat(quotes, budget);
                transport = pick.price().multiply(BigDecimal.valueOf(2));
                mode = pick.seatType() + "（12306实时票价）";
            } else {
                double dist = com.example.aitourism.util.CityGeoUtil.distanceKm(originCity, destCity);
                double oneWay = dist > 50 ? Math.max(70, Math.min(dist * 1.3 * 0.46, 900)) : 400;
                transport = BigDecimal.valueOf(Math.round(oneWay * 2));
                mode = "高铁二等座（系统估算）";
            }
        } else {
            transport = BigDecimal.valueOf(800);
            mode = "高铁二等座（系统估算·按典型跨省里程）";
        }

        Map<String, BigDecimal> hotelOverrides = new HashMap<>();
        String[][] tiers = {{"经济", "economy"}, {"舒适", "comfort"}, {"品质", "premium"}};
        for (String[] t : tiers) {
            PriceProxyService.HotelSnapshot snap = priceProxyService.hotelPrice(destCity, t[1]);
            if (snap != null) {
                hotelOverrides.put(t[0], snap.pricePerNight());
            }
        }

        BudgetEnvelope env = envelopeService.build(budget, days, Math.max(days * 2, 2),
                transport, mode, hotelOverrides);

        StringBuilder sb = new StringBuilder();
        sb.append("## 预算硬约束（必须严格遵守，优先级高于景点数量与住宿舒适度）\n");
        sb.append(String.format("- 用户总预算：**%s 元**，行程 %d 天（%d 晚），往返大交通约 %s 元（%s）%n",
                budget.toPlainString(), env.getDays(), env.getNights(),
                env.getTransportCost().toPlainString(), env.getTransportMode()));
        if (env.isFeasible()) {
            sb.append(String.format("- 档次判定：按「%s」档执行，预计总花费 %s 元，结余 %s 元%n",
                    env.getLevel(), env.getTotal().toPlainString(), env.getRemaining().toPlainString()));
            sb.append(String.format("- 分项标准：住宿 %s 元/晚（%s）、餐饮 %s 元/天、市内交通 %s 元/天、门票合计 %s 元、其他 %s 元%n",
                    env.getHotelPerNight().toPlainString(), env.getHotelTier(),
                    env.getFoodPerDay().toPlainString(), env.getLocalPerDay().toPlainString(),
                    env.getTicketTotal().toPlainString(), env.getOtherTotal().toPlainString()));
            for (String adj : env.getAdjustments()) {
                sb.append("- 调整记录：").append(adj).append("\n");
            }
            sb.append(String.format("- **最终方案总花费不得超过 %s 元**，攻略末尾必须输出费用参考表"
                    + "（交通/住宿/餐饮/门票/其他+合计），分项之和等于合计且合计 ≤ %s 元%n",
                    budget.toPlainString(), budget.toPlainString()));
        } else {
            sb.append(String.format("- ⚠️ **预算不足，无法支撑 %d 天行程**：最低可行预算约 %s 元，缺口约 %s 元%n",
                    env.getDays(), env.getMinBudget().toPlainString(),
                    env.getMinBudget().subtract(budget).toPlainString()));
            sb.append("- **必须先在攻略开头明确说明预算不足**，然后给出下列方案（可组合）：\n");
            for (String s : env.getSuggestions()) {
                sb.append("  - ").append(s).append("\n");
            }
            sb.append("- 注意：不得在预算内硬凑虚假低价行程，所有价格必须使用上方参考价口径\n");
        }
        return sb.toString();
    }

    /** 从真实报价中按预算选席别（默认二等座；预算紧则预算内最便宜） */
    private PriceProxyService.SeatQuote pickSeat(List<PriceProxyService.SeatQuote> quotes, BigDecimal budget) {
        PriceProxyService.SeatQuote second = quotes.stream()
                .filter(q -> "二等座".equals(q.seatType()) || "硬卧".equals(q.seatType()))
                .findFirst().orElse(null);
        if (budget != null && budget.compareTo(BigDecimal.ZERO) > 0) {
            BigDecimal oneWayCap = budget.multiply(BigDecimal.valueOf(0.35))
                    .divide(BigDecimal.valueOf(2), 0, RoundingMode.HALF_UP);
            if (second != null && second.price().compareTo(oneWayCap) <= 0) {
                return second;
            }
            return quotes.stream()
                    .filter(q -> q.price().compareTo(oneWayCap) <= 0)
                    .max(java.util.Comparator.comparing(PriceProxyService.SeatQuote::price))
                    .orElseGet(() -> quotes.stream()
                            .min(java.util.Comparator.comparing(PriceProxyService.SeatQuote::price))
                            .orElse(second));
        }
        return second != null ? second
                : quotes.stream().max(java.util.Comparator.comparing(PriceProxyService.SeatQuote::price)).orElse(null);
    }

    // ==================================================================================
    // 二、偏好画像沉淀（LLM 一次性抽取）
    // ==================================================================================

    @Override
    public void extractAndSavePreferences(String userId, String userMessage, String assistantReply) {
        if (userId == null || userMessage == null || userMessage.isBlank()) {
            return;
        }
        try {
            UserPreference existing = userPreferenceService.get(userId);
            String prompt = """
                    ## 任务
                    从下面这轮旅游规划对话中，抽取用户的旅行偏好画像。只输出 JSON，不要输出其他文字。
                    字段说明（抽不到就保留原值 null，不要猜测编造）：
                    - travel_style: 旅行风格，如「历史文化」「自然风光」「休闲度假」「城市漫步」「美食之旅」
                    - interests: 兴趣标签，逗号分隔，如「历史古迹,美食,摄影」
                    - pace: 行程节奏，「紧凑」/「适中」/「宽松」
                    - companion: 同行人群，「独自」/「情侣」/「家庭(带小孩)」/「家庭(带老人)」/「朋友」
                    - budget_min / budget_max: 若对话中明确提到预算区间，填数字（元），否则 null

                    ## 用户消息
                    %s

                    ## 助手回复（截断）
                    %s

                    ## 输出格式
                    {"travel_style": null, "interests": null, "pace": null, "companion": null, "budget_min": null, "budget_max": null}
                    """.formatted(
                    userMessage.length() > 800 ? userMessage.substring(0, 800) : userMessage,
                    assistantReply != null && assistantReply.length() > 400
                            ? assistantReply.substring(0, 400) : String.valueOf(assistantReply));

            OpenAiChatModel model = OpenAiChatModel.builder()
                    .apiKey(apiKey)
                    .baseUrl(baseUrl)
                    .modelName(modelName)
                    .responseFormat(ResponseFormat.builder().type(JSON).build())
                    .build();
            String result = model.chat(prompt);
            JsonNode node = objectMapper.readTree(result);

            UserPreference pref = existing != null ? existing : new UserPreference();
            pref.setUserId(userId);
            if (node.hasNonNull("travel_style")) pref.setTravelStyle(node.get("travel_style").asText());
            if (node.hasNonNull("interests")) pref.setInterests(node.get("interests").asText());
            if (node.hasNonNull("pace")) pref.setPace(node.get("pace").asText());
            if (node.hasNonNull("companion")) pref.setCompanion(node.get("companion").asText());
            if (node.hasNonNull("budget_min")) {
                try {
                    pref.setBudgetMin(new BigDecimal(node.get("budget_min").asText()));
                } catch (Exception ignored) {
                }
            }
            if (node.hasNonNull("budget_max")) {
                try {
                    pref.setBudgetMax(new BigDecimal(node.get("budget_max").asText()));
                } catch (Exception ignored) {
                }
            }
            userPreferenceService.save(userId, pref);
            log.info("[MEMORY] 用户{} 偏好画像已更新: 风格={} 兴趣={} 节奏={} 同行={}",
                    userId, pref.getTravelStyle(), pref.getInterests(), pref.getPace(), pref.getCompanion());
        } catch (Exception e) {
            // 记忆沉淀失败静默处理：不影响主流程，也不写入任何猜测值
            log.debug("[MEMORY] 偏好画像抽取失败（忽略）: {}", e.getMessage());
        }
    }

    // ==================================================================================
    // 三、轻量需求解析（与 BudgetServiceImpl 同口径的简化版）
    // ==================================================================================

    /**
     * 目的地城市：遍历坐标库已知城市名（长名优先），排除「从X出发」结构中的出发地。
     * 相比正则匹配，对「去成都玩5天」「成都5天行程」等自然表达更稳健。
     */
    static String extractDestCity(String text) {
        if (text == null) return null;
        // 先收集出发地（从X出发 / X出发 / 由X来 …）
        java.util.Set<String> origins = new java.util.HashSet<>();
        Matcher origin = Pattern.compile("(?:从|由|自)?([\\u4e00-\\u9fa5]{2,4})(?:出发|过来|来|启程|动身)").matcher(text);
        while (origin.find()) {
            origins.add(origin.group(1));
        }
        // 城市名长的优先（「西双版纳」优先于「西安」），取第一个非出发地的已知城市
        List<String> cities = com.example.aitourism.util.CityGeoUtil.knownCities().stream()
                .sorted((a, b) -> b.length() - a.length())
                .toList();
        for (String city : cities) {
            int idx = text.indexOf(city);
            if (idx < 0 || origins.contains(city)) continue;
            String before = idx >= 1 ? text.substring(idx - 1, idx) : "";
            if ("从".equals(before) || "由".equals(before) || "自".equals(before)) continue;
            int end = Math.min(text.length(), idx + city.length() + 2);
            String after = text.substring(idx + city.length(), end);
            if (after.startsWith("出发")) continue;
            return city;
        }
        return null;
    }

    /** 行程天数：N天/N日/N天N晚 */
    static int extractDays(String text) {
        if (text == null) return 0;
        int maxDay = 0;
        Matcher m = Pattern.compile("([0-9一二两三四五六七八九十]+)\\s*天\\s*([0-9一二两三四五六七八九十]+)\\s*[夜晚]").matcher(text);
        while (m.find()) {
            maxDay = Math.max(maxDay, parseDayNum(m.group(1)));
        }
        Matcher m2 = Pattern.compile("([0-9一二两三四五六七八九十]+)\\s*[日天]").matcher(text);
        while (m2.find()) {
            maxDay = Math.max(maxDay, parseDayNum(m2.group(1)));
        }
        return maxDay;
    }

    private static int parseDayNum(String s) {
        if (s == null || s.isEmpty()) return 0;
        if (s.matches("\\d+")) return Integer.parseInt(s);
        return switch (s) {
            case "一" -> 1;
            case "二", "两" -> 2;
            case "三" -> 3;
            case "四" -> 4;
            case "五" -> 5;
            case "六" -> 6;
            case "七" -> 7;
            case "八" -> 8;
            case "九" -> 9;
            case "十" -> 10;
            default -> 0;
        };
    }

    /** 用户预算：数字+元 / 中文数字+元 */
    static BigDecimal extractBudget(String text) {
        if (text == null) return null;
        Matcher m = Pattern.compile("(\\d{3,6})\\s*(?:元|块|块钱|人民币)").matcher(text);
        while (m.find()) {
            int val = Integer.parseInt(m.group(1));
            if (val >= 500 && val <= 100000) return BigDecimal.valueOf(val);
        }
        Matcher m2 = Pattern.compile("([零一二两三四五六七八九十百千万]+)\\s*(?:元|块钱|人民币)").matcher(text);
        while (m2.find()) {
            String numStr = m2.group(1);
            if (!numStr.contains("千") && !numStr.contains("万")) continue;
            int val = chineseToNumber(numStr);
            if (val >= 500 && val <= 100000) return BigDecimal.valueOf(val);
        }
        return null;
    }

    private static int chineseToNumber(String chinese) {
        int total = 0, current = 0;
        boolean sawDigit = false;
        for (char c : chinese.toCharArray()) {
            int digit = switch (c) {
                case '零' -> 0;
                case '一', '壹' -> 1;
                case '二', '两', '贰' -> 2;
                case '三', '叁' -> 3;
                case '四' -> 4;
                case '五' -> 5;
                case '六' -> 6;
                case '七' -> 7;
                case '八' -> 8;
                case '九' -> 9;
                default -> -1;
            };
            if (digit >= 0) {
                current = digit;
                sawDigit = true;
                continue;
            }
            switch (c) {
                case '十', '拾' -> {
                    if (!sawDigit) current = 1;
                    total += current * 10;
                }
                case '百', '佰' -> {
                    if (!sawDigit) current = 1;
                    total += current * 100;
                }
                case '千', '仟' -> {
                    if (!sawDigit) current = 1;
                    total += current * 1000;
                }
                case '万', '萬' -> {
                    if (!sawDigit) current = 1;
                    total = (total + current) * 10000;
                }
                default -> {
                }
            }
            current = 0;
            sawDigit = false;
        }
        return total + current;
    }
}
