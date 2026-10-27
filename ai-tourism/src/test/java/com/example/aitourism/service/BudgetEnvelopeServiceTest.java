package com.example.aitourism.service;

import com.example.aitourism.dto.budget.BudgetEnvelope;
import com.example.aitourism.entity.Budget;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * 预算封套引擎单元测试 —— 「严格按预算规划」的可验证性证明。
 *
 * <p>论文实验设计：预算硬约束的核心承诺是
 * <b>「输出的总预算恒 ≤ 用户给定预算」</b>。
 * 该承诺由 {@code reconcile()} 的「只压不抬」截断规则保证，
 * 本测试用多组场景逐一验证。
 *
 * <p>基准算例：往返大交通 800 元、5 天、8 个景点。
 * <pre>
 *   品质档合计 = 800 + 480×4 + 220×5 + 80×5 + 70×8×1.3 + 120×5 = 5548
 *   舒适档合计 = 800 + 260×4 + 120×5 + 45×5 + 70×8×1.0 +  60×5 = 3525
 *   经济档合计 = 800 + 120×4 +  70×5 + 25×5 + 70×8×0.6 +  30×5 = 2241
 *   经济档(免门票) = 800 + 120×4 + 70×5 + 25×5 + 0 + 30×5 = 1905
 * </pre>
 */
class BudgetEnvelopeServiceTest {

    private final BudgetEnvelopeService service = new BudgetEnvelopeService();

    private static final BigDecimal TRANSPORT = new BigDecimal("800");

    /** 金额比较（忽略 scale，480.00 == 480） */
    private static void assertMoney(String expected, BigDecimal actual) {
        assertEquals(0, new BigDecimal(expected).compareTo(actual),
                "期望 " + expected + "，实际 " + actual);
    }

    @Test
    @DisplayName("预算充裕(8000) → 选中「品质」档，且封套合计不超预算")
    void shouldPickQualityTierWhenBudgetIsAmple() {
        BudgetEnvelope env = service.build(new BigDecimal("8000"), 5, 8, TRANSPORT, "飞机经济舱");

        assertEquals("品质", env.getLevel());
        assertTrue(env.isFeasible());
        assertTrue(env.getTotal().compareTo(new BigDecimal("8000")) <= 0, "封套合计必须 ≤ 用户预算");
        assertMoney("480", env.getHotelPerNight());
        assertEquals(4, env.getNights(), "5天行程 = 4晚住宿");
        assertTrue(env.getRemaining().compareTo(BigDecimal.ZERO) > 0);
    }

    @Test
    @DisplayName("预算中等(4000) → 自动从品质降级到「舒适」档，并记录降级原因")
    void shouldFallBackToComfortTier() {
        BudgetEnvelope env = service.build(new BigDecimal("4000"), 5, 8, TRANSPORT, "高铁二等座");

        assertEquals("舒适", env.getLevel());
        assertTrue(env.getTotal().compareTo(new BigDecimal("4000")) <= 0);
        assertFalse(env.getAdjustments().isEmpty(), "发生降级时应记录调整说明");
        assertTrue(env.getAdjustments().get(0).contains("品质"), "应记录从品质档降级的原因");
        assertMoney("260", env.getHotelPerNight());
    }

    @Test
    @DisplayName("预算紧张(3000) → 自动降级到「经济」档")
    void shouldFallBackToEconomyTier() {
        BudgetEnvelope env = service.build(new BigDecimal("3000"), 5, 8, TRANSPORT, "高铁二等座");

        assertEquals("经济", env.getLevel());
        assertTrue(env.getTotal().compareTo(new BigDecimal("3000")) <= 0);
        assertMoney("120", env.getHotelPerNight());
        assertEquals(2, env.getAdjustments().size(), "品质、舒适两档均应被记录为降级");
    }

    @Test
    @DisplayName("预算极紧(2100) → 取消收费景点门票，改为免费景点为主")
    void shouldDropPaidTicketsWhenBudgetIsVeryTight() {
        BudgetEnvelope env = service.build(new BigDecimal("2100"), 5, 8, TRANSPORT, "高铁二等座");

        assertTrue(env.isFeasible());
        assertEquals(0, env.getPaidPoiCount(), "应取消收费景点");
        assertMoney("0", env.getTicketTotal());
        assertTrue(env.getAdjustments().stream().anyMatch(a -> a.contains("免费景点")));
    }

    @Test
    @DisplayName("预算不可行(1200) → feasible=false，给出最低可行预算与缩短天数/换交通的建议")
    void shouldMarkInfeasibleAndSuggestAlternatives() {
        BudgetEnvelope env = service.build(new BigDecimal("1200"), 5, 8,
                new BigDecimal("400"), "高铁二等座");

        assertFalse(env.isFeasible(), "预算低于最低可行预算时应判定不可行");
        assertMoney("1505", env.getMinBudget());
        assertTrue(env.getMinBudget().compareTo(new BigDecimal("1200")) > 0, "最低可行预算应高于给定预算");
        assertTrue(env.getRemaining().compareTo(BigDecimal.ZERO) < 0, "不可行时结余应为负（缺口）");
        assertTrue(env.getSuggestions().stream().anyMatch(s -> s.contains("缩短")),
                "应给出缩短天数的建议，实际=" + env.getSuggestions());
        assertTrue(env.getSuggestions().stream().anyMatch(s -> s.contains("硬座") || s.contains("大巴")),
                "应给出更经济交通方式的建议");
    }

    @Test
    @DisplayName("未指定预算 → 按「舒适」档给出参考值，核验状态为 UNKNOWN")
    void shouldGiveReferenceEnvelopeWhenBudgetMissing() {
        BudgetEnvelope env = service.build(null, 4, 6, TRANSPORT, "高铁二等座");

        assertEquals("舒适", env.getLevel());
        assertTrue(env.isFeasible());
        assertEquals(BudgetEnvelopeService.STATUS_UNKNOWN, reconciledStatus(env));
    }

    @Test
    @DisplayName("核验再平衡：超出封套上限的分项被截断，总预算收敛到预算内")
    void shouldClampOverBudgetCategories() {
        BudgetEnvelope env = service.build(new BigDecimal("3000"), 5, 8, TRANSPORT, "高铁二等座");

        // 模拟 LLM 提取出远超预算的费用
        Budget budget = new Budget();
        budget.setTransportCost(new BigDecimal("1600"));
        budget.setAccommodationCost(new BigDecimal("2500"));
        budget.setFoodCost(new BigDecimal("1200"));
        budget.setTicketCost(new BigDecimal("900"));
        budget.setOtherCost(new BigDecimal("800"));
        budget.setSessionId("test-session");

        service.reconcile(budget, env);

        assertTrue(budget.getTotalBudget().compareTo(new BigDecimal("3000")) <= 0,
                "核验后总预算必须 ≤ 用户预算，实际=" + budget.getTotalBudget());
        assertEquals(BudgetEnvelopeService.STATUS_WITHIN, budget.getBudgetStatus());
        assertMoney("3000", budget.getUserBudget());
        assertEquals(0, budget.getRemainingBudget()
                .compareTo(new BigDecimal("3000").subtract(budget.getTotalBudget())));
        // 各分项应恰好被压到封套上限
        assertMoney("925", budget.getTransportCost());      // 800 + 25×5
        assertMoney("480", budget.getAccommodationCost());  // 120×4
        assertMoney("350", budget.getFoodCost());           // 70×5
    }

    @Test
    @DisplayName("核验再平衡：低于上限的分项保持原值（只压不抬）")
    void shouldNotInflateCategoriesBelowCap() {
        BudgetEnvelope env = service.build(new BigDecimal("5000"), 5, 8, TRANSPORT, "高铁二等座");

        Budget budget = new Budget();
        budget.setTransportCost(new BigDecimal("800"));
        budget.setAccommodationCost(new BigDecimal("100"));   // 远低于上限
        budget.setFoodCost(new BigDecimal("50"));
        budget.setTicketCost(BigDecimal.ZERO);
        budget.setOtherCost(BigDecimal.ZERO);
        budget.setSessionId("test-session");

        service.reconcile(budget, env);

        assertMoney("100", budget.getAccommodationCost());
        assertMoney("50", budget.getFoodCost());
        assertTrue(budget.getRemainingBudget().compareTo(BigDecimal.ZERO) > 0, "应产生预算结余");
        assertEquals(BudgetEnvelopeService.STATUS_WITHIN, budget.getBudgetStatus());
    }

    @Test
    @DisplayName("1天行程 → 0 晚住宿，住宿不计入合计")
    void shouldHandleSingleDayTrip() {
        BudgetEnvelope env = service.build(new BigDecimal("1000"), 1, 2, new BigDecimal("200"), "长途大巴");

        assertEquals(0, env.getNights());
        assertTrue(env.getTotal().compareTo(new BigDecimal("1000")) <= 0);
        // 1天行程住宿封套虽给出单价，但 nights=0 使其不产生费用
        assertTrue(env.getTotal().compareTo(env.getTransportCost()) > 0, "除交通外仍应有餐饮等费用");
    }

    @Test
    @DisplayName("预算边界：恰好等于封套合计时应判定可行且结余为 0")
    void shouldBeFeasibleAtExactBoundary() {
        BigDecimal exact = service.build(new BigDecimal("99999"), 3, 4, TRANSPORT, "高铁二等座").getTotal();

        BudgetEnvelope env = service.build(exact, 3, 4, TRANSPORT, "高铁二等座");
        assertTrue(env.isFeasible());
        assertEquals(0, env.getRemaining().compareTo(BigDecimal.ZERO));
    }

    @Test
    @DisplayName("封套序列化：plan_json 含交通方式、住宿档次与建议")
    void shouldSerializePlanMap() {
        BudgetEnvelope env = service.build(new BigDecimal("4000"), 5, 8, TRANSPORT, "高铁二等座");
        var plan = env.toPlanMap();

        assertEquals("高铁二等座", plan.get("transportMode"));
        assertEquals("舒适", plan.get("level"));
        assertEquals(5, plan.get("days"));
        assertNotNull(plan.get("suggestions"));
        assertNotNull(plan.get("adjustments"));
    }

    @Test
    @DisplayName("酒店快照价覆盖：有快照的档次用真实快照价计算封套")
    void shouldUseHotelSnapshotOverrides() {
        // 成都舒适档快照价 328 元/晚（来自 t_hotel_price_snapshot）
        Map<String, BigDecimal> overrides = Map.of("舒适", new BigDecimal("328"));

        BudgetEnvelope env = service.build(new BigDecimal("5000"), 5, 8, TRANSPORT, "高铁二等座", overrides);

        assertEquals("舒适", env.getLevel());
        assertMoney("328", env.getHotelPerNight());
        // 合计 = 800 + 328×4 + 120×5 + 45×5 + 70×8×1.0 + 60×5 = 3797
        assertMoney("3797", env.getTotal());
    }

    @Test
    @DisplayName("酒店快照价覆盖：无快照的档次仍用默认价（部分覆盖）")
    void shouldFallBackToDefaultHotelPriceWithoutSnapshot() {
        Map<String, BigDecimal> overrides = Map.of("品质", new BigDecimal("760")); // 只有品质档有快照

        // 预算 4000：品质档(760)超预算 → 降级舒适档（无快照 → 默认 260）
        BudgetEnvelope env = service.build(new BigDecimal("4000"), 5, 8, TRANSPORT, "高铁二等座", overrides);

        assertEquals("舒适", env.getLevel());
        assertMoney("260", env.getHotelPerNight()); // 舒适档无快照，应保持默认价
    }

    // ------------------------------------------------------------------

    /** 用一个空预算对象跑一次核验，取出状态（便于断言） */
    private String reconciledStatus(BudgetEnvelope env) {
        Budget b = new Budget();
        b.setTransportCost(BigDecimal.ZERO);
        b.setAccommodationCost(BigDecimal.ZERO);
        b.setFoodCost(BigDecimal.ZERO);
        b.setTicketCost(BigDecimal.ZERO);
        b.setOtherCost(BigDecimal.ZERO);
        service.reconcile(b, env);
        return b.getBudgetStatus();
    }
}
