package com.example.aitourism.service;

import com.example.aitourism.dto.budget.TransportDuration;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.Map;

/**
 * 大交通时长解析服务（唯一口径）。
 *
 * <p>把「按预算选出的交通方式」翻译成「要坐多久」，两条链路共用：
 * <ul>
 *   <li>{@code PlanningContextServiceImpl}：聊天规划时注入 Prompt，让行程正文写出耗时</li>
 *   <li>{@code BudgetServiceImpl}：预算分析时写入封套，供前端展示时间账</li>
 * </ul>
 *
 * <p>数据来源两级（与价格的三级降级同一原则）：
 * <ol>
 *   <li><b>真实车次历时</b>：classpath:price/train_duration_local.json（12306 实爬，
 *       按「高铁动车 / 普速」分类取最快一趟），source = TRAIN_REAL</li>
 *   <li><b>速度模型</b>：里程 ÷ 巡航速度 + 进出站附加，source = ESTIMATE</li>
 * </ol>
 * 任何一步失败都降级，绝不抛异常打断规划。
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class TransportDurationService {

    private final PriceProxyService priceProxyService;

    /**
     * 解析大交通单程在途时长。
     *
     * @param mode     出行方式描述（高铁二等座 / 普速列车硬座 / 飞机经济舱 / 长途大巴…）
     * @param origin   出发城市，可为 null
     * @param dest     到达城市，可为 null
     * @param distKm   城市间直线距离，≤0 表示未知（按典型跨省 800km 估算）
     * @return 时长（永不为 null；minutesOneWay 至少为 1）
     */
    public TransportDuration resolve(String mode, String origin, String dest, double distKm) {
        String kind = kindOf(mode);

        // ① 真实车次历时（仅铁路有真实数据；飞机/大巴无官方时刻表，直接走模型）
        if (origin != null && dest != null && ("高铁动车".equals(kind) || "普速".equals(kind))) {
            try {
                // 优先车次级绑定表：与 trainQuotes 派生的席别来自同一趟车，票价与时长必然自洽
                Map<String, PriceProxyService.TrainOption> opts =
                        priceProxyService.trainOptions(origin, dest);
                PriceProxyService.TrainOption opt = opts.get(kind);
                if (opt != null && opt.minutes() > 0) {
                    TransportDuration d = new TransportDuration();
                    d.setMinutesOneWay(opt.minutes());
                    d.setKind(kind);
                    d.setTrainCode(opt.trainCode());
                    d.setDepart(opt.depart());
                    d.setArrive(opt.arrive());
                    d.setSource(TransportDuration.SOURCE_REAL);
                    d.setNote(realNote(opt.trainCode(), opt.depart(), opt.arrive()));
                    log.info("[DURATION] {}→{} 「{}」单程 {}（{} 实爬车次，与票价同源）",
                            origin, dest, mode, d.textOneWay(),
                            opt.trainCode() == null ? "12306" : opt.trainCode());
                    return d;
                }
                // 未命中车次级报价：不退回「每类最快车次的历时时长」，
                // 因为那样又会出现「估算票价 + 高铁时长」的不成对组合。
                // 统一在下面走速度模型，保证「要么全真实、要么全估算」。
                log.debug("[DURATION] {}→{} 无车次级报价，降级速度模型（{}）", origin, dest, kind);
            } catch (Exception e) {
                log.warn("[DURATION] 车次历时查询失败（降级速度模型）: {}", e.getMessage());
            }
        }

        // ② 速度模型估算
        double km = distKm > 0 ? distKm : 800;
        TransportDuration d = new TransportDuration();
        d.setMinutesOneWay(estimateMinutes(kind, km));
        d.setKind(kind);
        d.setSource(TransportDuration.SOURCE_ESTIMATE);
        d.setNote(String.format("%s，约 %.0f km", kind, km));
        return d;
    }

    private static String realNote(PriceProxyService.DurationQuote q) {
        return realNote(q.trainCode(), q.depart(), q.arrive());
    }

    private static String realNote(String trainCode, String depart, String arrive) {
        StringBuilder sb = new StringBuilder();
        if (trainCode != null) {
            sb.append(trainCode).append(' ');
        }
        if (depart != null) {
            sb.append(depart).append('→');
        }
        if (arrive != null) {
            sb.append(arrive);
        }
        return sb.toString().trim();
    }

    /** 出行方式 → 时长类别（与 train_duration_local.json / Python duration_kind_of 同口径） */
    public static String kindOf(String mode) {
        if (mode == null || mode.isBlank()) {
            return "高铁动车";
        }
        if (mode.contains("飞机") || mode.contains("航班") || mode.contains("机票")) {
            return "飞机经济舱";
        }
        if (mode.contains("大巴") || mode.contains("汽车")) {
            return "长途大巴";
        }
        if (mode.contains("普速") || mode.contains("硬座") || mode.contains("硬卧")
                || mode.contains("软卧") || mode.contains("软座")) {
            return "普速";
        }
        return "高铁动车";
    }

    /**
     * 速度模型：里程 ÷ 方式巡航速度 + 固定附加（进出站 / 候车 / 安检）。
     * 铁路里程 ≈ 直线距离 × 1.3，与票价模型同源。
     */
    public static int estimateMinutes(String kind, double distKm) {
        double km = Math.max(distKm, 0);
        return switch (kind) {
            case "普速" -> (int) Math.round(km * 1.3 / 100 * 60) + 60;
            case "长途大巴" -> (int) Math.round(km * 1.2 / 60 * 60) + 30;
            case "飞机经济舱" -> (int) Math.round(km / 750 * 60) + 180;
            default -> (int) Math.round(km * 1.3 / 220 * 60) + 60;
        };
    }
}
