package com.example.aitourism.service.impl;

import com.example.aitourism.entity.Budget;
import com.example.aitourism.entity.Message;
import com.example.aitourism.entity.Session;
import com.example.aitourism.entity.TravelPlan;
import com.example.aitourism.mapper.BudgetMapper;
import com.example.aitourism.mapper.ChatMessageMapper;
import com.example.aitourism.mapper.SessionMapper;
import com.example.aitourism.mapper.TravelPlanMapper;
import com.example.aitourism.service.BudgetService;
import com.example.aitourism.service.TravelPlanService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 旅行计划服务实现。
 *
 * <p>编辑重算的工程保证（对应同学项目「编辑后服务端确定性重算」的长处）：
 * 用户编辑行程内容后，预算不由前端计算、也不重新问大模型，
 * 而是调用与首次分析完全相同的 {@link BudgetService#analyze} 在服务端重算，
 * 保证「同一份行程文本 → 同一个预算结果」的可复现性。
 */
@Service
@Slf4j
public class TravelPlanServiceImpl implements TravelPlanService {

    private final TravelPlanMapper travelPlanMapper;
    private final SessionMapper sessionMapper;
    private final ChatMessageMapper chatMessageMapper;
    private final BudgetMapper budgetMapper;
    private final BudgetService budgetService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public TravelPlanServiceImpl(TravelPlanMapper travelPlanMapper,
                                 SessionMapper sessionMapper,
                                 ChatMessageMapper chatMessageMapper,
                                 BudgetMapper budgetMapper,
                                 BudgetService budgetService) {
        this.travelPlanMapper = travelPlanMapper;
        this.sessionMapper = sessionMapper;
        this.chatMessageMapper = chatMessageMapper;
        this.budgetMapper = budgetMapper;
        this.budgetService = budgetService;
    }

    @Override
    public TravelPlan saveFromSession(String sessionId, String userId, String titleOverride) {
        if (sessionId == null || sessionId.isBlank()) {
            throw new RuntimeException("3001: 会话ID不能为空");
        }
        Session session = sessionMapper.findBySessionId(sessionId);
        if (session == null) {
            throw new RuntimeException("3002: 会话不存在");
        }
        // 对象级授权：只能保存自己的会话
        if (session.getUserId() != null && !session.getUserId().equals(userId)) {
            throw new RuntimeException("3003: 无权访问该会话");
        }

        // 取会话中最后一条助手消息作为攻略全文
        List<Message> messages = chatMessageMapper.findBySessionId(sessionId);
        String content = null;
        for (int i = messages.size() - 1; i >= 0; i--) {
            Message m = messages.get(i);
            if ("assistant".equals(m.getRole()) && m.getContent() != null
                    && m.getContent().length() > 50) {
                content = m.getContent();
                break;
            }
        }
        if (content == null || content.isBlank()) {
            throw new RuntimeException("3004: 该会话还没有可保存的行程内容，请先生成攻略");
        }

        String dailyRoutes = session.getDailyRoutes();
        int days = estimateDays(content);
        String destCity = extractDestCity(dailyRoutes, content);

        // 幂等：同一会话重复保存 → 更新已有计划（而不是堆积重复计划）
        TravelPlan existing = travelPlanMapper.findByPlanId("PLAN-" + sessionId);
        TravelPlan plan = existing != null ? existing : new TravelPlan();
        boolean isNew = existing == null;
        if (isNew) {
            plan.setPlanId("PLAN-" + sessionId);
            plan.setUserId(userId);
            plan.setSessionId(sessionId);
            plan.setStatus("ACTIVE");
            plan.setVersion(0);
        }
        plan.setTitle(titleOverride != null && !titleOverride.isBlank()
                ? titleOverride.trim()
                : buildTitle(session.getTitle(), destCity, days));
        plan.setDestCity(destCity);
        plan.setOriginCity(session.getOriginCity());
        plan.setDays(days);
        plan.setBudgetAmount(session.getBudgetAmount());
        plan.setContent(content);
        plan.setDailyRoutes(dailyRoutes);
        // 预算快照：复用该会话已有的分析结果（含价格来源明细）
        try {
            Budget budget = budgetMapper.findBySessionId(sessionId);
            if (budget != null && budget.getDetailJson() != null) {
                plan.setBudgetJson(budget.getDetailJson());
            }
        } catch (Exception e) {
            log.warn("读取会话预算快照失败（保存时留空，可在计划页重新分析）: {}", e.getMessage());
        }

        int rows = isNew ? travelPlanMapper.insert(plan)
                : travelPlanMapper.updateWithVersionCheck(plan.getPlanId(), userId, plan.getVersion(),
                plan.getTitle(), plan.getDestCity(), plan.getOriginCity(), plan.getDays(),
                plan.getBudgetAmount(), plan.getContent(), plan.getDailyRoutes(), plan.getBudgetJson());
        if (rows <= 0) {
            throw new RuntimeException("4090: 计划已被其他会话修改，请刷新后重试");
        }
        log.info("行程保存: 会话{} → 计划{}（{}天/{}）", sessionId, plan.getPlanId(), days,
                isNew ? "新建" : "更新");
        return plan;
    }

    @Override
    public Map<String, Object> list(String userId, Integer page, Integer pageSize) {
        int p = (page == null || page < 1) ? 1 : page;
        int size = (pageSize == null || pageSize < 1) ? 10 : Math.min(pageSize, 50);
        List<TravelPlan> list = travelPlanMapper.pageByUser(userId, (p - 1) * size, size);
        long total = travelPlanMapper.countByUser(userId);
        Map<String, Object> result = new HashMap<>();
        result.put("list", list);
        result.put("total", total);
        result.put("page", p);
        result.put("page_size", size);
        return result;
    }

    @Override
    public TravelPlan detail(String planId, String userId) {
        TravelPlan plan = travelPlanMapper.findByPlanIdAndUser(planId, userId);
        if (plan == null) {
            throw new RuntimeException("3005: 计划不存在或无权访问");
        }
        return plan;
    }

    @Override
    public TravelPlan update(String planId, String userId, Integer expectedVersion,
                             String title, Integer days, BigDecimal budgetAmount,
                             String content, String dailyRoutes) {
        TravelPlan plan = travelPlanMapper.findByPlanIdAndUser(planId, userId);
        if (plan == null) {
            throw new RuntimeException("3005: 计划不存在或无权访问");
        }
        if (expectedVersion == null || !expectedVersion.equals(plan.getVersion())) {
            throw new RuntimeException("4090: 计划已被其他会话修改（版本冲突），请刷新后重试");
        }
        // 行程内容变化 → 服务端确定性重算预算（与首次分析同一引擎，保证可复现）
        String newBudgetJson = plan.getBudgetJson();
        boolean contentChanged = content != null && !content.isBlank()
                && !content.equals(plan.getContent());
        if (contentChanged) {
            try {
                Budget recomputed = budgetService.analyze(planId, userId, content);
                if (recomputed != null && recomputed.getDetailJson() != null) {
                    newBudgetJson = recomputed.getDetailJson();
                }
                log.info("计划{} 行程内容已变更，服务端重算预算: 总预算{}元 状态{}",
                        planId, recomputed != null ? recomputed.getTotalBudget() : null,
                        recomputed != null ? recomputed.getBudgetStatus() : null);
            } catch (Exception e) {
                log.warn("计划{} 预算重算失败（保留原快照）: {}", planId, e.getMessage());
            }
        }
        // 天数变化时同步修正标题中的天数（若标题含「N天」）
        int finalDays = days != null && days > 0 ? days : plan.getDays();
        String finalTitle = title;
        if ((finalTitle == null || finalTitle.isBlank()) && days != null && days > 0
                && !days.equals(plan.getDays()) && plan.getTitle() != null) {
            finalTitle = plan.getTitle().replaceAll("\\d+\\s*天", finalDays + "天");
        }

        int rows = travelPlanMapper.updateWithVersionCheck(planId, userId, expectedVersion,
                finalTitle, null, null, days, budgetAmount,
                content, dailyRoutes, newBudgetJson);
        if (rows <= 0) {
            throw new RuntimeException("4090: 计划已被其他会话修改（版本冲突），请刷新后重试");
        }
        TravelPlan updated = travelPlanMapper.findByPlanIdAndUser(planId, userId);
        if (updated != null) {
            updated.setDays(finalDays);
        }
        return updated;
    }

    @Override
    public boolean archive(String planId, String userId) {
        return travelPlanMapper.archiveByPlanId(planId, userId) > 0;
    }

    // ==================================================================================
    // 辅助方法
    // ==================================================================================

    /** 从攻略文本估算天数（第N天 / N天N晚 / N日游） */
    static int estimateDays(String text) {
        if (text == null) return 1;
        int maxDay = 0;
        Matcher m = Pattern.compile("第\\s*([0-9一二两三四五六七八九十]+)\\s*天").matcher(text);
        while (m.find()) {
            int d = parseDay(m.group(1));
            maxDay = Math.max(maxDay, d);
        }
        Matcher m2 = Pattern.compile("([0-9一二两三四五六七八九十]+)\\s*天\\s*([0-9一二两三四五六七八九十]+)\\s*[夜晚]").matcher(text);
        while (m2.find()) {
            int d = parseDay(m2.group(1));
            if (d > 1) maxDay = Math.max(maxDay, d);
        }
        if (maxDay <= 0) {
            Matcher m3 = Pattern.compile("([0-9一二两三四五六七八九十]+)\\s*[日天](?:游|行程|旅行|旅游|攻略|之旅)").matcher(text);
            while (m3.find()) {
                maxDay = Math.max(maxDay, parseDay(m3.group(1)));
            }
        }
        return Math.max(maxDay, 1);
    }

    private static int parseDay(String s) {
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

    /** 目的地城市：优先取路线 JSON 中首个点位的 city，其次从标题/正文提取 */
    private String extractDestCity(String dailyRoutes, String content) {
        if (dailyRoutes != null && !dailyRoutes.isBlank()) {
            try {
                JsonNode root = objectMapper.readTree(dailyRoutes);
                JsonNode routes = root.get("dailyRoutes");
                if (routes != null && routes.isArray()) {
                    for (JsonNode day : routes) {
                        JsonNode points = day.get("points");
                        if (points != null && points.isArray()) {
                            for (JsonNode p : points) {
                                if (p.hasNonNull("city") && !p.get("city").asText().isBlank()) {
                                    return p.get("city").asText();
                                }
                            }
                        }
                    }
                }
            } catch (Exception ignored) {
            }
        }
        return null;
    }

    private String buildTitle(String sessionTitle, String destCity, int days) {
        if (sessionTitle != null && !sessionTitle.isBlank()) {
            return sessionTitle.length() > 120 ? sessionTitle.substring(0, 120) : sessionTitle;
        }
        String city = destCity != null ? destCity + " " : "";
        return city + days + "天旅行计划";
    }
}
