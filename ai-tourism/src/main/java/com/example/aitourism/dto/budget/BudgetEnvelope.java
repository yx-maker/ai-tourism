package com.example.aitourism.dto.budget;

import lombok.Data;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

/**
 * 预算封套（Budget Envelope）—— 预算反推规划的结果载体。
 *
 * <p>论文定位：原「事后估算」预算模块的升级。原流程是
 * <i>生成行程 → 估算费用</i>，用户给定预算不产生任何约束；
 * 新流程是 <i>解析预算 → 反推封套 → 封套内生成行程 → 核验与再平衡</i>。
 *
 * <p>封套回答四个问题：
 * <ol>
 *   <li>这趟行程在给定预算下<b>能不能去</b>（{@link #feasible}）</li>
 *   <li>如果能去，<b>最高可承受的消费档次</b>是什么（{@link #level}）</li>
 *   <li>各分项的<b>费用上限</b>分别是多少（hotelPerNight / foodPerDay / …）</li>
 *   <li>如果不能去，<b>最低需要多少预算</b>、有哪些降级选项（{@link #minBudget}、{@link #adjustments}）</li>
 * </ol>
 */
@Data
public class BudgetEnvelope {

    /** 用户给定的总预算（元），null 表示未指定 */
    private BigDecimal userBudget;

    /** 行程天数 */
    private int days;

    /** 住宿晚数（= max(days-1, 0)） */
    private int nights;

    // ---------------- 大交通（由既有票价模型按预算选出） ----------------

    /** 往返大交通费用（元） */
    private BigDecimal transportCost = BigDecimal.ZERO;

    /** 出行方式描述，如「高铁二等座」 */
    private String transportMode;

    // ---------------- 大交通时长（按预算选定方式对应的在途时间） ----------------

    /** 大交通时长（单程在途分钟 + 来源 + 说明），见 {@link TransportDuration} */
    private TransportDuration transportDuration;

    /**
     * 单程在途时长文案，如「7 小时 2 分」（冗余字段，供前端直接展示）。
     * 真实来源为 12306 实爬车次历时，估算来源为速度模型。
     */
    private String transportDurationText;

    /** 时长来源：TRAIN_REAL（12306 实爬车次历时）/ ESTIMATE（速度模型估算） */
    private String transportDurationSource;

    // ---------------- 分项上限（封套核心） ----------------

    /** 住宿单价上限（元/晚） */
    private BigDecimal hotelPerNight = BigDecimal.ZERO;

    /** 住宿档次描述 */
    private String hotelTier;

    /** 餐饮上限（元/天） */
    private BigDecimal foodPerDay = BigDecimal.ZERO;

    /** 餐饮档次描述 */
    private String foodTier;

    /** 市内交通上限（元/天） */
    private BigDecimal localPerDay = BigDecimal.ZERO;

    /** 门票合计上限（元） */
    private BigDecimal ticketTotal = BigDecimal.ZERO;

    /** 计入门票的收费景点数 */
    private int paidPoiCount;

    /** 其他（购物/纪念品等）上限（元） */
    private BigDecimal otherTotal = BigDecimal.ZERO;

    // ---------------- 汇总与判定 ----------------

    /** 封套内各分项合计（元） */
    private BigDecimal total = BigDecimal.ZERO;

    /** 预算结余（元）= userBudget - total，负数表示封套本身已超支 */
    private BigDecimal remaining = BigDecimal.ZERO;

    /** 在给定预算下是否可行 */
    private boolean feasible = true;

    /** 消费档次：经济 / 舒适 / 品质 */
    private String level;

    /** 该天数下的最低可行预算（元）——用于向用户提示"至少需要多少" */
    private BigDecimal minBudget = BigDecimal.ZERO;

    /** 降级/调整动作记录，如「住宿档次由品质降为舒适」 */
    private List<String> adjustments = new ArrayList<>();

    /** 面向用户的规划建议 */
    private List<String> suggestions = new ArrayList<>();

    /**
     * 转成写入 t_budget.plan_json 的出行方案（严格按预算的可执行结论）。
     */
    public java.util.Map<String, Object> toPlanMap() {
        java.util.Map<String, Object> m = new java.util.LinkedHashMap<>();
        m.put("userBudget", userBudget);
        m.put("days", days);
        m.put("nights", nights);
        m.put("level", level);
        m.put("feasible", feasible);
        m.put("transportMode", transportMode);
        m.put("transportCost", transportCost);
        // 交通时长：与交通方式/票价并列展示，让用户看到「省钱 = 多花时间」的取舍
        m.put("transportDuration", transportDuration == null ? null : transportDuration.summary());
        m.put("transportDurationSource", transportDurationSource);
        m.put("transportMinutesOneWay", transportDuration == null ? null : transportDuration.getMinutesOneWay());
        m.put("hotelTier", hotelTier);
        m.put("hotelPerNight", hotelPerNight);
        m.put("foodTier", foodTier);
        m.put("foodPerDay", foodPerDay);
        m.put("localPerDay", localPerDay);
        m.put("ticketTotal", ticketTotal);
        m.put("paidPoiCount", paidPoiCount);
        m.put("otherTotal", otherTotal);
        m.put("total", total);
        m.put("remaining", remaining);
        m.put("minBudget", minBudget);
        m.put("adjustments", adjustments);
        m.put("suggestions", suggestions);
        return m;
    }
}
