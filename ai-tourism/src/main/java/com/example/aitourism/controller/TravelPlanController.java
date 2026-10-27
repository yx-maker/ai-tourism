package com.example.aitourism.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.example.aitourism.dto.BaseResponse;
import com.example.aitourism.entity.TravelPlan;
import com.example.aitourism.service.TravelPlanService;
import com.example.aitourism.util.Constants;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.util.Map;

/**
 * 旅行计划模块（行程持久化，开题报告数据库设计「行程表」落地）。
 *
 * <p>把会话中生成的攻略固化为「我的计划」：列表 / 详情 / 编辑 / 重算 / 归档。
 * 编辑保存采用乐观锁（version），并发冲突返回 4090。
 */
@RestController
@RequestMapping("/travel-plan")
@RequiredArgsConstructor
public class TravelPlanController {

    private final TravelPlanService travelPlanService;

    /** 从会话保存为旅行计划 */
    @PostMapping("/save-from-session")
    public BaseResponse<TravelPlan> saveFromSession(@RequestBody Map<String, Object> body) {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            String sessionId = (String) body.get("session_id");
            String title = (String) body.get("title");
            if (sessionId == null || sessionId.trim().isEmpty()) {
                return BaseResponse.error(2001, "会话ID不能为空");
            }
            return BaseResponse.success(travelPlanService.saveFromSession(sessionId, userId, title));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 我的计划列表 */
    @GetMapping("/list")
    public BaseResponse<Map<String, Object>> list(
            @RequestParam(defaultValue = "1") Integer page,
            @RequestParam(defaultValue = "10") Integer pageSize) {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            return BaseResponse.success(travelPlanService.list(userId, page, pageSize));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 计划详情 */
    @GetMapping("/detail/{planId}")
    public BaseResponse<TravelPlan> detail(@PathVariable String planId) {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            return BaseResponse.success(travelPlanService.detail(planId, userId));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /**
     * 更新计划（乐观锁 + 服务端预算重算）。
     * body: plan_id, version(必填), title?, days?, budget_amount?, content?, daily_routes?
     */
    @PostMapping("/update")
    public BaseResponse<TravelPlan> update(@RequestBody Map<String, Object> body) {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            String planId = (String) body.get("plan_id");
            if (planId == null || planId.trim().isEmpty()) {
                return BaseResponse.error(2001, "计划ID不能为空");
            }
            Integer version = body.get("version") instanceof Number n ? n.intValue() : null;
            if (version == null) {
                return BaseResponse.error(2002, "缺少版本号 version（乐观锁校验）");
            }
            String title = (String) body.get("title");
            Integer days = body.get("days") instanceof Number n ? n.intValue() : null;
            BigDecimal budgetAmount = body.get("budget_amount") instanceof Number n
                    ? BigDecimal.valueOf(n.doubleValue()) : null;
            String content = (String) body.get("content");
            String dailyRoutes = (String) body.get("daily_routes");
            return BaseResponse.success(travelPlanService.update(
                    planId, userId, version, title, days, budgetAmount, content, dailyRoutes));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 归档（软删除）计划 */
    @PostMapping("/delete")
    public BaseResponse<Void> delete(@RequestBody Map<String, Object> body) {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            String planId = (String) body.get("plan_id");
            if (planId == null || planId.trim().isEmpty()) {
                return BaseResponse.error(2001, "计划ID不能为空");
            }
            boolean ok = travelPlanService.archive(planId, userId);
            if (!ok) {
                return BaseResponse.error(3005, "计划不存在或无权访问");
            }
            return BaseResponse.success();
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
            return msg.substring(5);
        }
        return msg != null ? msg : "服务端错误";
    }
}
