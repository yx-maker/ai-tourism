package com.example.aitourism.service;

import com.example.aitourism.dto.budget.BudgetEnvelope;
import com.example.aitourism.dto.budget.TransportDuration;
import com.example.aitourism.entity.Budget;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Map;

/**
 * 预算封套服务（Budget Envelope Service）—— 预算硬约束规划引擎。
 *
 * <p>论文定位：把「预算」从<b>事后统计指标</b>升级为<b>事前约束条件</b>。
 *
 * <h3>核心算法：档次阶梯回退（Tier Ladder Fallback）</h3>
 * <p>给定「总预算 + 天数 + 出发地→目的地」，先由既有票价模型选出往返大交通，
 * 再把剩余可支配预算交给三级消费档次阶梯，自高向低试探，取<b>预算内可承受的最高档</b>：
 *
 * <pre>
 *   品质档合计 ≤ 预算 ?  采用品质档
 *        否则 舒适档合计 ≤ 预算 ?  采用舒适档
 *             否则 经济档合计 ≤ 预算 ?  采用经济档
 *                  否则 经济档 + 免费景点为主 ≤ 预算 ?  采用并提示
 *                       否则 判定不可行，给出最低可行预算与降级建议
 * </pre>
 *
 * <p>该算法是 O(3) 的确定性过程，无随机性、无外部依赖，可在单元测试中完全覆盖，
 * 相比「让大模型自己估」具有可复现、可解释、可验证的优势——这正是论文可量化的对比点。
 *
 * <h3>与 {@link BudgetServiceImpl} 的分工</h3>
 * <ul>
 *   <li>{@code BudgetEnvelopeService}：事前——算出「该花多少、怎么花」的上限封套</li>
 *   <li>{@code BudgetServiceImpl}：事后——从行程文本提取实际费用，并用封套<b>核验与再平衡</b></li>
 * </ul>
 */
@Service
@Slf4j
public class BudgetEnvelopeService {

    /** 门票均价（元/景点），与规则引擎 AVG_TICKET 口径一致 */
    private static final BigDecimal TICKET_AVG = new BigDecimal("70");

    /** 消费档次阶梯：由高到低排列，取预算内最高档 */
    private static final List<SpendTier> TIERS = List.of(
            new SpendTier("品质", 480, 220, 80, new BigDecimal("1.30"), 120, "高档酒店 / 精品民宿", "特色餐饮为主"),
            new SpendTier("舒适", 260, 120, 45, new BigDecimal("1.00"), 60, "舒适型连锁酒店", "常规餐饮"),
            new SpendTier("经济", 120, 70, 25, new BigDecimal("0.60"), 30, "青旅 / 经济型连锁", "简餐为主")
    );

    /** 预算达成状态：在预算内 */
    public static final String STATUS_WITHIN = "WITHIN_BUDGET";
    /** 预算达成状态：超出预算 */
    public static final String STATUS_OVER = "OVER_BUDGET";
    /** 预算达成状态：用户未指定预算 */
    public static final String STATUS_UNKNOWN = "UNKNOWN";

    /**
     * 消费档次定义。
     *
     * @param name          档次名
     * @param hotelPerNight 住宿单价（元/晚）
     * @param foodPerDay    餐饮（元/天）
     * @param localPerDay   市内交通（元/天）
     * @param ticketFactor  门票系数（相对均价，品质档会去更贵的收费景点）
     * @param otherPerDay   其他（元/天）
     * @param hotelTierName 住宿档次描述
     * @param foodTierName  餐饮档次描述
     */
    private record SpendTier(String name, double hotelPerNight, double foodPerDay, double localPerDay,
                             BigDecimal ticketFactor, double otherPerDay,
                             String hotelTierName, String foodTierName) {
    }

    // ==================================================================================
    // 一、事前：预算反推封套
    // ==================================================================================

    /**
     * 构建预算封套（住宿单价使用档次默认价）。
     */
    public BudgetEnvelope build(BigDecimal userBudget, int days, int poiCount,
                                BigDecimal transportCost, String transportMode) {
        return build(userBudget, days, poiCount, transportCost, transportMode, Map.of());
    }

    /**
     * 构建预算封套（住宿单价使用档次默认价，并携带大交通时长）。
     */
    public BudgetEnvelope build(BigDecimal userBudget, int days, int poiCount,
                                BigDecimal transportCost, String transportMode,
                                TransportDuration transportDuration) {
        return build(userBudget, days, poiCount, transportCost, transportMode, Map.of(), transportDuration);
    }

    /**
     * 构建预算封套。
     *
     * @param userBudget     用户给定总预算（元），null 表示未指定
     * @param days           行程天数
     * @param poiCount       计划游玩的景点数（用于门票估算）
     * @param transportCost  往返大交通费用（元），由票价模型/真实 API 按预算选出
     * @param transportMode  出行方式描述
     * @param hotelOverrides 住宿快照价覆盖（档次名 → 元/晚），无快照的档次仍用默认价。
     *                       来自 t_hotel_price_snapshot，使封套的住宿上限贴近真实行情
     * @return 预算封套
     */
    public BudgetEnvelope build(BigDecimal userBudget, int days, int poiCount,
                                BigDecimal transportCost, String transportMode,
                                Map<String, BigDecimal> hotelOverrides) {
        return build(userBudget, days, poiCount, transportCost, transportMode, hotelOverrides, null);
    }

    /**
     * 构建预算封套。
     *
     * @param transportDuration 大交通时长（真实车次历时或速度模型估算），可为 null
     */
    public BudgetEnvelope build(BigDecimal userBudget, int days, int poiCount,
                                BigDecimal transportCost, String transportMode,
                                Map<String, BigDecimal> hotelOverrides,
                                TransportDuration transportDuration) {
        BudgetEnvelope env = new BudgetEnvelope();
        int safeDays = Math.max(days, 1);
        int nights = Math.max(safeDays - 1, 0);
        BigDecimal transport = scale(transportCost);

        env.setUserBudget(userBudget);
        env.setDays(safeDays);
        env.setNights(nights);
        env.setTransportCost(transport);
        env.setTransportMode(transportMode == null || transportMode.isBlank() ? "高铁二等座" : transportMode);
        env.setTransportDuration(transportDuration);
        env.setTransportDurationSource(transportDuration == null ? null : transportDuration.getSource());
        env.setTransportDurationText(transportDuration == null ? null : transportDuration.summary());

        int paidPoi = poiCount > 0 ? poiCount : Math.max(safeDays * 2, 2);

        // ---------- 情形 1：用户未指定预算 → 给「舒适」档参考值，不做约束 ----------
        if (userBudget == null || userBudget.compareTo(BigDecimal.ZERO) <= 0) {
            applyTier(env, TIERS.get(1), paidPoi, hotelOverrides);
            env.setLevel("舒适");
            env.setFeasible(true);
            env.setRemaining(BigDecimal.ZERO);
            env.setMinBudget(env.getTotal());
            env.getSuggestions().add("未检测到明确的预算金额，已按「舒适」档给出参考费用。"
                    + "若需严格控预算，请在需求中写明「预算 X 元」。");
            return env;
        }

        // ---------- 情形 2：档次阶梯回退，取预算内最高档 ----------
        for (SpendTier tier : TIERS) {
            BigDecimal total = totalFor(env, tier, paidPoi, hotelOverrides);
            if (total.compareTo(userBudget) <= 0) {
                applyTier(env, tier, paidPoi, hotelOverrides);
                env.setFeasible(true);
                env.setLevel(tier.name());
                env.setRemaining(userBudget.subtract(total));
                env.setMinBudget(totalFor(env, TIERS.get(TIERS.size() - 1), 0, hotelOverrides));
                addWithinSuggestions(env, tier);
                log.info("[ENVELOPE] 预算{}元/{}天 选定「{}」档 预计{}元 结余{}元",
                        userBudget, safeDays, tier.name(), total, env.getRemaining());
                return env;
            }
            env.getAdjustments().add(String.format("「%s」档预计 %s 元，超出预算 %s 元，自动降级重算",
                    tier.name(), yuan(total), yuan(total.subtract(userBudget))));
        }

        // ---------- 情形 3：连「经济」档都超预算 → 取消收费景点门票再试 ----------
        SpendTier eco = TIERS.get(TIERS.size() - 1);
        BigDecimal ecoNoTicket = totalFor(env, eco, 0, hotelOverrides);
        applyTier(env, eco, 0, hotelOverrides);
        env.setLevel("经济");
        env.setMinBudget(ecoNoTicket);
        if (ecoNoTicket.compareTo(userBudget) <= 0) {
            env.setFeasible(true);
            env.setRemaining(userBudget.subtract(ecoNoTicket));
            env.getAdjustments().add("已取消收费景点门票预算，行程以免费景点 / 低价景点为主");
            env.getSuggestions().add(String.format(
                    "预算偏紧：已按「经济档 + 免费景点为主」安排，预计 %s 元，控制在预算 %s 元以内。",
                    yuan(ecoNoTicket), yuan(userBudget)));
            log.info("[ENVELOPE] 预算{}元/{}天 降级为「经济档+免费景点」预计{}元", userBudget, safeDays, ecoNoTicket);
            return env;
        }

        // ---------- 情形 4：判定不可行 ----------
        env.setFeasible(false);
        env.setRemaining(userBudget.subtract(ecoNoTicket));
        env.getAdjustments().add(String.format("最低可行预算 %s 元仍高于给定预算 %s 元",
                yuan(ecoNoTicket), yuan(userBudget)));
        addInfeasibleSuggestions(env, paidPoi);
        log.warn("[ENVELOPE] 预算{}元/{}天 不可行，最低需{}元（缺口{}元）",
                userBudget, safeDays, ecoNoTicket, ecoNoTicket.subtract(userBudget));
        return env;
    }

    /** 应用某一档次：写入各分项上限与合计（酒店单价优先用快照真实价） */
    private void applyTier(BudgetEnvelope env, SpendTier tier, int paidPoi,
                           Map<String, BigDecimal> hotelOverrides) {
        BigDecimal nights = BigDecimal.valueOf(env.getNights());
        BigDecimal days = BigDecimal.valueOf(env.getDays());
        BigDecimal ticket = ticketFor(tier, paidPoi);
        BigDecimal hotelPrice = hotelFor(tier, hotelOverrides);

        env.setHotelPerNight(scale(hotelPrice));
        env.setHotelTier(tier.hotelTierName());
        env.setFoodPerDay(scale(BigDecimal.valueOf(tier.foodPerDay())));
        env.setFoodTier(tier.foodTierName());
        env.setLocalPerDay(scale(BigDecimal.valueOf(tier.localPerDay())));
        env.setTicketTotal(ticket);
        env.setPaidPoiCount(paidPoi);
        env.setOtherTotal(scale(BigDecimal.valueOf(tier.otherPerDay()).multiply(days)));

        BigDecimal total = env.getTransportCost()
                .add(env.getHotelPerNight().multiply(nights))
                .add(env.getFoodPerDay().multiply(days))
                .add(env.getLocalPerDay().multiply(days))
                .add(ticket)
                .add(env.getOtherTotal());
        env.setTotal(scale(total));
    }

    /** 档次对应酒店单价：有快照覆盖用快照价，否则用档次默认价 */
    private BigDecimal hotelFor(SpendTier tier, Map<String, BigDecimal> hotelOverrides) {
        if (hotelOverrides != null) {
            BigDecimal override = hotelOverrides.get(tier.name());
            if (override != null && override.compareTo(BigDecimal.ZERO) > 0) {
                return override;
            }
        }
        return BigDecimal.valueOf(tier.hotelPerNight());
    }

    /** 纯计算：某一档次下的合计（不改动 env） */
    private BigDecimal totalFor(BudgetEnvelope env, SpendTier tier, int paidPoi,
                                Map<String, BigDecimal> hotelOverrides) {
        BigDecimal days = BigDecimal.valueOf(env.getDays());
        BigDecimal nights = BigDecimal.valueOf(env.getNights());
        return scale(env.getTransportCost()
                .add(hotelFor(tier, hotelOverrides).multiply(nights))
                .add(BigDecimal.valueOf(tier.foodPerDay()).multiply(days))
                .add(BigDecimal.valueOf(tier.localPerDay()).multiply(days))
                .add(ticketFor(tier, paidPoi))
                .add(BigDecimal.valueOf(tier.otherPerDay()).multiply(days)));
    }

    private BigDecimal ticketFor(SpendTier tier, int paidPoi) {
        return TICKET_AVG.multiply(BigDecimal.valueOf(Math.max(paidPoi, 0)))
                .multiply(tier.ticketFactor())
                .setScale(0, RoundingMode.HALF_UP);
    }

    /** 预算内：给出结余利用建议 */
    private void addWithinSuggestions(BudgetEnvelope env, SpendTier tier) {
        BigDecimal remain = env.getRemaining();
        env.getSuggestions().add(String.format(
                "预算 %s 元内可执行「%s」档方案：%s，%s；预计总花费 %s 元，结余约 %s 元。",
                yuan(env.getUserBudget()), tier.name(), tier.hotelTierName(), tier.foodTierName(),
                yuan(env.getTotal()), yuan(remain)));
        if (remain.compareTo(env.getUserBudget().multiply(new BigDecimal("0.20"))) > 0) {
            env.getSuggestions().add(String.format(
                    "结余较充裕（约 %s 元），可考虑升级住宿档次、增加 1 个付费体验项目，或预留购物预算。",
                    yuan(remain)));
        }
    }

    /** 不可行：给出可执行的降级路径 */
    private void addInfeasibleSuggestions(BudgetEnvelope env, int paidPoi) {
        BigDecimal budget = env.getUserBudget();
        BigDecimal minBudget = env.getMinBudget();
        env.getSuggestions().add(String.format(
                "当前预算 %s 元低于该行程的最低可行预算 %s 元，缺口约 %s 元。",
                yuan(budget), yuan(minBudget), yuan(minBudget.subtract(budget))));

        // 反推「预算不变时可支持的最大天数」
        int fitDays = maxFeasibleDays(env, paidPoi, budget);
        if (fitDays > 0 && fitDays < env.getDays()) {
            env.getSuggestions().add(String.format(
                    "方案一：天数由 %d 天缩短为 %d 天，即可控制在预算内。", env.getDays(), fitDays));
        }
        env.getSuggestions().add("方案二：改乘普速列车硬座 / 长途大巴往返，可显著降低大交通占比。");
        env.getSuggestions().add("方案三：住宿改为青旅床位或经济型连锁，餐饮以本地小吃为主。");
        env.getSuggestions().add(String.format("方案四：把总预算提高到 %s 元以上。", yuan(minBudget)));
    }

    /**
     * 反推：在给定预算下，最多能支持几天行程（经济档、免费景点为主）。
     *
     * @return 可支持的最大天数，0 表示 1 天都不可行
     */
    public int maxFeasibleDays(BudgetEnvelope env, int paidPoi, BigDecimal budget) {
        SpendTier eco = TIERS.get(TIERS.size() - 1);
        for (int d = env.getDays(); d >= 1; d--) {
            BudgetEnvelope probe = new BudgetEnvelope();
            probe.setDays(d);
            probe.setNights(Math.max(d - 1, 0));
            probe.setTransportCost(env.getTransportCost());
            if (totalFor(probe, eco, 0, Map.of()).compareTo(budget) <= 0) {
                return d;
            }
        }
        return 0;
    }

    // ==================================================================================
    // 二、事后：用封套核验并再平衡
    // ==================================================================================

    /**
     * 用预算封套核验已计算的预算，并把各分项收敛到封套上限内。
     *
     * <p>规则：<b>只压不抬</b>——低于上限的分项保持原值（尊重行程实际内容），
     * 高于上限的分项截断到上限。由于封套各分项之和本身 ≤ 用户预算（可行时），
     * 截断后总预算必然落在预算内，从而实现「严格按预算」。
     *
     * @param budget 已融合的预算对象（会被就地修改）
     * @param env    预算封套，null 或未指定预算时仅标记为 UNKNOWN
     */
    public void reconcile(Budget budget, BudgetEnvelope env) {
        if (budget == null) {
            return;
        }
        if (env == null || env.getUserBudget() == null) {
            budget.setBudgetStatus(STATUS_UNKNOWN);
            return;
        }

        budget.setUserBudget(env.getUserBudget());

        BigDecimal days = BigDecimal.valueOf(Math.max(env.getDays(), 1));
        BigDecimal nights = BigDecimal.valueOf(env.getNights());

        // 分项上限：交通上限 = 往返大交通 + 市内交通封套（原引擎把两者合并计在 transportCost）
        BigDecimal transportCap = env.getTransportCost().add(env.getLocalPerDay().multiply(days));
        BigDecimal hotelCap = env.getHotelPerNight().multiply(nights);
        BigDecimal foodCap = env.getFoodPerDay().multiply(days);
        BigDecimal ticketCap = env.getTicketTotal();
        BigDecimal otherCap = env.getOtherTotal();

        BigDecimal before = nz(budget.getTransportCost())
                .add(nz(budget.getAccommodationCost())).add(nz(budget.getFoodCost()))
                .add(nz(budget.getTicketCost())).add(nz(budget.getOtherCost()));

        budget.setTransportCost(clampDown(budget.getTransportCost(), transportCap));
        budget.setAccommodationCost(clampDown(budget.getAccommodationCost(), hotelCap));
        budget.setFoodCost(clampDown(budget.getFoodCost(), foodCap));
        budget.setTicketCost(clampDown(budget.getTicketCost(), ticketCap));
        budget.setOtherCost(clampDown(budget.getOtherCost(), otherCap));

        BigDecimal total = nz(budget.getTransportCost())
                .add(nz(budget.getAccommodationCost())).add(nz(budget.getFoodCost()))
                .add(nz(budget.getTicketCost())).add(nz(budget.getOtherCost()));
        budget.setTotalBudget(scale(total));

        BigDecimal remaining = env.getUserBudget().subtract(total);
        budget.setRemainingBudget(scale(remaining));
        budget.setBudgetStatus(remaining.compareTo(BigDecimal.ZERO) >= 0 ? STATUS_WITHIN : STATUS_OVER);

        if (before.compareTo(total) != 0) {
            log.info("[RECONCILE] 会话{} 预算再平衡：{}元 → {}元（用户预算{}元，状态{}）",
                    budget.getSessionId(), before.setScale(0, RoundingMode.HALF_UP),
                    total.setScale(0, RoundingMode.HALF_UP), env.getUserBudget(), budget.getBudgetStatus());
        }
    }

    // ==================================================================================
    // 工具方法
    // ==================================================================================

    /** 只压不抬：v 高于 cap 时截断到 cap，否则保持原值 */
    private BigDecimal clampDown(BigDecimal v, BigDecimal cap) {
        BigDecimal value = nz(v);
        if (cap == null || cap.compareTo(BigDecimal.ZERO) < 0) {
            return scale(value);
        }
        return scale(value.min(cap));
    }

    private BigDecimal nz(BigDecimal v) {
        return v == null ? BigDecimal.ZERO : v;
    }

    private BigDecimal scale(BigDecimal v) {
        return nz(v).setScale(2, RoundingMode.HALF_UP);
    }

    private String yuan(BigDecimal v) {
        return nz(v).setScale(0, RoundingMode.HALF_UP).toPlainString();
    }
}
