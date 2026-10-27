import com.example.aitourism.dto.budget.BudgetEnvelope;
import com.example.aitourism.entity.Budget;
import com.example.aitourism.service.BudgetEnvelopeService;

import java.math.BigDecimal;
import java.util.Map;

/**
 * 预算封套引擎独立验证器（不依赖 JUnit / Spring 上下文）。
 * 与 src/test/.../BudgetEnvelopeServiceTest.java 覆盖同一组场景，
 * 用于在离线环境下直接对 target/classes 中的编译产物做行为验证。
 */
public class VerifyEnvelope {

    static int pass = 0;
    static int fail = 0;

    static final BigDecimal TRANSPORT = new BigDecimal("800");
    static final BudgetEnvelopeService SVC = new BudgetEnvelopeService();

    public static void main(String[] args) {
        // 1. 预算充裕 → 品质档
        BudgetEnvelope q = SVC.build(new BigDecimal("8000"), 5, 8, TRANSPORT, "飞机经济舱");
        check("充裕预算选中品质档", "品质".equals(q.getLevel()));
        check("充裕预算可行", q.isFeasible());
        check("封套合计不超预算", q.getTotal().compareTo(new BigDecimal("8000")) <= 0);
        check("品质档住宿 480/晚", eq("480", q.getHotelPerNight()));
        check("5天=4晚", q.getNights() == 4);

        // 2. 预算中等 → 舒适档
        BudgetEnvelope c = SVC.build(new BigDecimal("4000"), 5, 8, TRANSPORT, "高铁二等座");
        check("中等预算降级到舒适档", "舒适".equals(c.getLevel()));
        check("舒适档合计 3525", eq("3525", c.getTotal()));
        check("记录品质档降级原因", c.getAdjustments().get(0).contains("品质"));
        check("舒适档住宿 260/晚", eq("260", c.getHotelPerNight()));

        // 3. 预算紧张 → 经济档
        BudgetEnvelope e = SVC.build(new BigDecimal("3000"), 5, 8, TRANSPORT, "高铁二等座");
        check("紧张预算降级到经济档", "经济".equals(e.getLevel()));
        check("经济档合计 2241", eq("2241", e.getTotal()));
        check("记录 2 次降级", e.getAdjustments().size() == 2);
        check("经济档住宿 120/晚", eq("120", e.getHotelPerNight()));

        // 4. 极紧 → 取消收费景点
        BudgetEnvelope t = SVC.build(new BigDecimal("2100"), 5, 8, TRANSPORT, "高铁二等座");
        check("极紧预算仍可行", t.isFeasible());
        check("取消收费景点", t.getPaidPoiCount() == 0);
        check("门票预算归零", eq("0", t.getTicketTotal()));
        check("提示免费景点为主",
                t.getAdjustments().stream().anyMatch(a -> a.contains("免费景点")));

        // 5. 不可行
        BudgetEnvelope inf = SVC.build(new BigDecimal("1200"), 5, 8, new BigDecimal("400"), "高铁二等座");
        check("预算不足判定不可行", !inf.isFeasible());
        check("最低可行预算 1505", eq("1505", inf.getMinBudget()));
        check("结余为负（缺口）", inf.getRemaining().compareTo(BigDecimal.ZERO) < 0);
        check("给出缩短天数建议",
                inf.getSuggestions().stream().anyMatch(s -> s.contains("缩短")));
        check("给出更经济交通建议",
                inf.getSuggestions().stream().anyMatch(s -> s.contains("硬座") || s.contains("大巴")));

        // 6. 未指定预算
        BudgetEnvelope n = SVC.build(null, 4, 6, TRANSPORT, "高铁二等座");
        check("无预算时按舒适档参考", "舒适".equals(n.getLevel()));
        check("无预算时状态 UNKNOWN", "UNKNOWN".equals(reconcileStatus(n)));

        // 7. 核验再平衡：只压不抬
        BudgetEnvelope env = SVC.build(new BigDecimal("3000"), 5, 8, TRANSPORT, "高铁二等座");
        Budget over = new Budget();
        over.setSessionId("verify-1");
        over.setTransportCost(new BigDecimal("1600"));
        over.setAccommodationCost(new BigDecimal("2500"));
        over.setFoodCost(new BigDecimal("1200"));
        over.setTicketCost(new BigDecimal("900"));
        over.setOtherCost(new BigDecimal("800"));
        SVC.reconcile(over, env);
        check("核验后总预算 ≤ 用户预算", over.getTotalBudget().compareTo(new BigDecimal("3000")) <= 0);
        check("核验后总预算 = 封套上限和 2241", eq("2241", over.getTotalBudget()));
        check("状态 WITHIN_BUDGET", "WITHIN_BUDGET".equals(over.getBudgetStatus()));
        check("交通压到 925", eq("925", over.getTransportCost()));
        check("住宿压到 480", eq("480", over.getAccommodationCost()));
        check("餐饮压到 350", eq("350", over.getFoodCost()));
        check("结余 759", eq("759", over.getRemainingBudget()));

        Budget low = new Budget();
        low.setSessionId("verify-2");
        low.setTransportCost(new BigDecimal("800"));
        low.setAccommodationCost(new BigDecimal("100"));
        low.setFoodCost(new BigDecimal("50"));
        low.setTicketCost(BigDecimal.ZERO);
        low.setOtherCost(BigDecimal.ZERO);
        BudgetEnvelope env5k = SVC.build(new BigDecimal("5000"), 5, 8, TRANSPORT, "高铁二等座");
        SVC.reconcile(low, env5k);
        check("低于上限不抬高（住宿保持 100）", eq("100", low.getAccommodationCost()));
        check("低于上限不抬高（餐饮保持 50）", eq("50", low.getFoodCost()));
        check("产生结余", low.getRemainingBudget().compareTo(BigDecimal.ZERO) > 0);

        // 8. 1 天行程
        BudgetEnvelope one = SVC.build(new BigDecimal("1000"), 1, 2, new BigDecimal("200"), "长途大巴");
        check("1天=0晚", one.getNights() == 0);
        check("1天行程仍可行", one.getTotal().compareTo(new BigDecimal("1000")) <= 0);

        // 9. 边界：恰好等于封套合计
        BigDecimal exact = SVC.build(new BigDecimal("99999"), 3, 4, TRANSPORT, "高铁二等座").getTotal();
        BudgetEnvelope bd = SVC.build(exact, 3, 4, TRANSPORT, "高铁二等座");
        check("边界值可行", bd.isFeasible());
        check("边界值结余为 0", bd.getRemaining().compareTo(BigDecimal.ZERO) == 0);

        // 10. 序列化
        Map<String, Object> plan = c.toPlanMap();
        check("plan 含交通方式", "高铁二等座".equals(plan.get("transportMode")));
        check("plan 含档次", "舒适".equals(plan.get("level")));
        check("plan 含建议", plan.get("suggestions") != null);
        check("plan 含调整记录", plan.get("adjustments") != null);

        System.out.println("\n========================================");
        System.out.printf("  通过 %d 项，失败 %d 项%n", pass, fail);
        System.out.println("========================================");
        if (fail > 0) System.exit(1);
    }

    static String reconcileStatus(BudgetEnvelope env) {
        Budget b = new Budget();
        b.setTransportCost(BigDecimal.ZERO);
        b.setAccommodationCost(BigDecimal.ZERO);
        b.setFoodCost(BigDecimal.ZERO);
        b.setTicketCost(BigDecimal.ZERO);
        b.setOtherCost(BigDecimal.ZERO);
        SVC.reconcile(b, env);
        return b.getBudgetStatus();
    }

    static boolean eq(String expected, BigDecimal actual) {
        return actual != null && new BigDecimal(expected).compareTo(actual) == 0;
    }

    static void check(String name, boolean ok) {
        if (ok) {
            pass++;
            System.out.println("  [PASS] " + name);
        } else {
            fail++;
            System.out.println("  [FAIL] " + name);
        }
    }
}
