package com.example.aitourism.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.example.aitourism.dto.BaseResponse;
import com.example.aitourism.entity.UserPreference;
import com.example.aitourism.service.UserPreferenceService;
import com.example.aitourism.util.Constants;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 用户偏好模块（开题报告数据库设计：用户偏好表，个性化推荐数据支撑）
 */
@RestController
@RequestMapping("/preference")
@RequiredArgsConstructor
public class PreferenceController {

    private final UserPreferenceService preferenceService;

    /** 获取我的偏好 */
    @GetMapping("/get")
    public BaseResponse<UserPreference> get() {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            return BaseResponse.success(preferenceService.get(userId));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 保存我的偏好 */
    @PostMapping("/save")
    public BaseResponse<UserPreference> save(@RequestBody UserPreference pref) {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            return BaseResponse.success(preferenceService.save(userId, pref));
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
