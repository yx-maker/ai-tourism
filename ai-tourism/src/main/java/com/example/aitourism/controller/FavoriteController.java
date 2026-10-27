package com.example.aitourism.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.example.aitourism.dto.BaseResponse;
import com.example.aitourism.entity.Favorite;
import com.example.aitourism.service.FavoriteService;
import com.example.aitourism.util.Constants;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 收藏模块（开题报告数据库设计：收藏表）
 */
@RestController
@RequestMapping("/favorite")
@RequiredArgsConstructor
public class FavoriteController {

    private final FavoriteService favoriteService;

    /** 收藏景点 */
    @PostMapping("/add")
    public BaseResponse<Favorite> add(@RequestBody Map<String, Object> body) {
        try {
            Object poiIdObj = body.get("poi_id") != null ? body.get("poi_id") : body.get("poiId");
            Long poiId = Long.valueOf(String.valueOf(poiIdObj));
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            return BaseResponse.success(favoriteService.add(userId, poiId));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        } catch (Exception e) {
            return BaseResponse.error(Constants.ERROR_CODE_SERVER_ERROR, "参数错误");
        }
    }

    /** 我的收藏列表 */
    @GetMapping("/list")
    public BaseResponse<List<Favorite>> list() {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            return BaseResponse.success(favoriteService.list(userId));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 取消收藏 */
    @PostMapping("/remove")
    public BaseResponse<Void> remove(@RequestBody Map<String, Object> body) {
        try {
            Object poiIdObj = body.get("poi_id") != null ? body.get("poi_id") : body.get("poiId");
            Long poiId = Long.valueOf(String.valueOf(poiIdObj));
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            favoriteService.remove(userId, poiId);
            return BaseResponse.success();
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        } catch (Exception e) {
            return BaseResponse.error(Constants.ERROR_CODE_SERVER_ERROR, "参数错误");
        }
    }

    /** 是否已收藏 */
    @GetMapping("/check")
    public BaseResponse<Map<String, Object>> check(@RequestParam Long poiId) {
        try {
            String userId = (String) StpUtil.getLoginIdDefaultNull();
            if (userId == null) {
                return BaseResponse.error(1101, "未登录或登录已过期");
            }
            Map<String, Object> result = new HashMap<>();
            result.put("favorited", favoriteService.isFavorite(userId, poiId));
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
