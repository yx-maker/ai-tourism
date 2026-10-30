package com.example.aitourism.dto.budget;

import lombok.Data;

/**
 * 大交通时长（单程在途时间）—— 与「大交通价格」并列的可溯源指标。
 *
 * <p>论文定位：预算系统原先只回答「要花多少钱」，本次补充「要花多少时间」，
 * 使「按预算选交通方式」的取舍可见：预算紧张时降级到普速列车会省下票价，
 * 但单程在途时间可能从 7 小时变成 30 小时，这个代价必须显式呈现给用户。
 *
 * <p>数据真实性分层（与价格三级降级同一套原则）：
 * <ol>
 *   <li>{@link #SOURCE_REAL}：12306 实爬车次历时（train_duration_local.json），
 *       按「高铁动车 / 普速」分类取最快一趟，携带车次号与到发时刻，可溯源</li>
 *   <li>{@link #SOURCE_ESTIMATE}：速度模型估算（里程 ÷ 方式巡航速度 + 进出站/候车附加），
 *       仅在无真实车次数据时使用，前端必须标注「估算」</li>
 * </ol>
 */
@Data
public class TransportDuration {

    /** 真实车次历时（12306 实爬） */
    public static final String SOURCE_REAL = "TRAIN_REAL";
    /** 速度模型估算 */
    public static final String SOURCE_ESTIMATE = "ESTIMATE";

    /** 单程在途时长（分钟） */
    private Integer minutesOneWay;

    /** 交通类别：高铁动车 / 普速 / 长途大巴 / 飞机经济舱 */
    private String kind;

    /** 真实车次号（如 G2942），估算时为 null */
    private String trainCode;

    /** 出发时刻 HH:mm（真实车次） */
    private String depart;

    /** 到达时刻 HH:mm（真实车次） */
    private String arrive;

    /** {@link #SOURCE_REAL} 或 {@link #SOURCE_ESTIMATE} */
    private String source;

    /** 人类可读说明，如「G2942 07:44→14:46」或「速度模型估算」 */
    private String note;

    /** 是否为真实数据 */
    public boolean isReal() {
        return SOURCE_REAL.equals(source);
    }

    /** 单程时长文案，如「7 小时 2 分」 */
    public String textOneWay() {
        return minutesOneWay == null ? null : human(minutesOneWay.longValue());
    }

    /** 往返在途合计文案，如「14 小时 4 分」 */
    public String textRoundTrip() {
        return minutesOneWay == null ? null : human(minutesOneWay * 2L);
    }

    /**
     * 来源标签（供 Prompt 与前端说明）：
     * 「12306 实爬车次历时（G2942 07:44→14:46）」/「速度模型估算（高铁动车，约 1231 km）」
     */
    public String label() {
        String head = isReal() ? "12306 实爬车次历时" : "速度模型估算";
        return (note == null || note.isBlank()) ? head : head + "（" + note + "）";
    }

    /** 完整展示文案：「单程约 7 小时 2 分 · 往返在途约 14 小时 4 分」 */
    public String summary() {
        String one = textOneWay();
        if (one == null) {
            return null;
        }
        return "单程约 " + one + " · 往返在途约 " + textRoundTrip();
    }

    /** 分钟数 → 「X 小时 Y 分」/「X 分钟」 */
    public static String human(Long minutes) {
        if (minutes == null) {
            return null;
        }
        long m = Math.max(minutes, 0);
        if (m < 60) {
            return m + " 分钟";
        }
        long h = m / 60;
        long rest = m % 60;
        return rest == 0 ? h + " 小时" : h + " 小时 " + rest + " 分";
    }
}
