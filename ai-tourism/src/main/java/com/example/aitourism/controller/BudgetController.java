package com.example.aitourism.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.example.aitourism.dto.BaseResponse;
import com.example.aitourism.entity.Budget;
import com.example.aitourism.service.BudgetService;
import com.example.aitourism.util.Constants;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 预算分析模块（开题报告核心模块⑤）
 * 自动统计住宿、交通、餐饮、门票等分项预算，生成可视化图表数据（ECharts）
 */
@RestController
@RequestMapping("/budget")
@RequiredArgsConstructor
public class BudgetController {

    private final BudgetService budgetService;

    /** 行程预算分析：传入会话ID与行程文本，返回五类分项+总预算 */
    @PostMapping("/analyze")
    public BaseResponse<Budget> analyze(@RequestBody Map<String, Object> body) {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            String sessionId = (String) body.get("session_id");
            String itineraryText = (String) body.get("itinerary_text");
            if (sessionId == null || sessionId.trim().isEmpty()) {
                return BaseResponse.error(2001, "会话ID不能为空");
            }
            if (itineraryText == null || itineraryText.trim().isEmpty()) {
                return BaseResponse.error(2002, "行程内容不能为空");
            }
            return BaseResponse.success(budgetService.analyze(sessionId, userId, itineraryText));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 查询某会话的预算分析结果 */
    @GetMapping("/session/{sessionId}")
    public BaseResponse<Budget> getBySession(@PathVariable String sessionId) {
        try {
            return BaseResponse.success(budgetService.getBySession(sessionId));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 查询我的最近预算记录（ECharts 历史趋势） */
    @GetMapping("/recent")
    public BaseResponse<Map<String, Object>> recent(@RequestParam(defaultValue = "10") Integer limit) {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            List<Budget> list = budgetService.recent(userId, limit);
            // 汇总各分项累计（供饼图/趋势图使用）
            Map<String, Object> result = new HashMap<>();
            result.put("list", list);
            return BaseResponse.success(result);
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    private int parseCode(RuntimeException e) {
        String msg = e.getMessage();
        if (msg != null && msg.matches("^\\d{4}:.*")) {
            return Integer.parseInt(msg.substring(0, 4));
        }
        return Constants.ERROR_CODE_SERVER_ERROR;
    }

    private String parseMsg(RuntimeException e) {
        String msg = e.getMessage();
        if (msg != null && msg.matches("^\\d{4}:.*")) {
            return msg.substring(6);
        }
        return msg != null ? msg : "服务端错误";
    }
}
